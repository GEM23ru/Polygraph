"""
Polygraph — мульти-провайдерный AI-оркестратор.
6 провайдеров. 20+ моделей. Одна правда.
"""

import os, time, json, hashlib
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Загрузка .env ===
try:
    from pathlib import Path
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
except Exception:
    pass


# ============================================================
# ТИПЫ ЗАДАЧ
# ============================================================

class TaskType(Enum):
    FAST = "fast"
    REASONING = "reasoning"
    CODING = "coding"
    CREATIVE = "creative"
    LONG = "long"

def classify(prompt: str) -> TaskType:
    t = prompt.lower()
    if any(w in t for w in ["код", "функци", "класс", "python", "javascript",
            "react", "api", "скрипт", "алгоритм", "рефактор", "баг"]):
        return TaskType.CODING
    if any(w in t for w in ["объясни", "почему", "как работает", "разбери",
            "проанализируй", "логика", "шаг за шагом", "докажи"]):
        return TaskType.REASONING
    if any(w in t for w in ["напиши статью", "слоган", "продающ", "реклам",
            "пост", "историю", "креатив", "придумай", "сценарий"]):
        return TaskType.CREATIVE
    if len(prompt) > 2000:
        return TaskType.LONG
    return TaskType.FAST


# ============================================================
# МОДЕЛИ
# ============================================================

@dataclass
class Spec:
    key: str
    provider: str
    model_id: str
    speed: str
    context: int
    strengths: list[str] = field(default_factory=list)

MODELS = {
    # ===== OpenRouter (free) — проверено живыми на 2026-06 =====
    "r1":           Spec("r1",           "openrouter", "z-ai/glm-4.5-air:free",                    "smart",   131072,  ["reasoning", "coding"]),
    "deepseek":     Spec("deepseek",     "openrouter", "meta-llama/llama-3.3-70b-instruct:free",   "balanced",131072,  ["chat", "coding"]),
    "llama4":       Spec("llama4",       "openrouter", "qwen/qwen3-coder:free",                    "smart",  1048576,  ["long", "coding"]),
    "qwen":         Spec("qwen",         "openrouter", "qwen/qwen3-next-80b-a3b-instruct:free",    "smart",   262144,  ["coding"]),
    "grok":         Spec("grok",         "openrouter", "openai/gpt-oss-20b:free",                  "fast",    131072,  ["fast"]),
    "gemma":        Spec("gemma",        "openrouter", "google/gemma-4-31b-it:free",               "balanced",262144,  ["chat"]),
    "mistral-or":   Spec("mistral-or",   "openrouter", "nvidia/nemotron-nano-9b-v2:free",          "balanced",128000,  ["chat"]),
    "oss120":       Spec("oss120",       "openrouter", "openai/gpt-oss-120b:free",                 "smart",   131072,  ["reasoning", "coding"]),

    # ===== Google AI Studio =====
    "gemini":       Spec("gemini",       "google",    "gemini-2.5-flash",                          "fast",  1000000,  ["fast", "multimodal"]),
    "gemini-pro":   Spec("gemini-pro",   "google",    "gemini-2.5-pro",                            "smart", 1000000,  ["reasoning", "coding"]),
    "gemini-3":     Spec("gemini-3",     "google",    "gemini-3-flash-preview",                    "fast",  1000000,  ["fast"]),

    # ===== Groq =====
    "groq-70b":     Spec("groq-70b",     "groq",      "llama-3.3-70b-versatile",                  "fast",   128000,  ["fast", "chat"]),
    "groq-8b":      Spec("groq-8b",      "groq",      "llama-3.1-8b-instant",                     "fast",   128000,  ["fast"]),
    "groq-oss":     Spec("groq-oss",     "groq",      "openai/gpt-oss-120b",                      "balanced",128000, ["reasoning", "chat"]),
    "groq-kimi":    Spec("groq-kimi",    "groq",      "moonshotai/kimi-k2-instruct-0905",         "smart",  256000,  ["reasoning", "coding"]),
    "groq-qwen":    Spec("groq-qwen",    "groq",      "qwen/qwen3-32b",                           "balanced",128000, ["coding", "reasoning"]),

    # ===== Cerebras =====
    "cerebras":     Spec("cerebras",     "cerebras",  "llama3.3-70b",                              "fast",    8000,   ["fast"]),

    # ===== Mistral AI =====
    "mistral-l":    Spec("mistral-l",    "mistral",   "mistral-large-latest",                      "smart",  256000,  ["reasoning"]),
    "mistral-s":    Spec("mistral-s",    "mistral",   "mistral-small-latest",                      "balanced",256000,  ["chat"]),

    # ===== Cohere =====
    "cohere":       Spec("cohere",       "cohere",    "command-r-plus",                            "smart",   128000,  ["reasoning"]),
}

ROUTES = {
    # Приоритет: Groq первым (14 400/день — самый щедрый лимит и самый быстрый),
    # затем OpenRouter / Google / Mistral / Cohere как резерв.
    # Роутер сам пропустит провайдеров без ключа, так что список безопасен.
    TaskType.FAST:      ["groq-8b", "groq-70b", "grok", "gemini", "gemma", "mistral-s"],
    TaskType.REASONING: ["groq-oss", "groq-70b", "oss120", "gemini-pro", "mistral-l", "cohere"],
    TaskType.CODING:    ["groq-qwen", "groq-kimi", "groq-70b", "qwen", "llama4", "oss120"],
    TaskType.CREATIVE:  ["groq-70b", "groq-kimi", "deepseek", "gemini", "mistral-s", "cohere"],
    TaskType.LONG:      ["groq-kimi", "llama4", "gemini", "mistral-l", "gemini-pro"],
}

# Fallback: сначала щедрый Groq, потом всё остальное доступное.
FALLBACK = ["groq-70b", "groq-8b", "groq-oss", "oss120", "grok", "deepseek",
            "gemma", "gemini", "mistral-s", "mistral-l", "cohere", "gemini-pro"]


# ============================================================
# ПРОВАЙДЕРЫ
# ============================================================

class BaseProvider:
    def __init__(self, api_key=""):
        self.api_key = api_key
    @property
    def ok(self) -> bool:
        return bool(self.api_key and "your-key-here" not in self.api_key)
    def call(self, model_id, system, prompt, temperature=0.7, max_tokens=2048) -> str:
        raise NotImplementedError


class OpenRouter(BaseProvider):
    name = "openrouter"
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            from openai import OpenAI
            self._c = OpenAI(api_key=self.api_key, base_url="https://openrouter.ai/api/v1")
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        msgs = []
        if sys: msgs.append({"role":"system","content":sys})
        msgs.append({"role":"user","content":p})
        r = self.c.chat.completions.create(model=mid, messages=msgs, temperature=t, max_tokens=mt, timeout=30)
        return r.choices[0].message.content


class Google(BaseProvider):
    name = "google"
    import threading as _threading
    _last_call = 0.0  # rate limit: 10 RPM → 6 сек между вызовами
    _lock = _threading.Lock()  # потокобезопасность для parallel/ensemble
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            from google import genai
            self._c = genai.Client(api_key=self.api_key)
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        # Соблюдаем rate limit (10 RPM = 1 вызов в 6 секунд),
        # сериализуя вызовы между потоками через общий lock.
        with Google._lock:
            elapsed = time.time() - Google._last_call
            if elapsed < 6.0:
                time.sleep(6.0 - elapsed)
            Google._last_call = time.time()

        txt = f"System: {sys}\n\nUser: {p}" if sys else p
        r = self.c.models.generate_content(model=mid, contents=txt,
            config={"temperature":t,"max_output_tokens":mt})
        return r.text


class GroqProvider(BaseProvider):
    name = "groq"
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            from groq import Groq as G
            self._c = G(api_key=self.api_key)
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        msgs = []
        if sys: msgs.append({"role":"system","content":sys})
        msgs.append({"role":"user","content":p})
        r = self.c.chat.completions.create(model=mid, messages=msgs, temperature=t, max_tokens=mt)
        return r.choices[0].message.content


class CerebrasProvider(BaseProvider):
    name = "cerebras"
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            from openai import OpenAI
            self._c = OpenAI(api_key=self.api_key, base_url="https://api.cerebras.ai/v1")
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        msgs = []
        if sys: msgs.append({"role":"system","content":sys})
        msgs.append({"role":"user","content":p})
        r = self.c.chat.completions.create(model=mid, messages=msgs, temperature=t, max_tokens=mt)
        return r.choices[0].message.content


class MistralProvider(BaseProvider):
    name = "mistral"
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            from openai import OpenAI
            self._c = OpenAI(api_key=self.api_key, base_url="https://api.mistral.ai/v1")
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        msgs = []
        if sys: msgs.append({"role":"system","content":sys})
        msgs.append({"role":"user","content":p})
        r = self.c.chat.completions.create(model=mid, messages=msgs, temperature=t, max_tokens=mt)
        return r.choices[0].message.content


class CohereProvider(BaseProvider):
    name = "cohere"
    def __init__(self, key=""):
        super().__init__(key)
        self._c = None
    @property
    def c(self):
        if self._c is None and self.ok:
            import cohere as ch
            self._c = ch.ClientV2(api_key=self.api_key)
        return self._c
    def call(self, mid, sys, p, t=0.7, mt=2048):
        msgs = []
        if sys: msgs.append({"role":"system","content":sys})
        msgs.append({"role":"user","content":p})
        r = self.c.chat(model=mid, messages=msgs, temperature=t, max_tokens=mt)
        return r.message.content[0].text if r.message.content else ""


# ============================================================
# POLYGRAPH
# ============================================================

class Polygraph:

    def __init__(self):
        keys = {n: os.environ.get(k, "") for n, k in [
            ("openrouter","OPENROUTER_API_KEY"), ("google","GEMINI_API_KEY"),
            ("groq","GROQ_API_KEY"), ("cerebras","CEREBRAS_API_KEY"),
            ("mistral","MISTRAL_API_KEY"), ("cohere","COHERE_API_KEY"),
        ]}
        self.providers = {}
        for name, cls in [
            ("openrouter", OpenRouter), ("google", Google),
            ("groq", GroqProvider), ("cerebras", CerebrasProvider),
            ("mistral", MistralProvider), ("cohere", CohereProvider)
        ]:
            self.providers[name] = cls(keys.get(name, ""))

        self._cache: dict[str, tuple[float, str]] = {}
        self._stats = {n: {"calls":0,"errs":0} for n in self.providers}

        ok = [p.name for p in self.providers.values() if p.ok]
        print(f"🔷 Polygraph: {len(ok)} провайдер{'ов' if len(ok)!=1 else ''}, {len(MODELS)} моделей")
        for o in ok: print(f"   ✅ {o}")
        no = [n for n,p in self.providers.items() if not p.ok]
        if no: print(f"   ⚠️  Нет ключей: {', '.join(no)}")

    # ===== Вызов модели =====
    def ask(self, model: str, system: str = "", prompt: str = "",
            temperature: float = 0.7, max_tokens: int = None) -> str:
        spec = MODELS.get(model)
        if not spec:
            return f"[!] Unknown: {model}"
        prov = self.providers.get(spec.provider)
        if not prov or not prov.ok:
            return f"[!] {spec.provider} off"

        ck = hashlib.md5(f"{model}:{system}:{prompt}".encode()).hexdigest()
        if ck in self._cache:
            ts, val = self._cache[ck]
            if time.time() - ts < 300:  # 5 min cache
                return val
            del self._cache[ck]

        mt = max_tokens or 1024
        last_err = ""

        for attempt in range(3):
            try:
                result = prov.call(spec.model_id, system, prompt, temperature, mt)
                self._cache[ck] = (time.time(), result)
                self._stats[spec.provider]["calls"] += 1
                return result
            except Exception as e:
                self._stats[spec.provider]["errs"] += 1
                last_err = str(e)[:100]
                if attempt < 2:
                    time.sleep(2 + attempt * 3)  # нарастающая задержка

        # Fallback при неудаче
        fb = self._fallback(system, prompt, temperature, mt)
        if fb:
            self._cache[ck] = (time.time(), fb)
            return fb
        return f"[!] {model} + fallback exhausted ({last_err})"

    def _fallback(self, sys, p, t, mt):
        for m in FALLBACK:
            spec = MODELS.get(m)
            if not spec: continue
            prov = self.providers.get(spec.provider)
            if not prov or not prov.ok: continue
            try:
                r = prov.call(spec.model_id, sys, p, t, mt)
                self._stats[spec.provider]["calls"] += 1
                return r
            except:
                self._stats[spec.provider]["errs"] += 1
                time.sleep(1)
        return ""

    # ===== Роутинг =====
    def _is_available(self, model_key: str) -> bool:
        """Есть ли ключ у провайдера этой модели (без сетевого запроса)."""
        spec = MODELS.get(model_key)
        if not spec:
            return False
        prov = self.providers.get(spec.provider)
        return bool(prov and prov.ok)

    def route(self, prompt: str, context: str = "") -> str:
        task = classify(prompt)
        candidates = ROUTES[task]
        full = f"{context}\n\n{prompt}" if context else prompt
        sys = "Ты — полезный ассистент. Отвечай точно, по делу, без воды."

        # Пробуем только модели, у которых есть ключ (не тратим попытки впустую)
        for m in candidates:
            if not self._is_available(m):
                continue
            r = self.ask(m, sys, full)
            if not r.startswith("[!"):
                return r

        # Запасной круг: ЛЮБАЯ доступная модель из FALLBACK
        for m in FALLBACK:
            if not self._is_available(m):
                continue
            r = self.ask(m, sys, full)
            if not r.startswith("[!"):
                return r

        return "[!] Все доступные модели сейчас недоступны (лимиты исчерпаны или провайдеры заняты). Попробуй позже или добавь ключ Groq."

    # ===== Параллельный вызов =====
    def parallel(self, tasks: list[dict]) -> dict[str, str]:
        valid = []
        for t in tasks:
            m = t.get("model","gemini")
            spec = MODELS.get(m)
            if spec:
                prov = self.providers.get(spec.provider)
                if prov and prov.ok:
                    valid.append(t)
        if not valid:
            return {"error": "no available models"}

        results = {}
        with ThreadPoolExecutor(max_workers=min(len(valid), 4)) as ex:
            futs = {}
            for t in valid:
                f = ex.submit(self.ask, t["model"],
                    t.get("system",""), t.get("prompt",""), t.get("temperature",0.7))
                futs[f] = t["model"]
            for f in as_completed(futs):
                results[futs[f]] = f.result()
        return results

    # ===== Ансамбль =====
    def ensemble(self, system: str, prompt: str) -> str:
        # Берём по одной работающей модели от каждого доступного провайдера
        models = []
        for prov_name in ["openrouter", "google", "groq"]:
            prov = self.providers.get(prov_name)
            if not prov or not prov.ok: continue
            for key, spec in MODELS.items():
                if spec.provider == prov_name and spec.speed in ("smart", "balanced", "fast"):
                    models.append(key)
                    break
        models = models[:3]

        if len(models) < 2:
            return self.route(prompt)

        tasks = [{"model": m, "system": system, "prompt": prompt} for m in models]
        results = self.parallel(tasks)
        good = {m: r for m, r in results.items() if r and not r.startswith("[!")}

        if len(good) < 2:
            return list(good.values())[0] if good else self.route(prompt)

        syn = (f"Синтезируй лучший ответ из вариантов. Будь краток.\n\n"
               f"Вопрос: {prompt}\n\n" +
               "\n\n".join(f"--- {m} ---\n{r}" for m, r in good.items()) +
               "\n\nСинтезированный ответ:")
        return self.ask("gemini", "Ты — редактор.", syn)

    # ===== Load-balanced =====
    def balanced(self, system: str, prompt: str) -> str:
        avail = [(self._stats[name]["calls"], name, prov)
                 for name, prov in self.providers.items() if prov.ok]
        avail.sort(key=lambda x: x[0])
        for _, pname, _ in avail:
            for mk, spec in MODELS.items():
                if spec.provider == pname and spec.speed == "fast":
                    r = self.ask(mk, system, prompt)
                    if not r.startswith("[!"): return r
        return self.ask("gemini", system, prompt)

    # ===== Инфо =====
    def stats(self) -> dict:
        return {
            "calls": sum(s["calls"] for s in self._stats.values()),
            "errors": sum(s["errs"] for s in self._stats.values()),
            "by_provider": dict(self._stats),
            "cache": len(self._cache),
        }

    def models(self, available_only: bool = False) -> list[dict]:
        r = []
        for k, s in MODELS.items():
            ok = self.providers.get(s.provider) and self.providers[s.provider].ok
            if available_only and not ok: continue
            r.append({"key":k,"provider":s.provider,"model":s.model_id,"speed":s.speed,"context":s.context,"ok":ok,"strengths":s.strengths})
        return r


def create() -> Polygraph:
    return Polygraph()
