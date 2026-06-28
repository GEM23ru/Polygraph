"""
Polygraph — интерактивный чат с агентом.

Общайся с агентом в реальном времени: он умеет искать в интернете,
считать, читать/писать файлы и выполнять Python-код.

  python chat.py            # обычный режим
  python chat.py --debug    # показывать вызовы инструментов и ошибки

Команды внутри чата:
  /help     — помощь
  /tools    — список инструментов
  /models   — доступные модели
  /clear    — очистить память диалога
  /stats    — статистика вызовов
  /exit     — выход (или Ctrl+C)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import create
from agent import Agent, default_tools


HELP = """
Команды:
  /help    — эта справка
  /tools   — список доступных инструментов
  /models  — доступные модели (с твоими ключами)
  /model   — показать/сменить модель (/model gpt-oss, /model gemini, /model auto)
  /clear   — очистить память диалога
  /stats   — статистика вызовов
  /exit    — выход

Что умеет агент:
  • искать в интернете (web_search)
  • считать (calculator) и выполнять Python (run_python)
  • читать/писать файлы (read_file, write_file, list_files)
  • просто отвечать и рассуждать
"""


def main():
    debug = "--debug" in sys.argv
    print()
    pg = create()

    agent = Agent(pg, debug=debug)
    for t in default_tools(tavily_key=os.environ.get("TAVILY_API_KEY", "")):
        agent.register(t)

    # Проверка: есть ли хоть один рабочий провайдер
    available = [n for n, p in pg.providers.items() if p.ok]
    if not available:
        print("\n❌ Нет ни одного API-ключа. Заполни .env (см. .env.example) и запусти снова.")
        return

    print("\n" + "═" * 60)
    print("  🤖 Polygraph Chat — агент с инструментами")
    print("  Напиши сообщение или /help для команд. /exit — выход.")
    print("═" * 60)

    # Простая память диалога (последние реплики идут в контекст)
    history: list[tuple[str, str]] = []
    MAX_HISTORY = 6  # пар «вопрос-ответ»

    while True:
        try:
            user = input("\n\033[1;36mТы:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Пока!")
            break

        if not user:
            continue

        # ── Команды ──
        if user in ("/exit", "/quit", "/q"):
            print("👋 Пока!")
            break
        if user == "/help":
            print(HELP)
            continue
        if user == "/tools":
            print("\nИнструменты:")
            for name, t in agent.tools.items():
                print(f"  • {name} — {t.description}")
            continue
        if user == "/models":
            print("\nДоступные модели:")
            for m in pg.models(available_only=True):
                print(f"  {m['key']:14s} | {m['provider']:11s} | {m['speed']:8s} | ctx={m['context']}")
            continue
        if user == "/clear":
            history.clear()
            print("🧹 Память диалога очищена.")
            continue
        if user.startswith("/model"):
            parts = user.split()
            aliases = list(agent.MODEL_ALIASES.keys())
            if len(parts) == 1:
                cur = agent.force_model or "авто"
                print(f"Текущая модель: {cur}")
                print(f"Доступно: {', '.join(aliases)} (или /model auto — авто-выбор)")
            elif parts[1] in ("auto", "авто", ""):
                agent.force_model = ""
                print("✅ Модель: авто-выбор (gpt-oss → llama → ...)")
            elif parts[1] in agent.MODEL_ALIASES:
                agent.force_model = parts[1]
                print(f"✅ Модель зафиксирована: {parts[1]}")
            else:
                print(f"❌ Неизвестно. Доступно: {', '.join(aliases)}, auto")
            continue
        if user == "/stats":
            s = pg.stats()
            print(f"\nВызовов: {s['calls']}, ошибок: {s['errors']}, в кеше: {s['cache']}")
            for p, st in s["by_provider"].items():
                if st["calls"] or st["errs"]:
                    print(f"  {p}: {st['calls']}✓ / {st['errs']}✗")
            continue

        # ── Формируем сообщение с короткой памятью диалога ──
        context = ""
        if history:
            recent = history[-MAX_HISTORY:]
            context = "Предыдущий диалог:\n" + "\n".join(
                f"Ты: {q}\nАгент: {a}" for q, a in recent
            ) + "\n\nНовый вопрос:\n"

        print("\033[2m  ...думаю...\033[0m", end="\r")
        try:
            answer = agent.run(context + user)
        except Exception as e:
            answer = f"[ошибка: {e}]"

        print(" " * 20, end="\r")  # стираем "...думаю..."
        model_tag = f" \033[2m[{agent.last_model}]\033[0m" if agent.last_model else ""
        print(f"\033[1;32mАгент:\033[0m{model_tag} {answer}")

        history.append((user, answer))


if __name__ == "__main__":
    main()
