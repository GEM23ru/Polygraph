"""
Polygraph Web — веб-интерфейс чата (как ChatGPT, но локально).

  pip install flask
  python web.py
  → открой в браузере http://127.0.0.1:5000

Использует то же ядро (core.py) и агента (agent.py), что и chat.py.
"""

import sys, os, json, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, Response
from core import create
from agent import Agent, default_tools

app = Flask(__name__)

# ── Инициализация агента (один раз при старте) ──
pg = create()
agent = Agent(pg, debug=False)
for t in default_tools(tavily_key=os.environ.get("TAVILY_API_KEY", "")):
    agent.register(t)

MAX_HISTORY = 6

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
    CHATS[cid] = {"id": cid, "title": "Новый чат", "messages": [], "ts": time.time()}
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
    --border:#242936; --text:#e6e8ee; --muted:#8b93a3; --bubble-user:#1c2struct;
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
  header h1 { font-size:16px; font-weight:600; display:flex; align-items:center; gap:8px; }
  header .logo { width:24px; height:24px; }
  header .spacer { flex:1; }
  select { background:var(--bg2); color:var(--text); border:1px solid var(--border); border-radius:9px; padding:8px 12px; font-size:13px; cursor:pointer; }
  .status { display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); cursor:pointer; padding:4px 8px; border-radius:8px; }
  .status:hover { background:var(--hover); }
  .status .pill { display:inline-flex; align-items:center; gap:4px; }
  .status .led { width:8px; height:8px; border-radius:50%; }
  .status .led.on { background:#34d399; box-shadow:0 0 6px #34d399; }
  .status .led.off { background:#ef4444; box-shadow:0 0 6px #ef4444; }
  .status .led.wait { background:#fbbf24; }

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
  .card .ttl { font-weight:600; font-size:14px; margin-bottom:4px; }
  .card .sub { font-size:12.5px; color:var(--muted); }

  /* Messages - stil Claude/ChatGPT */
  .msg { margin:22px 0; display:flex; flex-direction:column; animation:fade .3s ease; }
  @keyframes fade { from{opacity:0; transform:translateY(6px)} to{opacity:1; transform:none} }
  .msg.user { align-items:flex-end; }
  .msg.bot { align-items:flex-start; }
  .msg .body { line-height:1.6; white-space:pre-wrap; word-wrap:break-word; font-size:15px; max-width:100%; }
  /* puzyr usera sprava */
  .msg.user .body { background:var(--bg3); padding:11px 16px; border-radius:18px; max-width:78%; }
  /* otvet agenta - bez puzyrya */
  .msg.bot .body { padding:0; }
  .msg .tag { font-size:11px; color:var(--muted); margin-bottom:5px; display:flex; align-items:center; gap:6px; }
  .msg .tag .botico { width:18px; height:18px; border-radius:5px; }
  .msg .body .tablewrap { overflow-x:auto; margin:12px 0; border-radius:10px; border:1px solid var(--border); }
  .msg .body table { border-collapse:collapse; font-size:14px; width:100%; }
  .msg .body th { border:1px solid var(--border); padding:9px 13px; background:var(--bg3); font-weight:600; text-align:left; white-space:nowrap; }
  .msg .body td { border:1px solid var(--border); padding:9px 13px; vertical-align:top; min-width:120px; line-height:1.5; }
  .msg .body tbody tr:nth-child(even) td { background:var(--bg2); }
  .msg .body h4 { font-size:15px; font-weight:700; margin:14px 0 6px; color:var(--accent); }
  .msg .body ul { margin:8px 0 8px 4px; padding-left:18px; }
  .msg .body ol { margin:8px 0 8px 4px; padding-left:22px; }
  .msg .body li { margin:3px 0; }
  .msg .body hr { border:none; border-top:1px solid var(--border); margin:14px 0; }
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
  .attach { background:transparent; border:1px solid var(--border); color:var(--muted); width:34px; height:34px; border-radius:50%; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center; transition:all .15s; }
  .attach:hover { background:var(--hover); color:var(--text); }
  .attach svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
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
    <button class="iconbtn" onclick="toggleSidebar()" title="Свернуть панель">☰</button>
    <h1><img class="logo" src="/favicon.ico" alt=""> Polygraph</h1>
    <span id="status" class="status" title="Статус провайдеров — нажми для проверки" onclick="checkStatus()"></span>
    <span class="spacer"></span>
    <select id="model" title="Модель">
      <option value="auto">Авто</option>
      <option value="gpt-oss">gpt-oss (умная)</option>
      <option value="gemini">Gemini</option>
      <option value="llama">Llama 70B</option>
      <option value="fast">Быстрая</option>
    </select>
    <button class="iconbtn" onclick="toggleTheme()" id="themeBtn" title="Сменить тему">🌙</button>
  </header>

  <!-- Приветственный экран -->
  <div id="welcome">
    <img class="biglogo" src="/favicon.ico" alt="">
    <h2>Чем могу помочь?</h2>
    <p>Я Polygraph — умный ассистент. Ищу в интернете, читаю сайты, пишу код, считаю и работаю с файлами.</p>
    <div class="cards">
      <div class="card" onclick="quick('Найди и сделай вывод: актуальные тренды для продавцов на Wildberries')">
        <div class="ttl">🔍 Исследование</div>
        <div class="sub">Найти в интернете и сделать вывод</div>
      </div>
      <div class="card" onclick="quick('Напиши на Python функцию, которая проверяет, палиндром ли строка')">
        <div class="ttl">💻 Код</div>
        <div class="sub">Написать и проверить программу</div>
      </div>
      <div class="card" onclick="quick('Объясни простыми словами, что такое нейросеть')">
        <div class="ttl">💡 Объяснение</div>
        <div class="sub">Разобрать сложную тему просто</div>
      </div>
      <div class="card" onclick="quick('Посчитай сложный процент: 100000 рублей под 12% годовых на 3 года')">
        <div class="ttl">🧮 Расчёты</div>
        <div class="sub">Вычислить через код</div>
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
  s = s.replace(/^[ \t]*#{1,6}[ \t]*(.+)$/gm, function(m,t){ return '<h4>'+t.trim()+'</h4>'; });
  s = s.replace(/^[ \t]*-{3,}[ \t]*$/gm, '<hr>');
  s = s.replace(/[*][*](.+?)[*][*]/g,'<b>$1</b>');
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

function toggleTheme(){
  const html = document.documentElement;
  const next = html.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  document.getElementById('themeBtn').textContent = next==='dark' ? '🌙' : '☀️';
  localStorage.setItem('pg_theme', next);
}
(function(){ const t=localStorage.getItem('pg_theme'); if(t){ document.documentElement.setAttribute('data-theme',t); document.getElementById('themeBtn')&&(document.getElementById('themeBtn').textContent=t==='dark'?'🌙':'☀️'); } })();

function quick(text){ inp.value=text; sendMsg(); }

async function checkStatus(){
  const el = document.getElementById('status');
  el.innerHTML = '<span class="pill"><span class="led wait"></span>проверяю…</span>';
  try{
    const r = await fetch('/api/status'); const d = await r.json();
    el.innerHTML = d.providers.map(p =>
      `<span class="pill"><span class="led ${p.ok?'on':'off'}"></span>${p.name}${p.ok?'':' ('+(p.reason||'нет')+')'}</span>`
    ).join('&nbsp;&nbsp;');
  }catch(e){ el.innerHTML = '<span class="pill"><span class="led off"></span>нет связи</span>'; }
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


def _send_icon(prefer_png=False):
    names = ("polygraph_icon.png", "polygraph.ico") if prefer_png else ("polygraph.ico", "polygraph_icon.png")
    for name in names:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        if os.path.exists(path):
            mime = "image/x-icon" if name.endswith(".ico") else "image/png"
            with open(path, "rb") as f:
                resp = Response(f.read(), mimetype=mime)
                resp.headers["Cache-Control"] = "no-cache"  # пусть браузер не кэширует
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
    """Проверка, какие провайдеры реально отвечают (живой пинг)."""
    import concurrent.futures as _cf
    checks = [
        ("groq", "groq-8b", "Groq (VPN)"),
        ("google", "gemini", "Google"),
        ("openrouter", "grok", "OpenRouter"),
    ]
    def ping(item):
        pname, mkey, label = item
        prov = pg.providers.get(pname)
        if not prov or not prov.ok:
            return {"name": label, "ok": False, "reason": "нет ключа"}
        from core import MODELS
        spec = MODELS.get(mkey)
        try:
            r = prov.call(spec.model_id, "", "ok", 0.0, 5)
            return {"name": label, "ok": bool(r and not str(r).startswith("[!"))}
        except Exception as e:
            msg = str(e)
            reason = "VPN?" if ("Forbidden" in msg or "403" in msg) else ("лимит" if "429" in msg else "ошибка")
            return {"name": label, "ok": False, "reason": reason}
    results = []
    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
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
    import re as _re
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "нет файла"}), 400

    # Безопасное имя файла
    name = os.path.basename(f.filename)
    name = _re.sub(r"[^\w.\-() ]", "_", name)[:120] or "file"

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
    import re as _refref
    refers_to_file = bool(_refref.search(
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

    # контекст из истории этого чата
    msgs = chat["messages"]
    context = ""
    if msgs:
        pairs = []
        i = 0
        while i < len(msgs):
            if msgs[i]["role"] == "user":
                a = msgs[i+1]["text"] if i+1 < len(msgs) and msgs[i+1]["role"] == "bot" else ""
                pairs.append((msgs[i]["text"], a))
            i += 1
        recent = pairs[-MAX_HISTORY:]
        if recent:
            context = ("Ниже — предыдущий диалог ДЛЯ КОНТЕКСТА (не копируй прошлые ответы "
                       "дословно, отвечай заново и по существу):\n" + "\n".join(
                f"Пользователь: {q}\nТы ответил: {a}" for q, a in recent) +
                "\n\n=====\nТЕКУЩИЙ ВОПРОС (ответь именно на него, полноценно):\n")

    try:
        answer = agent.run(context + user_full)
    except Exception as e:
        answer = f"[ошибка: {e}]"

    # Распознаём сгенерированные картинки (маркер IMAGE:путь|текст)
    import re as _re2
    gen_images = []
    def _extract_img(m):
        rel = m.group(1).strip()
        caption = (m.group(2) or "").strip()
        gen_images.append("/agent_files/" + rel)
        return caption
    answer = _re2.sub(r"IMAGE:([^\s|]+)\|?([^\n]*)", _extract_img, answer)
    answer = answer.strip() or ("Готово!" if gen_images else answer)

    # сохраняем сообщения
    user_display = user + ("  📎 " + ", ".join(f.get("name","") for f in files) if files else "")
    chat["messages"].append({"role": "user", "text": user_display, "files": files})
    chat["messages"].append({"role": "bot", "text": answer, "model": agent.last_model, "images": gen_images})
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

    # ── Защита от двойного запуска ──
    # Если порт 5000 уже занят — значит сервер УЖЕ работает (возможно, фоновый .vbs).
    # Не запускаем второй (это вызывало путаницу со старым кодом), просто открываем браузер.
    def _port_busy():
        try:
            with socket.create_connection(("127.0.0.1", 5000), timeout=0.5):
                return True
        except OSError:
            return False

    _dev_check = ("--dev" in sys.argv) or (os.environ.get("PG_DEV") == "1")
    # в dev-режиме reloader сам перезапускает дочерний процесс — проверку делаем
    # только в основном процессе и не в dev
    if (not _dev_check) and os.environ.get("WERKZEUG_RUN_MAIN") != "true" and _port_busy():
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

    # Открываем браузер в фоне, как только сервер будет готов
    # Открываем браузер только один раз. В dev-режиме reloader перезапускает
    # процесс — открываем только в дочернем (WERKZEUG_RUN_MAIN), чтобы не плодить вкладки.
    _dev = ("--dev" in sys.argv) or (os.environ.get("PG_DEV") == "1")
    if (not _dev) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=open_browser_when_ready, daemon=True).start()

    # Режим разработки (авто-перезагрузка при изменении кода):
    #   python web.py --dev    ИЛИ  установить PG_DEV=1
    # В этом режиме сервер сам подхватывает правки в .py — перезапуск не нужен.
    dev_mode = ("--dev" in sys.argv) or (os.environ.get("PG_DEV") == "1")
    if dev_mode:
        print("  🔧 Режим разработки: авто-перезагрузка при изменении кода ВКЛЮЧЕНА")
        print("═" * 56 + "\n")
        # use_reloader=True следит за файлами; браузер откроется один раз
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
    else:
        app.run(host="127.0.0.1", port=5000, debug=False)
