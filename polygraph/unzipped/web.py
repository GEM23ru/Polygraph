"""
Polygraph Web — веб-интерфейс чата (как ChatGPT, но локально).

  pip install flask
  python web.py
  → открой в браузере http://127.0.0.1:5000

Использует то же ядро (core.py) и агента (agent.py), что и chat.py.
"""

import sys, os, json, time, uuid, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, Response
from core import create
from agent import Agent, default_tools

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 МБ лимит на загрузку файлов

# ── Инициализация агента (один раз при старте) ──
pg = create()
agent = Agent(pg, debug=False)  # tool_calls пишутся в agent_files/tool_calls.log постоянно
for t in default_tools(tavily_key=os.environ.get("TAVILY_API_KEY", "")):
    agent.register(t)

MAX_HISTORY = 50  # сколько последних пар сообщений передавать в модель.
                  # Было 6 — модель забывала контекст уже после 7-го сообщения.
                  # 50 = ~часа активного общения, достаточно для большинства диалогов.
                  # При лимите 128К токенов у моделей переполнить трудно.

# ── Хранилище нескольких чатов ──
# CHATS = { id: {"id","title","messages":[{"role","text","model"}], "ts"} }
CHATS = {}
CHATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chats.json")


def load_chats():
    global CHATS
    try:
        if os.path.exists(CHATS_FILE):
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                CHATS = json.load(f)
            # Мягкая миграция: добавим пустые turns в старые чаты,
            # чтобы новый код не упал на них (Шаг 1 Фазы 3).
            for c in CHATS.values():
                c.setdefault("turns", [])
                c.setdefault("messages", [])
    except Exception:
        CHATS = {}


def save_chats():
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(CHATS, f, ensure_ascii=False)
    except Exception:
        pass


def new_chat():
    cid = uuid.uuid4().hex[:12]
    # messages — старый формат для UI (роли user/bot, текст для показа)
    # turns — новый формат (Шаг 1 Фазы 3): честная история в OpenAI-стиле
    #         с tool_calls, чтобы модель видела свои прошлые вызовы инструментов
    CHATS[cid] = {"id": cid, "title": "Новый чат", "messages": [], "turns": [], "ts": time.time()}
    return cid


load_chats()

PAGE = """<!doctype html>
<html lang="ru" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polygraph</title>
<link rel="icon" type="image/x-icon" href="/favicon.ico?v=2">
<link rel="icon" type="image/png" href="/favicon.png?v=2">
<link rel="shortcut icon" href="/favicon.ico?v=2">
<style>
  :root {
    --accent:#22d3ee; --accent-2:#0891b2; --accent-soft:rgba(34,211,238,.12);
  }
  [data-theme="dark"] {
    --bg:#0b0d12; --bg2:#12151d; --bg3:#1a1e29; --panel:#10131a;
    --border:#242936; --text:#e6e8ee; --muted:#8b93a3;
    --bubble-user:#192232; --hover:#1b1f2a;
  }
  [data-theme="light"] {
    --bg:#ffffff; --bg2:#f7f8fa; --bg3:#eef0f4; --panel:#f7f8fa;
    --border:#e3e6ec; --text:#1a1d24; --muted:#6b7280; --bubble-user:#eef4ff; --hover:#f0f2f6;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:"Inter","SF Pro Text",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; letter-spacing:-.01em;
    background:var(--bg); color:var(--text); height:100vh; display:flex; overflow:hidden; transition:background .25s,color .25s; }

  /* Sidebar */
  #sidebar { width:268px; background:var(--bg2); border-right:1px solid var(--border); display:flex; flex-direction:column; transition:width .22s ease; flex-shrink:0; }
  #sidebar.collapsed { width:0; border:none; overflow:hidden; }
  .sb-top { padding:14px; }
  #newBtn { width:100%; background:linear-gradient(135deg,var(--accent),var(--accent-2)); border:none; color:#04222a; padding:11px; border-radius:11px; font-weight:700; cursor:pointer; font-size:14px; transition:transform .1s,filter .15s; }
  #newBtn:hover { filter:brightness(1.08); }
  #newBtn:active { transform:scale(.98); }
  #chatList { flex:1; overflow-y:auto; padding:4px 10px 12px; }
  .ci { display:flex; align-items:center; gap:6px; padding:10px 11px; border-radius:9px; cursor:pointer; font-size:13.5px; color:var(--text); margin-bottom:2px; transition:background .12s; }
  .ci:hover { background:var(--hover); }
  .ci.active { background:var(--accent-soft); }
  .ci .t { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ci .del { opacity:0; color:var(--muted); padding:2px 5px; border-radius:5px; font-size:12px; }
  .ci:hover .del { opacity:.7; }
  .ci .del:hover { opacity:1; background:rgba(255,80,80,.15); color:#ff6b6b; }
  .sb-foot { padding:12px 14px; border-top:1px solid var(--border); display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); }

  /* Main */
  #main { flex:1; display:flex; flex-direction:column; min-width:0; }
  header { padding:12px 16px; display:flex; align-items:center; gap:10px; border-bottom:1px solid var(--border); background:var(--bg); }
  .iconbtn { background:transparent; border:1px solid var(--border); color:var(--text); width:38px; height:38px; border-radius:10px; cursor:pointer; font-size:16px; display:flex; align-items:center; justify-content:center; transition:background .12s; }
  .iconbtn:hover { background:var(--hover); }
  .iconbtn svg { width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  /* === Переключатель темы "астро" — toggle-pill с двумя опциями === */
  .theme-toggle { display:inline-flex; align-items:center; background:var(--bg2); border:1px solid var(--border); border-radius:24px; padding:3px; cursor:pointer; height:38px; }
  .theme-toggle .opt { width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; transition:background .25s; }
  .theme-toggle .opt svg { width:16px; height:16px; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; transition:stroke .25s; }
  .theme-toggle .opt.active { background:linear-gradient(135deg, var(--accent), var(--accent-2)); }
  .theme-toggle .opt.active svg { stroke:#04222a; }
  .theme-toggle .opt:not(.active) svg { stroke:var(--muted); }
  .theme-toggle .opt:not(.active):hover svg { stroke:var(--text); }
  header h1 { font-size:16px; font-weight:600; display:flex; align-items:center; gap:8px; }
  header .logo { width:24px; height:24px; }
  header .spacer { flex:1; }
  select { background:var(--bg2); color:var(--text); border:1px solid var(--border); border-radius:9px; padding:8px 12px; font-size:13px; cursor:pointer; }
  /* ── Статус провайдеров (компактный + раскрывающийся) ── */
  .status { position:relative; display:inline-flex; align-items:center; gap:6px; font-size:12px;
            color:var(--muted); cursor:pointer; padding:5px 10px; border-radius:8px;
            user-select:none; transition:background .12s; }
  .status:hover { background:var(--hover); }
  .status .led { width:8px; height:8px; border-radius:50%; flex-shrink:0; position:relative; }
  .status .led.on { background:#34d399; box-shadow:0 0 6px #34d399; }
  .status .led.off { background:#ef4444; box-shadow:0 0 6px #ef4444; }
  .status .led.warn { background:#fbbf24; box-shadow:0 0 6px #fbbf24; }
  .status .led.wait { background:#fbbf24; }
  /* Пульсация на зелёной точке — "живой" индикатор */
  .status .led.on::after { content:""; position:absolute; inset:0; border-radius:50%;
            background:#34d399; opacity:.6; animation:pulse 2s ease-out infinite; }
  @keyframes pulse { 0%{ transform:scale(1); opacity:.6; } 100%{ transform:scale(2.4); opacity:0; } }
  .status .label { white-space:nowrap; }
  .status .caret { font-size:9px; opacity:.5; margin-left:2px; transition:transform .15s; }
  .status.open .caret { transform:rotate(180deg); }

  /* Выпадающая панель с детализацией по каждому провайдеру */
  .status-panel { position:absolute; top:calc(100% + 6px); left:0; min-width:220px; z-index:30;
            background:var(--bg2); border:1px solid var(--border); border-radius:12px;
            padding:6px; box-shadow:0 8px 24px rgba(0,0,0,.25);
            opacity:0; transform:translateY(-4px); pointer-events:none;
            transition:opacity .15s, transform .15s; }
  .status.open .status-panel { opacity:1; transform:translateY(0); pointer-events:auto; }
  .sp-row { display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:7px;
            font-size:13px; color:var(--text); }
  .sp-row:hover { background:var(--hover); }
  .sp-row .led { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
  .sp-row .led.on { background:#34d399; box-shadow:0 0 5px #34d399; }
  .sp-row .led.off { background:#ef4444; box-shadow:0 0 5px #ef4444; }
  .sp-row .name { flex:1; }
  .sp-row .reason { font-size:11px; color:var(--muted); }
  .sp-foot { padding:6px 8px; font-size:11px; color:var(--muted); border-top:1px solid var(--border);
            margin-top:4px; display:flex; align-items:center; justify-content:flex-end; }
  .sp-foot button { background:none; border:none; color:var(--accent); cursor:pointer;
            font-size:11px; padding:2px 6px; border-radius:5px; }
  .sp-foot button:hover { background:var(--hover); }

  #chat { flex:1; overflow-y:auto; }
  .wrap { max-width:760px; margin:0 auto; padding:24px 20px; }

  /* Welcome screen */
  #welcome { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:20px; }
  #welcome .biglogo { width:76px; height:76px; margin-bottom:22px; filter:drop-shadow(0 0 24px var(--accent-soft)); animation:float 3s ease-in-out infinite; }
  @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
  #welcome h2 { font-size:30px; font-weight:700; margin-bottom:10px; background:linear-gradient(135deg,var(--text),var(--accent)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  #welcome p { color:var(--muted); font-size:15px; margin-bottom:30px; max-width:440px; line-height:1.5; }
  .cards { display:grid; grid-template-columns:1fr 1fr; gap:12px; max-width:540px; width:100%; }
  .card { background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:15px 16px; text-align:left; cursor:pointer; transition:all .15s; }
  .card:hover { border-color:var(--accent); background:var(--bg3); transform:translateY(-2px); }
  .card .ico { width:28px; height:28px; margin-bottom:10px; display:block; }
  .card .ico svg { width:100%; height:100%; stroke-width:1.75; stroke-linecap:round; stroke-linejoin:round; }
  .card .ttl { font-weight:600; font-size:14px; margin-bottom:4px; }
  .card .sub { font-size:12.5px; color:var(--muted); }

  /* Messages - stil Claude/ChatGPT */
  .msg { margin:18px 0; display:flex; flex-direction:column; animation:fade .3s ease; }
  @keyframes fade { from{opacity:0; transform:translateY(6px)} to{opacity:1; transform:none} }
  .msg.user { align-items:flex-end; }
  .msg.bot { align-items:flex-start; }
  .msg .body { line-height:1.55; white-space:pre-wrap; word-wrap:break-word; font-size:15px; max-width:100%; }
  /* puzyr usera sprava */
  .msg.user .body { background:var(--bg3); padding:11px 16px; border-radius:18px; max-width:78%; }
  /* otvet agenta - bez puzyrya */
  .msg.bot .body { padding:0; }
  .msg .tag { font-size:11px; color:var(--muted); margin-bottom:5px; display:flex; align-items:center; gap:6px; }
  .msg .tag .botico { width:18px; height:18px; border-radius:5px; }
  /* === Таблицы в стиле Linear: бирюзовая шапка с яркой линией снизу === */
  .msg .body .tablewrap { overflow-x:auto; margin:12px 0; }
  .msg .body table { border-collapse:collapse; font-size:14px; width:auto; min-width:0; }
  .msg .body thead { border-bottom:1px solid var(--accent); }
  .msg .body th { padding:8px 14px 12px 0; font-weight:600; text-align:left; white-space:nowrap;
                  color:var(--accent); background:transparent; }
  .msg .body td { padding:11px 14px 11px 0; vertical-align:top; line-height:1.5; color:var(--text);
                  border-bottom:1px solid var(--border); }
  /* Последняя колонка — без правого padding */
  .msg .body th:last-child, .msg .body td:last-child { padding-right:0; }
  /* Убираем нижнюю границу у последней строки */
  .msg .body tbody tr:last-child td { border-bottom:none; }
  /* === Заголовки в стиле ChatGPT/Claude: белые/тёмные, без цвета акцента, иерархия по размеру === */
  .msg .body h3 { font-size:18px; font-weight:700; margin:16px 0 6px; color:var(--text); letter-spacing:-.01em; line-height:1.3; }
  .msg .body h3:first-child { margin-top:0; }
  .msg .body h4 { font-size:16px; font-weight:600; margin:12px 0 4px; color:var(--text); letter-spacing:-.005em; line-height:1.35; }
  .msg .body h4:first-child { margin-top:0; }
  .msg .body i, .msg .body em { font-style:italic; color:var(--text); }
  /* === Цитаты "> текст" — вертикальная полоска слева, как в Notion/Linear === */
  .msg .body blockquote { margin:10px 0; padding:6px 0 6px 14px; border-left:3px solid var(--accent);
                          color:var(--muted); font-style:normal; }
  .msg .body blockquote > * { margin:0; }
  .msg .body ul { margin:4px 0 8px 4px; padding-left:18px; }
  .msg .body ol { margin:4px 0 8px 4px; padding-left:22px; }
  .msg .body li { margin:3px 0; }
  /* === HR: убран совсем. Разделы разделяются заголовками и воздухом === */
  .msg .body hr { display:none; }
  .msg .body a { color:var(--accent); }
  .msg .body code { background:var(--bg3); padding:1px 6px; border-radius:5px; font-size:13px; }
  /* knopki deystviy pod soobsheniem */
  .acts { display:flex; gap:2px; margin-top:6px; opacity:0; transition:opacity .15s; }
  .msg:hover .acts { opacity:1; }
  .acts button { background:transparent; border:none; color:var(--muted); width:30px; height:30px; border-radius:7px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all .12s; }
  .acts button:hover { background:var(--hover); color:var(--text); }
  .acts button svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  .acts .done { color:#34d399; }
  /* sgenerirovannye kartinki */
  .genimgs { display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }
  .genimg { position:relative; max-width:340px; }
  .genimg img { width:100%; border-radius:14px; display:block; border:1px solid var(--border); }
  .genimg .dl { position:absolute; top:8px; right:8px; width:34px; height:34px; border-radius:9px; background:rgba(0,0,0,.55); display:flex; align-items:center; justify-content:center; opacity:0; transition:opacity .15s; }
  .genimg:hover .dl { opacity:1; }
  .genimg .dl svg { width:18px; height:18px; fill:none; stroke:#fff; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  .typing { color:var(--muted); font-style:italic; }
  /* Brendovyy indikator "dumaet" - kristall s molniyami (plavnyy, medlennyy) */
  .thinker { display:inline-flex; align-items:center; padding:4px 0; }
  .thinker svg { width:34px; height:34px; }
  .thinker .ring { stroke:var(--accent); stroke-width:2; fill:none; stroke-dasharray:18 120; stroke-linecap:round;
        filter:drop-shadow(0 0 5px var(--accent)); animation:trace 2.6s linear infinite; }
  .thinker .core { fill:var(--accent); filter:drop-shadow(0 0 6px var(--accent)); transform-origin:center;
        animation:corepulse 2.6s ease-in-out infinite; }
  @keyframes trace { to { stroke-dashoffset:-138; } }
  @keyframes corepulse { 0%,100%{ opacity:.4; transform:scale(.65); } 50%{ opacity:1; transform:scale(1); } }

  /* Input */
  footer { padding:12px 0 18px; background:var(--bg); }
  .inbox { max-width:760px; margin:0 auto; padding:0 20px; }
  .inrow { display:flex; gap:8px; align-items:flex-end; background:var(--bg2); border:1px solid var(--border); border-radius:18px; padding:8px 8px 8px 8px; transition:border-color .15s; }
  .inrow:focus-within { border-color:var(--accent); }
  #inp { flex:1; background:transparent; color:var(--text); border:none; padding:8px 4px; font-size:15px; resize:none; max-height:180px; font-family:inherit; line-height:1.5; align-self:center; }
  #inp:focus { outline:none; }
  #send { background:linear-gradient(135deg,var(--accent),var(--accent-2)); border:none; width:40px; height:40px; border-radius:11px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; transition:filter .15s; }
  #send:hover { filter:brightness(1.1); }
  #send:disabled { opacity:.5; cursor:not-allowed; }
  #send svg { width:20px; height:20px; fill:#04222a; }
  .hint { text-align:center; font-size:11.5px; color:var(--muted); margin-top:9px; }
  /* knopka prikrepit */
  /* Кнопка "прикрепить": бирюзовый +, без обводки, hover-фон */
  .attach { background:transparent; border:none; color:var(--accent); width:34px; height:34px; border-radius:50%; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; transition:all .15s; }
  .attach:hover { background:var(--accent-soft); }
  .attach svg { width:22px; height:22px; fill:none; stroke:currentColor; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
  /* preview prikreplyonnyh faylov */
  #attachRow { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px; }
  .chip { display:inline-flex; align-items:center; gap:8px; background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:6px 10px; font-size:13px; }
  .chip img { width:34px; height:34px; object-fit:cover; border-radius:6px; }
  .chip .x { cursor:pointer; color:var(--muted); padding:0 2px; }
  .chip .x:hover { color:#ff6b6b; }
  /* drag&drop overlay */
  #dropOverlay { display:none; position:fixed; inset:0; z-index:50; background:rgba(0,0,0,.55); align-items:center; justify-content:center; }
  #dropOverlay.show { display:flex; }
  #dropOverlay .dropbox { border:2px dashed var(--accent); border-radius:20px; padding:50px 70px; font-size:20px; color:#fff; background:var(--accent-soft); }
</style>
</head>
<body>

<aside id="sidebar">
  <div class="sb-top">
    <button id="newBtn" onclick="newChat()">＋ Новый чат</button>
  </div>
  <div id="chatList"></div>
  <div class="sb-foot">
    <span class="dot" style="width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399"></span>
    Polygraph · локально
  </div>
</aside>

<div id="main">
  <header>
    <button class="iconbtn" onclick="toggleSidebar()" title="Свернуть/показать панель чатов">
      <svg viewBox="0 0 24 24" stroke="currentColor"><rect x="3" y="4" width="18" height="16" rx="2" fill="var(--accent)"/><line x1="9" y1="4" x2="9" y2="20" stroke="#04222a"/></svg>
    </button>
    <h1><img class="logo" src="/favicon.ico" alt=""> Polygraph</h1>
    <div id="status" class="status" title="Статус провайдеров — клик чтобы раскрыть" onclick="toggleStatus()">
      <span class="led wait"></span>
      <span class="label">проверяю…</span>
      <span class="caret">▾</span>
      <div class="status-panel" onclick="event.stopPropagation()">
        <div id="statusRows"></div>
        <div class="sp-foot">
          <button onclick="checkStatus(true)">↻ Обновить</button>
        </div>
      </div>
    </div>
    <span class="spacer"></span>
    <select id="model" title="Модель">
      <option value="auto">Авто</option>
      <option value="gpt-oss">gpt-oss (умная)</option>
      <option value="gemini">Gemini</option>
      <option value="llama">Llama 70B</option>
      <option value="fast">Быстрая</option>
    </select>
    <div class="theme-toggle" id="themeToggle" onclick="toggleTheme()" title="Сменить тему">
      <div class="opt" data-theme-opt="dark"><svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></div>
      <div class="opt" data-theme-opt="light"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/><line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg></div>
    </div>
  </header>

  <!-- Приветственный экран -->
  <div id="welcome">
    <img class="biglogo" src="/favicon.ico" alt="">
    <h2>Чем могу помочь?</h2>
    <p>Я Polygraph — умный ассистент. Ищу в интернете, читаю сайты, пишу код, считаю и работаю с файлами.</p>
    <div class="cards">
      <div class="card" onclick="quick('Найди и сделай вывод: что нового в мире AI на этой неделе')">
        <span class="ico"><svg viewBox="0 0 24 24" stroke="var(--accent)"><circle cx="11" cy="11" r="8" fill="var(--accent-soft)"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span>
        <div class="ttl">Исследование</div>
        <div class="sub">Найти в интернете и сделать вывод</div>
      </div>
      <div class="card" onclick="quick('Помоги написать тёплое поздравление коллеге с днём рождения')">
        <span class="ico"><svg viewBox="0 0 24 24" stroke="var(--accent)"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" fill="var(--accent-soft)"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" fill="var(--accent)" stroke="var(--accent)"/></svg></span>
        <div class="ttl">Текст</div>
        <div class="sub">Написать письмо, пост, поздравление</div>
      </div>
      <div class="card" onclick="quick('Объясни простыми словами, как работает нейросеть')">
        <span class="ico"><svg viewBox="0 0 24 24" stroke="var(--accent)"><path d="M12 2a7 7 0 0 0-4 12.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26A7 7 0 0 0 12 2z" fill="var(--accent-soft)"/><line x1="9" y1="21" x2="15" y2="21" stroke-width="2"/></svg></span>
        <div class="ttl">Объяснение</div>
        <div class="sub">Разобрать сложную тему просто</div>
      </div>
      <div class="card" onclick="quick('Напиши на Python функцию, которая проверяет, палиндром ли строка')">
        <span class="ico"><svg viewBox="0 0 24 24" stroke="var(--accent)"><rect x="2" y="4" width="20" height="16" rx="3" fill="var(--accent-soft)"/><polyline points="16 14 19 11 16 8" fill="none"/><polyline points="8 8 5 11 8 14" fill="none"/></svg></span>
        <div class="ttl">Код</div>
        <div class="sub">Написать и проверить программу</div>
      </div>
    </div>
  </div>

  <!-- Окно чата (скрыто до первого сообщения) -->
  <div id="chat" style="display:none"><div class="wrap" id="wrap"></div></div>

  <footer>
    <div class="inbox">
      <div id="attachRow"></div>
      <div class="inrow">
        <button id="attachBtn" class="attach" onclick="document.getElementById('fileInp').click()" title="Прикрепить файл">
          <svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
        <input type="file" id="fileInp" multiple style="display:none" onchange="handleFiles(this.files)">
        <textarea id="inp" rows="1" placeholder="Спроси что угодно..."></textarea>
        <button id="send" onclick="sendMsg()" title="Отправить">
          <svg viewBox="0 0 24 24"><path d="M3 11l18-8-8 18-2-7-8-3z"/></svg>
        </button>
      </div>
      <div class="hint">Ответы могут содержать ошибки — проверяй важные данные. Для Groq нужен VPN.</div>
    </div>
  </footer>
  <div id="dropOverlay"><div class="dropbox">📎 Отпусти файл, чтобы прикрепить</div></div>
</div>

<script>
const wrap = document.getElementById('wrap');
const inp  = document.getElementById('inp');
const send = document.getElementById('send');
const chatBox = document.getElementById('chat');
const welcome = document.getElementById('welcome');
let currentChat = null;

function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmt(s){
  s = esc(s);
  // <br> -> временный маркер (НЕ перенос строки, чтобы не ломать строки таблиц)
  s = s.replace(/&lt;br[^&]*&gt;/gi, '@@BR@@');
  // Заголовки: # / ## → крупный <h3>, ### и глубже → <h4>
  s = s.replace(/^[ \t]*(#{1,6})[ \t]+(.+)$/gm, function(m, hashes, t){
    const tag = hashes.length <= 2 ? 'h3' : 'h4';
    return '<'+tag+'>'+t.trim()+'</'+tag+'>';
  });
  s = s.replace(/^[ \t]*-{3,}[ \t]*$/gm, '<hr>');
  // Цитаты "> текст" — одна строка = одна цитата (для многострочных Mistral сам формирует
  // подряд несколько > строк, мы их склеиваем ниже на этапе обработки строк).
  s = s.replace(/^[ \t]*&gt;[ \t]?(.+)$/gm, '@@BQ@@$1');
  // Жирный **текст** — обрабатываем ПЕРВЫМ (двойные звёздочки)
  s = s.replace(/[*][*](.+?)[*][*]/g,'<b>$1</b>');
  // Курсив *текст* — одиночные звёздочки.
  // Требуем, чтобы СЛЕВА и СПРАВА от звёздочек НЕ было цифр (иначе ломаем математику 2*3*4).
  // И внутри нет пробелов сразу после открывающей или перед закрывающей.
  s = s.replace(/(^|[^*0-9])[*]([^* \t0-9][^*]*?[^* \t]|[^* \t0-9])[*](?=[^*0-9]|$)/g, '$1<i>$2</i>');
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/(https?:[^ )<]+)/g,'<a href="$1" target="_blank">$1</a>');

  const NL = String.fromCharCode(10);
  const lines = s.split(NL);
  let out = [], i = 0;
  while(i < lines.length){
    if(/^[ \t]*[|].*[|][ \t]*$/.test(lines[i])){
      let tbl = [];
      while(i < lines.length && /^[ \t]*[|].*[|][ \t]*$/.test(lines[i])){ tbl.push(lines[i]); i++; }
      out.push(renderTable(tbl));
    } else { out.push(lines[i]); i++; }
  }
  s = out.join(NL);

  // Списки: построчно (маркированные - * и нумерованные 1. 2.)
  {
    const ls = s.split(NL);
    let res = [], buf = [], bufType = null;
    const flush = function(){
      if(buf.length){
        const tag = bufType === 'ol' ? 'ol' : 'ul';
        res.push('<'+tag+'>'+buf.map(function(x){return '<li>'+x+'</li>';}).join('')+'</'+tag+'>');
        buf=[]; bufType=null;
      }
    };
    for(let k=0;k<ls.length;k++){
      const bullet = ls[k].match(/^[ \t]*[-*][ \t]+(.+)$/);
      const numbered = ls[k].match(/^[ \t]*[0-9]+[.)][ \t]+(.+)$/);
      if(bullet){ if(bufType==='ol') flush(); bufType='ul'; buf.push(bullet[1]); }
      else if(numbered){ if(bufType==='ul') flush(); bufType='ol'; buf.push(numbered[1]); }
      else { flush(); res.push(ls[k]); }
    }
    flush();
    s = res.join(NL);
  }

  // оставшиеся маркеры @@BR@@ -> настоящий перенос строки
  s = s.split('@@BR@@').join('<br>');
  // Цитаты: склеиваем подряд идущие @@BQ@@-строки в один <blockquote>
  {
    const ls = s.split(NL);
    let res = [], bq = [];
    const flushBq = function(){
      if(bq.length){
        res.push('<blockquote>' + bq.join('<br>') + '</blockquote>');
        bq = [];
      }
    };
    for(let k=0; k<ls.length; k++){
      if(ls[k].indexOf('@@BQ@@') === 0){
        bq.push(ls[k].substring(6));  // убираем маркер
      } else {
        flushBq();
        res.push(ls[k]);
      }
    }
    flushBq();
    s = res.join(NL);
  }
  return s;
}
function renderTable(rows){
  const parse = function(r){ return r.trim().replace(/^[|]|[|]$/g,'').split('|').map(function(cc){ return cc.trim().split('@@BR@@').join('<br>'); }); };
  let bodyRows = rows.map(parse);
  let header = null;
  if(bodyRows.length >= 2 && bodyRows[1].every(function(cc){ return /^:?-{2,}:?$/.test(cc); })){
    header = bodyRows[0];
    bodyRows = bodyRows.slice(2);
  }
  let html = '<div class="tablewrap"><table>';
  if(header){ html += '<thead><tr>'+header.map(function(cc){ return '<th>'+cc+'</th>'; }).join('')+'</tr></thead>'; }
  html += '<tbody>'+bodyRows.map(function(r){ return '<tr>'+r.map(function(cc){ return '<td>'+cc+'</td>'; }).join('')+'</tr>'; }).join('')+'</tbody>';
  html += '</table></div>';
  return html;
}

function showChat(){ welcome.style.display='none'; chatBox.style.display='block'; }
function showWelcome(){ welcome.style.display='flex'; chatBox.style.display='none'; wrap.innerHTML=''; }

// SVG-ikonki deystviy
const ICO = {
  copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  retry:'<svg viewBox="0 0 24 24"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.8-3.4L23 10M1 14l4.7 4.4A9 9 0 0 0 20.5 15"/></svg>',
  check:'<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>',
  download:'<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>'
};

function copyText(btn, text){
  navigator.clipboard.writeText(text).then(()=>{
    const old = btn.innerHTML; btn.innerHTML = ICO.check; btn.classList.add('done');
    setTimeout(()=>{ btn.innerHTML = old; btn.classList.remove('done'); }, 1200);
  });
}

function addMsg(text, who, tag, images){
  showChat();
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  // tag (tolko u bota: ikonka + model)
  let head = '';
  if(who === 'bot'){
    head = `<div class="tag"><img class="botico" src="/favicon.ico" alt="">${tag?esc(tag):'Polygraph'}</div>`;
  }
  const bodyHtml = who==='bot' ? fmt(text) : esc(text);
  // сгенерированные картинки
  let imgsHtml = '';
  if(images && images.length){
    imgsHtml = '<div class="genimgs">' + images.map(u =>
      `<div class="genimg"><img src="${u}" alt=""><a class="dl" href="${u}" download title="Скачать">${ICO.download}</a></div>`
    ).join('') + '</div>';
  }
  // knopki deystviy
  let acts = '';
  if(who === 'user'){
    acts = '<div class="acts"><button title="Копировать" data-act="copy">'+ICO.copy+'</button>'
         + '<button title="Редактировать" data-act="edit">'+ICO.edit+'</button></div>';
  } else if(text && text !== '…'){
    acts = '<div class="acts"><button title="Копировать" data-act="copy">'+ICO.copy+'</button>'
         + '<button title="Повторить" data-act="retry">'+ICO.retry+'</button></div>';
  }
  d.innerHTML = `${head}<div class="body">${bodyHtml}${imgsHtml}</div>${acts}`;
  // privyazka deystviy
  const copyBtn = d.querySelector('[data-act="copy"]');
  if(copyBtn) copyBtn.onclick = ()=> copyText(copyBtn, text);
  const editBtn = d.querySelector('[data-act="edit"]');
  if(editBtn) editBtn.onclick = ()=>{ inp.value = text; inp.focus(); inp.dispatchEvent(new Event('input')); };
  const retryBtn = d.querySelector('[data-act="retry"]');
  if(retryBtn) retryBtn.onclick = ()=> retryLast();
  wrap.appendChild(d);
  chatBox.scrollTop = 1e9;
  return d;
}

let _lastUserMsg = '';
function retryLast(){ if(_lastUserMsg){ inp.value = _lastUserMsg; sendMsg(); } }

function toggleSidebar(){ document.getElementById('sidebar').classList.toggle('collapsed'); }

// Переключатель темы "астро" — подсвечивает активную опцию (луну или солнце)
function _setThemeActive(theme){
  const tg = document.getElementById('themeToggle');
  if(!tg) return;
  tg.querySelectorAll('.opt').forEach(o => {
    o.classList.toggle('active', o.getAttribute('data-theme-opt') === theme);
  });
}
function toggleTheme(){
  const html = document.documentElement;
  const next = html.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  _setThemeActive(next);
  localStorage.setItem('pg_theme', next);
}
(function(){
  const t = localStorage.getItem('pg_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
  _setThemeActive(t);
})();

function quick(text){ inp.value=text; sendMsg(); }

// ── Статус провайдеров: компактный значок + раскрывающаяся панель ──
let _statusData = null;       // последний результат /api/status
let _statusTimer = null;      // авто-обновление каждые 60 сек

// Tooltip-подсказки по причинам падения провайдера
const REASON_HINTS = {
  'VPN?': 'попробуй включить VPN — провайдер блокирует РФ',
  'лимит': 'дневной лимит исчерпан, сбросится через ~24 ч',
  'нет ключа': 'добавь ключ в .env и перезапусти',
  'ошибка': 'провайдер вернул неизвестную ошибку',
};

function toggleStatus(){
  const el = document.getElementById('status');
  el.classList.toggle('open');
  // Закрытие при клике вне панели
  if(el.classList.contains('open')){
    setTimeout(()=>{
      document.addEventListener('click', _closeStatusOnce, {once:true});
    }, 0);
  }
}
function _closeStatusOnce(e){
  const el = document.getElementById('status');
  if(el && !el.contains(e.target)) el.classList.remove('open');
}

function _renderStatusCompact(data){
  // Решаем, что показать «снаружи»: если есть проблемные — то проблемного,
  // иначе общий «все N онлайн».
  const total = data.providers.length;
  const broken = data.providers.filter(p => !p.ok);
  const led = document.querySelector('#status > .led');
  const label = document.querySelector('#status > .label');
  if(broken.length === 0){
    led.className = 'led on';
    label.textContent = total === 1 ? '1 провайдер онлайн' : `Все ${total} онлайн`;
  } else if(broken.length === total){
    led.className = 'led off';
    label.textContent = 'Все упали';
  } else {
    // Часть провайдеров упала — показываем виновника
    led.className = 'led warn';
    const first = broken[0];
    label.textContent = `${first.name}: ${first.reason || 'упал'}`;
  }
}

function _renderStatusPanel(data){
  const rows = document.getElementById('statusRows');
  rows.innerHTML = data.providers.map(p => {
    const reason = p.reason || '';
    const hint = REASON_HINTS[reason] || '';
    const reasonHtml = p.ok ? '' :
      `<span class="reason" title="${esc(hint)}">${esc(reason)}</span>`;
    return `<div class="sp-row" title="${esc(hint)}">
              <span class="led ${p.ok?'on':'off'}"></span>
              <span class="name">${esc(p.name)}</span>
              ${reasonHtml}
            </div>`;
  }).join('');
}

async function checkStatus(forceShowWait){
  const led = document.querySelector('#status > .led');
  const label = document.querySelector('#status > .label');
  // Показываем "проверяю..." только при первом запуске или ручном refresh —
  // фоновое авто-обновление делаем тихо, чтобы не моргало.
  if(forceShowWait || !_statusData){
    led.className = 'led wait';
    label.textContent = 'проверяю…';
  }
  try{
    const r = await fetch('/api/status');
    const d = await r.json();
    _statusData = d;
    _renderStatusCompact(d);
    _renderStatusPanel(d);
  }catch(e){
    led.className = 'led off';
    label.textContent = 'нет связи';
  }
}

// Авто-обновление каждые 60 сек (тихо, без "проверяю...")
function _startStatusTimer(){
  if(_statusTimer) clearInterval(_statusTimer);
  _statusTimer = setInterval(()=>{ checkStatus(false); }, 60000);
}

async function loadChats(){
  const r = await fetch('/api/chats'); const d = await r.json();
  const list = document.getElementById('chatList');
  list.innerHTML = '';
  if(!d.chats.length){ list.innerHTML='<div style="padding:10px 16px;color:var(--muted);font-size:12px">Пока нет чатов</div>'; return; }
  d.chats.forEach(c=>{
    const el = document.createElement('div');
    el.className = 'ci' + (c.id===currentChat ? ' active' : '');
    el.innerHTML = `<span class="t">${esc(c.title)}</span><span class="del" title="Удалить">🗑</span>`;
    el.querySelector('.t').onclick = ()=> openChat(c.id);
    el.querySelector('.del').onclick = (e)=>{ e.stopPropagation(); delChat(c.id); };
    list.appendChild(el);
  });
}

async function openChat(id){
  currentChat = id;
  const r = await fetch('/api/chat/'+id); const c = await r.json();
  if(!c.messages || !c.messages.length){ showWelcome(); }
  else { wrap.innerHTML=''; showChat(); c.messages.forEach(m=> addMsg(m.text, m.role, m.role==='bot'?(m.model||''):'', m.images)); }
  loadChats();
}

async function newChat(){
  const r = await fetch('/api/new',{method:'POST'}); const d = await r.json();
  currentChat = d.id;
  showWelcome();
  loadChats();
  inp.focus();
}

async function delChat(id){
  if(!confirm('Удалить этот чат?')) return;
  await fetch('/api/delete/'+id,{method:'POST'});
  if(currentChat===id){ currentChat=null; showWelcome(); }
  loadChats();
}

// ── Прикреплённые файлы ──
let _attached = [];  // [{name, path, kind}]

async function handleFiles(fileList){
  for(const f of fileList){
    const fd = new FormData(); fd.append('file', f);
    try{
      const r = await fetch('/api/upload', {method:'POST', body:fd});
      const d = await r.json();
      if(d.ok){ _attached.push(d); renderAttached(); }
      else alert('Не удалось загрузить: '+(d.error||''));
    }catch(e){ alert('Ошибка загрузки: '+e); }
  }
  document.getElementById('fileInp').value = '';
}

function renderAttached(){
  const row = document.getElementById('attachRow');
  row.innerHTML = _attached.map((f,i)=>{
    const thumb = f.kind==='image' ? `<img src="/agent_files/${f.path}" alt="">` : '📄';
    return `<span class="chip">${thumb}<span>${esc(f.name)}</span><span class="x" onclick="removeAttached(${i})">✕</span></span>`;
  }).join('');
}
function removeAttached(i){ _attached.splice(i,1); renderAttached(); }

// drag & drop по всему окну
const overlay = document.getElementById('dropOverlay');
let _dragCnt = 0;
window.addEventListener('dragenter', e=>{ e.preventDefault(); _dragCnt++; overlay.classList.add('show'); });
window.addEventListener('dragover', e=>{ e.preventDefault(); });
window.addEventListener('dragleave', e=>{ e.preventDefault(); _dragCnt--; if(_dragCnt<=0) overlay.classList.remove('show'); });
window.addEventListener('drop', e=>{ e.preventDefault(); _dragCnt=0; overlay.classList.remove('show'); if(e.dataTransfer.files.length) handleFiles(e.dataTransfer.files); });

async function sendMsg(){
  const text = inp.value.trim();
  if(!text && !_attached.length) return;
  const filesToSend = _attached.slice();
  const dispText = text + (filesToSend.length ? '  📎 ' + filesToSend.map(f=>f.name).join(', ') : '');
  inp.value=''; inp.style.height='auto';
  _attached = []; renderAttached();
  addMsg(dispText || '📎 (файл)', 'user');
  _lastUserMsg = text;
  send.disabled = true;
  const thinking = addMsg('','bot');
  thinking.classList.add('thinking');
  thinking.querySelector('.body').innerHTML = '<span class="thinker"><svg viewBox="0 0 40 40"><polygon class="ring" points="20,3 35,11.5 35,28.5 20,37 5,28.5 5,11.5"/><circle class="core" cx="20" cy="20" r="4"/></svg></span>';
  try{
    const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:text, model:document.getElementById('model').value, chat_id:currentChat, files:filesToSend})});
    const data = await r.json();
    thinking.remove();
    addMsg(data.answer || '[пустой ответ]', 'bot', data.model || '', data.images);
    currentChat = data.chat_id || currentChat;
    loadChats();
  }catch(e){
    thinking.remove();
    addMsg('Ошибка соединения: '+e,'bot');
  }
  send.disabled = false;
  inp.focus();
}

inp.addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); sendMsg(); } });
inp.addEventListener('input', ()=>{ inp.style.height='auto'; inp.style.height=Math.min(inp.scrollHeight,180)+'px'; });

showWelcome();
loadChats();
checkStatus();
_startStatusTimer();  // авто-обновление статуса каждые 60 сек
inp.focus();

// ── Авто-выключение сервера при закрытии вкладки ──
// При загрузке отменяем возможное запланированное выключение (если это был F5)
fetch('/api/stay', {method:'POST'}).catch(()=>{});
// При закрытии вкладки шлём "bye" (sendBeacon работает даже при закрытии)
window.addEventListener('pagehide', ()=>{
  try { navigator.sendBeacon('/api/bye'); } catch(e){}
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


# ── Авто-выключение при закрытии вкладки ──
import threading as _thr

_shutdown_timer = None

def _do_shutdown():
    """Останавливаем сервер, если за время ожидания никто не вернулся."""
    os._exit(0)  # жёстко завершаем процесс (и reloader тоже)

@app.route("/api/bye", methods=["POST"])
def api_bye():
    """Вкладка закрывается. Запускаем отложенное выключение (отменяемое)."""
    global _shutdown_timer
    if _shutdown_timer:
        _shutdown_timer.cancel()
    # Ждём 3 сек: если это был F5/переоткрытие — /api/stay отменит выключение
    _shutdown_timer = _thr.Timer(3.0, _do_shutdown)
    _shutdown_timer.daemon = True
    _shutdown_timer.start()
    return Response("", status=204)

@app.route("/api/stay", methods=["POST"])
def api_stay():
    """Страница (снова) активна — отменяем запланированное выключение."""
    global _shutdown_timer
    if _shutdown_timer:
        _shutdown_timer.cancel()
        _shutdown_timer = None
    return Response("", status=204)


_ICON_CACHE: dict[str, tuple[bytes, str]] = {}  # name -> (bytes, mime)

def _send_icon(prefer_png=False):
    names = ("polygraph_icon.png", "polygraph.ico") if prefer_png else ("polygraph.ico", "polygraph_icon.png")
    for name in names:
        # Кэш: читаем файл с диска один раз за процесс
        if name not in _ICON_CACHE:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            if not os.path.exists(path):
                _ICON_CACHE[name] = (b"", "")  # запомним, что файла нет
                continue
            mime = "image/x-icon" if name.endswith(".ico") else "image/png"
            with open(path, "rb") as f:
                _ICON_CACHE[name] = (f.read(), mime)
        data, mime = _ICON_CACHE[name]
        if data:
            resp = Response(data, mimetype=mime)
            resp.headers["Cache-Control"] = "public, max-age=3600"  # пусть браузер кэширует час
            return resp
    return Response("", status=404)


@app.route("/favicon.ico")
def favicon():
    return _send_icon(prefer_png=False)


@app.route("/favicon.png")
def favicon_png():
    return _send_icon(prefer_png=True)


def _chat_list():
    """Список чатов для боковой панели (новые сверху)."""
    items = sorted(CHATS.values(), key=lambda c: c.get("ts", 0), reverse=True)
    return [{"id": c["id"], "title": c["title"], "ts": c.get("ts", 0)} for c in items]


@app.route("/api/chats")
def api_chats():
    return jsonify({"chats": _chat_list()})


@app.route("/api/status")
def api_status():
    """Проверка, какие провайдеры реально отвечают (живой пинг).
    Показываем только провайдеров, у которых есть ключ — чтобы индикатор
    не захламлялся бесполезными «нет ключа» (cerebras/cohere для большинства)."""
    import concurrent.futures as _cf
    # Все провайдеры, которые есть в проекте. Порядок = слева направо в UI.
    all_checks = [
        ("mistral", "mistral-l", "Mistral"),
        ("github", "gh-gpt5-mini", "GitHub"),
        ("groq", "groq-8b", "Groq (VPN)"),
        ("google", "gemini", "Google"),
        ("openrouter", "grok", "OpenRouter"),
        ("cloudflare", "cf-oss20", "Cloudflare"),
        ("cohere", "cohere", "Cohere"),
        ("cerebras", "cerebras", "Cerebras"),
    ]
    # Фильтруем — пингуем только тех, у кого реально есть ключ.
    # Так в индикаторе не висят «нет ключа» от провайдеров, которые юзер не подключал.
    checks = [c for c in all_checks if pg.providers.get(c[0]) and pg.providers[c[0]].ok]

    def ping(item):
        pname, mkey, label = item
        prov = pg.providers.get(pname)
        from core import MODELS
        spec = MODELS.get(mkey)
        try:
            r = prov.call(spec.model_id, "", "ok", 0.0, 5)
            return {"name": label, "ok": bool(r and not str(r).startswith("[!"))}
        except Exception as e:
            msg = str(e)
            reason = "VPN?" if ("Forbidden" in msg or "403" in msg) else ("лимит" if "429" in msg else "ошибка")
            return {"name": label, "ok": False, "reason": reason}

    if not checks:
        return jsonify({"providers": [{"name": "нет ключей", "ok": False, "reason": ".env пуст"}]})

    with _cf.ThreadPoolExecutor(max_workers=min(len(checks), 6)) as ex:
        results = list(ex.map(ping, checks))
    return jsonify({"providers": results})


@app.route("/api/chat/<cid>")
def api_get_chat(cid):
    c = CHATS.get(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify(c)


@app.route("/api/new", methods=["POST"])
def api_new():
    cid = new_chat()
    agent.session_model = None  # новый чат — заново выбираем модель
    save_chats()
    return jsonify({"id": cid, "chats": _chat_list()})


@app.route("/api/delete/<cid>", methods=["POST"])
def api_delete(cid):
    CHATS.pop(cid, None)
    save_chats()
    return jsonify({"chats": _chat_list()})


@app.route("/agent_files/<path:subpath>")
def serve_agent_file(subpath):
    """Отдаёт файлы из agent_files (для превью загруженных картинок)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_files")
    full = os.path.abspath(os.path.join(base, subpath))
    if not full.startswith(os.path.abspath(base)) or not os.path.exists(full):
        return Response("", status=404)
    ext = os.path.splitext(full)[1].lower()
    mimes = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
             ".webp":"image/webp",".gif":"image/gif",".bmp":"image/bmp"}
    with open(full, "rb") as f:
        return Response(f.read(), mimetype=mimes.get(ext, "application/octet-stream"))


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Загрузка файла в рабочую папку агента (agent_files/uploads/)."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "нет файла"}), 400

    # Безопасное имя файла
    name = os.path.basename(f.filename)
    name = re.sub(r"[^\w.\-() ]", "_", name)[:120] or "file"

    updir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_files", "uploads")
    os.makedirs(updir, exist_ok=True)
    # Избегаем перезаписи: если есть — добавим число
    path = os.path.join(updir, name)
    base, ext = os.path.splitext(name)
    i = 1
    while os.path.exists(path):
        name = f"{base}_{i}{ext}"
        path = os.path.join(updir, name)
        i += 1
    f.save(path)

    # Относительный путь для инструментов (от agent_files)
    rel = os.path.join("uploads", name).replace("\\", "/")
    ext_low = ext.lower()
    is_image = ext_low in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
    return jsonify({"ok": True, "name": name, "path": rel,
                    "kind": "image" if is_image else "file"})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    user = (data.get("message") or "").strip()
    model = data.get("model", "auto")
    cid = data.get("chat_id")
    files = data.get("files") or []  # список {name, path, kind}

    if not user and not files:
        return jsonify({"answer": "Пустое сообщение.", "model": ""})

    # Прикреплённые файлы — добавляем инструкцию агенту
    file_note = ""
    if files:
        names = ", ".join(f.get("name", "") for f in files)
        img = [f for f in files if f.get("kind") == "image"]
        docs = [f for f in files if f.get("kind") != "image"]
        parts = []
        for f in img:
            parts.append(f"[Прикреплено ИЗОБРАЖЕНИЕ: {f['path']} — посмотри его через analyze_image с image='{f['path']}']")
        for f in docs:
            parts.append(f"[Прикреплён ФАЙЛ: {f['path']} — прочитай через read_file с path='{f['path']}']")
        file_note = "\n\n" + "\n".join(parts)
        if not user:
            user = "Посмотри прикреплённый файл и опиши/проанализируй его."

    user_full = user + file_note

    # Если в этом сообщении файла нет, но пользователь ЯВНО ссылается на ранее
    # присланный файл/картинку — подставим путь. Срабатывает только при отсылке,
    # чтобы не мешать обычным запросам («найди X», «что в оферте»).
    refers_to_file = bool(re.search(
        r'(?i)(эт(от|у|о|и)|её|ее|неё|нее|нём|нем|ней|картинк|изображени|фото|снимок|'
        r'скрин|слайд|файл|документ|выше|присл|тут|здесь|на нём|поправ|доработ|измен)', user))
    if not files and cid in CHATS and refers_to_file:
        recent_msgs = CHATS[cid]["messages"][-6:]  # последние ~3 пары
        last_file = None
        for m in reversed(recent_msgs):
            mf = m.get("files") or []
            if mf:
                last_file = mf[-1]
                break
        if last_file:
            if last_file.get("kind") == "image":
                user_full += (f"\n\n[Система: недавно в диалоге пользователь прислал изображение: "
                              f"{last_file['path']}. Скорее всего этот вопрос относится к нему. "
                              f"Если так — вызови analyze_image с image='{last_file['path']}' "
                              f"и отвечай по картинке. НЕ проси прислать снова — оно уже есть.]")
            else:
                user_full += (f"\n\n[Система: недавно был прислан файл: {last_file['path']}. "
                              f"Если вопрос про него — read_file с path='{last_file['path']}'.]")

    # гарантируем существование чата
    if not cid or cid not in CHATS:
        cid = new_chat()
    chat = CHATS[cid]

    # выбор модели
    # Смена модели в дропдапе сбрасывает закрепление (выбор пользователя в приоритете)
    new_force = "" if model in ("auto", "", None) else model
    if new_force != agent.force_model:
        agent.session_model = None
    agent.force_model = new_force

    # Шаг 2 Фазы 3: собираем prior_messages из честных turn-ов чата.
    # Модель увидит свои прошлые tool_calls и их результаты — не будет выдумывать.
    # Берём последние MAX_HISTORY turn-ов (= ~6 пар вопрос-ответ), не больше.
    prior_messages: list[dict] = []
    recent_turns = chat.get("turns", [])[-MAX_HISTORY:]
    for t in recent_turns:
        # Каждый turn — это полный лог [user, assistant?(tool_calls), tool, assistant(final)]
        # Просто конкатенируем — модель воспримет это как естественный диалог.
        prior_messages.extend(t.get("messages", []))

    # Фолбэк: если turn-ов нет (старый чат до Шага 1), склеиваем по-старому из messages.
    # Это позволит модели всё же видеть какой-то контекст, пока чат не обновится.
    fallback_context = ""
    if not prior_messages and chat["messages"]:
        msgs = chat["messages"]
        pairs = []
        i = 0
        while i < len(msgs):
            if msgs[i]["role"] == "user":
                a = msgs[i+1]["text"] if i+1 < len(msgs) and msgs[i+1]["role"] == "bot" else ""
                pairs.append((msgs[i]["text"], a))
            i += 1
        recent = pairs[-MAX_HISTORY:]
        if recent:
            fallback_context = ("Ниже — предыдущий диалог ДЛЯ КОНТЕКСТА (не копируй прошлые ответы "
                                "дословно, отвечай заново и по существу):\n" + "\n".join(
                f"Пользователь: {q}\nТы ответил: {a}" for q, a in recent) +
                "\n\n=====\nТЕКУЩИЙ ВОПРОС (ответь именно на него, полноценно):\n")

    try:
        # Если есть честная история — передаём её отдельным аргументом.
        # Если нет (старые чаты) — старый способ через склейку.
        answer = agent.run(fallback_context + user_full, prior_messages=prior_messages or None)
    except Exception as e:
        answer = f"[ошибка: {e}]"

    # Защита: гарантируем, что answer — строка.
    # Некоторые провайдеры могут вернуть list (мультимодальный content) или dict —
    # без этой защиты re.sub ниже падает с TypeError и фронт получает HTML 500.
    if not isinstance(answer, str):
        if isinstance(answer, list):
            parts_text = []
            for p in answer:
                if isinstance(p, dict):
                    parts_text.append(p.get("text", "") or "")
                else:
                    parts_text.append(str(p))
            answer = "".join(parts_text) or "[пустой ответ от модели]"
        else:
            answer = str(answer)

    # Распознаём сгенерированные картинки (маркер IMAGE:путь|текст)
    gen_images = []
    def _extract_img(m):
        rel = m.group(1).strip()
        caption = (m.group(2) or "").strip()
        gen_images.append("/agent_files/" + rel)
        return caption
    answer = re.sub(r"IMAGE:([^\s|]+)\|?([^\n]*)", _extract_img, answer)
    answer = answer.strip() or ("Готово!" if gen_images else answer)

    # сохраняем сообщения (старый формат — для UI)
    user_display = user + ("  📎 " + ", ".join(f.get("name","") for f in files) if files else "")
    chat["messages"].append({"role": "user", "text": user_display, "files": files})
    chat["messages"].append({"role": "bot", "text": answer, "model": agent.last_model, "images": gen_images})

    # Шаг 1 Фазы 3: сохраняем честный turn в OpenAI-формате (с tool_calls).
    # Пока никуда не передаётся — просто копится, чтобы убедиться, что лог
    # корректно собирается. На Шаге 2 начнём передавать его обратно в модель.
    chat.setdefault("turns", []).append({
        "ts": time.time(),
        "user_msg": {"text": user, "files": files, "display": user_display},
        "messages": list(agent.last_messages),  # копия лога from Agent
        "model": agent.last_model,
        "images": gen_images,
    })

    chat["ts"] = time.time()
    # заголовок чата = начало первого вопроса
    if chat["title"] == "Новый чат":
        chat["title"] = (user[:38] + "…") if len(user) > 38 else user
    save_chats()

    return jsonify({"answer": answer, "model": agent.last_model,
                    "images": gen_images, "chat_id": cid, "chats": _chat_list()})


if __name__ == "__main__":
    import threading, time as _t, webbrowser, socket

    URL = "http://127.0.0.1:5000"

    # Режим разработки (авто-перезагрузка): --dev или PG_DEV=1
    dev_mode = ("--dev" in sys.argv) or (os.environ.get("PG_DEV") == "1")

    # ── Защита от двойного запуска ──
    # Если порт 5000 уже занят — значит сервер УЖЕ работает (возможно, фоновый .vbs).
    # Не запускаем второй (это вызывало путаницу со старым кодом), просто открываем браузер.
    def _port_busy():
        try:
            with socket.create_connection(("127.0.0.1", 5000), timeout=0.5):
                return True
        except OSError:
            return False

    # в dev-режиме reloader сам перезапускает дочерний процесс — проверку делаем
    # только в основном процессе и не в dev
    if (not dev_mode) and os.environ.get("WERKZEUG_RUN_MAIN") != "true" and _port_busy():
        print("\n" + "═" * 56)
        print("  ⚠️  Polygraph УЖЕ запущен (порт 5000 занят).")
        print("  Открываю существующий сервер в браузере.")
        print("  Если нужен свежий запуск — сначала «Остановить Polygraph.bat».")
        print("═" * 56 + "\n")
        try:
            webbrowser.open(URL)
        except Exception:
            pass
        sys.exit(0)

    def open_browser_when_ready():
        # Ждём, пока сервер реально начнёт слушать порт, потом открываем браузер.
        for _ in range(60):  # до ~30 сек
            try:
                with socket.create_connection(("127.0.0.1", 5000), timeout=0.5):
                    break
            except OSError:
                _t.sleep(0.5)
        try:
            webbrowser.open(URL)
        except Exception:
            pass

    available = [n for n, p in pg.providers.items() if p.ok]
    print("\n" + "═" * 56)
    if available:
        print("  🔷 Polygraph Web запущен!")
        print(f"  Браузер откроется сам. Адрес:  {URL}")
        print(f"  Провайдеры: {', '.join(available)}")
    else:
        print("  ⚠️  Нет API-ключей! Заполни .env (см. .env.example).")
    print("  Остановить: Ctrl+C")
    print("═" * 56 + "\n")

    # Открываем браузер в фоне, как только сервер будет готов.
    # В dev-режиме reloader перезапускает процесс — открываем только в дочернем
    # (WERKZEUG_RUN_MAIN), чтобы не плодить вкладки.
    if (not dev_mode) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=open_browser_when_ready, daemon=True).start()

    # Режим разработки: сервер сам подхватывает правки в .py — перезапуск не нужен.
    if dev_mode:
        print("  🔧 Режим разработки: авто-перезагрузка при изменении кода ВКЛЮЧЕНА")
        print("═" * 56 + "\n")
        # use_reloader=True следит за файлами; браузер откроется один раз
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
    else:
        app.run(host="127.0.0.1", port=5000, debug=False)
