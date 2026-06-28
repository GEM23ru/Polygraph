"""
Polygraph — самодиагностика.

Проверяет КАЖДУЮ модель из MODELS реальным мини-запросом,
с паузами между запросами (чтобы не упереться в rate limit)
и повтором при временных ошибках 429/503.

  python healthcheck.py            # проверить все модели
  python healthcheck.py --free     # только бесплатные (openrouter + google)
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import create, MODELS

# Пауза между запросами к ОДНОМУ провайдеру (чтобы не словить лимит).
# OpenRouter free ~20 RPM, Google free 10 RPM → 7 секунд безопасно.
PAUSE = {"openrouter": 4.0, "google": 7.0, "groq": 2.5}
DEFAULT_PAUSE = 2.0

FREE_PROVIDERS = {"openrouter", "google", "groq"}


def try_model(prov, spec, retries=2):
    """Пробуем модель, повторяя при временных ошибках (429/503)."""
    last_err = ""
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            # 300 токенов — чтобы reasoning-модели (gpt-oss и т.п.) успели
            # потратить часть на размышление и всё равно выдать ответ.
            r = prov.call(spec.model_id, "", "Скажи 'привет' одним словом.", 0.0, 300)
            dt = time.time() - t0
            if r and r.strip():
                return ("ok", dt, r.strip()[:45])
            last_err = "пустой ответ"
        except Exception as e:
            dt = time.time() - t0
            last_err = str(e)
            # 429/503 — временные, есть смысл повторить с паузой
            if ("429" in last_err or "503" in last_err) and attempt < retries:
                wait = 8 * (attempt + 1)
                print(f"     ↻ {spec.key}: {('429 лимит' if '429' in last_err else '503 занято')}, "
                      f"повтор через {wait}s...")
                time.sleep(wait)
                continue
            return ("fail", dt, last_err[:80])
    return ("fail", 0.0, last_err[:80])


def main():
    free_only = "--free" in sys.argv
    print()
    pg = create()
    title = "только бесплатные" if free_only else "все"
    print(f"\n🩺 Проверяю модели ({title}) с паузами против rate limit...\n")

    ok_list, fail_list, skip_list = [], [], []

    for key, spec in MODELS.items():
        if free_only and spec.provider not in FREE_PROVIDERS:
            skip_list.append(key)
            continue
        prov = pg.providers.get(spec.provider)
        if not prov or not prov.ok:
            skip_list.append(key)
            continue

        status, dt, info = try_model(prov, spec)
        if status == "ok":
            print(f"  ✅ {key:14s} | {spec.provider:11s} | {dt:5.1f}s | {info}")
            ok_list.append(key)
        else:
            tag = "429 лимит" if "429" in info else ("503 занято" if "503" in info else "ошибка")
            print(f"  ❌ {key:14s} | {spec.provider:11s} | {dt:5.1f}s | [{tag}] {info[:50]}")
            fail_list.append(key)

        # пауза перед следующим запросом к тому же провайдеру
        time.sleep(PAUSE.get(spec.provider, DEFAULT_PAUSE))

    print("\n" + "─" * 60)
    print(f"✅ Работает:    {len(ok_list)}  → {', '.join(ok_list) or '—'}")
    print(f"❌ Ошибки:      {len(fail_list)} → {', '.join(fail_list) or '—'}")
    print(f"⏭️  Пропущено:   {len(skip_list)} → {', '.join(skip_list) or '—'}")
    print("─" * 60)

    if fail_list:
        print("\n💡 429 = лимит исчерпан (подожди минуту/завтра).")
        print("   503 = провайдер сейчас перегружен (попробуй позже).")
        print("   Это НЕ поломка — бесплатные пулы общие и иногда заняты.")


if __name__ == "__main__":
    main()
