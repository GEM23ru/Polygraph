"""
Polygraph — демо-запуск.

  1. Вставь ключи в .env
  2. pip install -r requirements.txt
  3. python run.py
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import create, MODELS
from agent import Agent, default_tools


def main():
    print()
    pg = create()

    # Инструменты (debug=True — печатает вызовы инструментов и ошибки провайдеров)
    agent = Agent(pg, debug=True)
    for t in default_tools(tavily_key=os.environ.get("TAVILY_API_KEY", "")):
        agent.register(t)

    print("\n📋 Доступные модели:")
    for m in pg.models(available_only=True):
        print(f"   {m['key']:15s} | {m['provider']:12s} | {m['speed']:8s} | ctx={m['context']}")

    # === 1. Роутинг: быстро ===
    print("\n" + "─" * 60)
    print("1. Роутинг: быстрый вопрос → gpt-oss-20b / Gemini Flash")
    r = pg.route("Сколько будет 15% от 3400 рублей?")
    print(r[:300])

    time.sleep(1)  # пауза чтобы не спамить API

    # === 2. Роутинг: сложно ===
    print("\n" + "─" * 60)
    print("2. Роутинг: сложный вопрос → GLM-4.5-Air / Gemini Pro")
    r = pg.route("Объясни, почему небо голубое, с точки зрения физики. 3 предложения.")
    print(r[:400])

    time.sleep(1)

    # === 3. Параллельно ===
    print("\n" + "─" * 60)
    print("3. Parallel: 2 модели одновременно")
    results = pg.parallel([
        {"model":"gemini",    "system":"Reply in Russian.","prompt":"Хайку про код."},
        {"model":"deepseek",  "system":"Reply in Russian.","prompt":"Что такое рекурсия? 1 предложение."},
    ])
    for m, a in results.items():
        print(f"\n   [{m}]: {a[:250]}")

    time.sleep(1)

    # === 4. Ансамбль ===
    print("\n" + "─" * 60)
    print("4. Ансамбль: модели из разных провайдеров → синтез")
    r = pg.ensemble("Reply in Russian.", "3 главных тренда AI в 2026. По 1 предложению.")
    print(r[:500])

    time.sleep(1)

    # === 5. Load-balanced ===
    print("\n" + "─" * 60)
    print("5. Load-balanced (наименее загруженный провайдер)")
    r = pg.balanced("You are helpful.", "What is the capital of France? В 1 предложении.")
    print(r[:200])

    time.sleep(1)

    # === 6. Agent loop ===
    print("\n" + "─" * 60)
    print("6. Agent loop (function calling)")
    r = agent.run("Посчитай (15 + 7) * 3 и скажи текущее время.")
    print(r[:400])

    # === Статистика ===
    print("\n" + "─" * 60)
    s = pg.stats()
    print(f"Статистика: {s['calls']} вызовов, {s['errors']} ошибок, {s['cache']} в кеше")
    for p, st in s["by_provider"].items():
        print(f"   {p}: {st['calls']}✓ / {st['errs']}✗")

    print("\n" + "─" * 60)
    print("✅ Polygraph reality check complete.")


if __name__ == "__main__":
    main()
