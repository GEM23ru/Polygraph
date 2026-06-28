"""
Шаг 1 Фазы 3 — smoke-тест.
Проверяем, что Agent.last_messages корректно заполняется в OpenAI-ветке
после симулированного вызова с tool_calls.

Без реальных API — мокаем провайдера inline.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Agent, Tool


# ── Мок-классы провайдера ──────────────────────────────────────────
class MockMsg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

class MockChoice:
    def __init__(self, msg):
        self.message = msg

class MockResp:
    def __init__(self, msg):
        self.choices = [MockChoice(msg)]

class MockToolCall:
    def __init__(self, tcid, name, args):
        self.id = tcid
        class F:
            def __init__(s, n, a):
                s.name = n
                s.arguments = json.dumps(a)
        self.function = F(name, args)
        self.type = "function"

class MockChat:
    """Возвращает ответы по очереди из списка."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def create(self, **kw):
        self.calls.append(kw)
        if self.responses:
            return self.responses.pop(0)
        return MockResp(MockMsg("конец"))

class MockClient:
    def __init__(self, responses):
        self.chat = type("X", (), {"completions": MockChat(responses)})()

class MockProvider:
    def __init__(self, responses):
        self.ok = True
        self.c = MockClient(responses)

class MockPolygraph:
    def __init__(self, prov):
        # Подставим mock-провайдера в groq, чтобы _FC_PROVIDERS его подхватил первым
        self.providers = {"groq": prov, "openrouter": None, "cerebras": None, "mistral": None, "google": None}
    def route(self, msg):
        # Заглушка для финального fallback в Agent.run()
        return "[!] mock-fallback"


# ── Тест 1: простой ответ без инструментов ──────────────────────────
def test_simple_response():
    print("\n=== Тест 1: простой ответ без инструментов ===")
    prov = MockProvider([MockResp(MockMsg("Привет! 🙂"))])
    pg = MockPolygraph(prov)
    agent = Agent(pg, debug=False)
    result = agent.run("привет")
    print(f"Ответ: {result}")
    print(f"last_model: {agent.last_model}")
    print(f"last_messages ({len(agent.last_messages)}):")
    for m in agent.last_messages:
        print(f"  {m}")
    assert result == "Привет! 🙂", f"Ожидали 'Привет! 🙂', получили {result!r}"
    assert len(agent.last_messages) == 2, "Должно быть 2 сообщения: user + assistant"
    assert agent.last_messages[0]["role"] == "user"
    assert agent.last_messages[1]["role"] == "assistant"
    assert agent.last_messages[1]["content"] == "Привет! 🙂"
    print("✅ ОК")


# ── Тест 2: ответ с одним tool_call ─────────────────────────────────
def test_with_tool_call():
    print("\n=== Тест 2: ответ с вызовом инструмента ===")
    # Сначала модель просит вызвать calculator, потом отвечает текстом
    tc = MockToolCall("call_1", "calculator", {"expression": "2+2"})
    prov = MockProvider([
        MockResp(MockMsg("", tool_calls=[tc])),
        MockResp(MockMsg("Получилось 4 🙂")),
    ])
    pg = MockPolygraph(prov)
    agent = Agent(pg, debug=True)

    # Регистрируем инструмент calculator
    def calc(expression: str) -> str:
        return str(eval(expression, {"__builtins__":{}}, {}))
    agent.register(Tool(
        "calculator", "calc",
        {"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]},
        calc
    ))

    result = agent.run("сколько 2+2?")
    print(f"\nОтвет: {result}")
    print(f"\nlast_messages ({len(agent.last_messages)}):")
    for i, m in enumerate(agent.last_messages):
        role = m.get("role")
        if role == "tool":
            print(f"  [{i}] tool (id={m.get('tool_call_id')}): {m.get('content','')[:60]}")
        elif role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                print(f"  [{i}] assistant.tool_call: {tc['function']['name']}({tc['function']['arguments']})")
        else:
            print(f"  [{i}] {role}: {m.get('content','')[:80]}")

    assert result == "Получилось 4 🙂"
    assert len(agent.last_messages) == 4, f"Ожидали 4 сообщения (user, assistant-tool_call, tool, assistant), получили {len(agent.last_messages)}"
    assert agent.last_messages[0]["role"] == "user"
    assert agent.last_messages[1]["role"] == "assistant"
    assert "tool_calls" in agent.last_messages[1]
    assert agent.last_messages[1]["tool_calls"][0]["function"]["name"] == "calculator"
    assert agent.last_messages[2]["role"] == "tool"
    assert agent.last_messages[2]["content"] == "4"
    assert agent.last_messages[3]["role"] == "assistant"
    assert agent.last_messages[3]["content"] == "Получилось 4 🙂"
    print("✅ ОК")


# ── Тест 3: сброс last_messages между вызовами ──────────────────────
def test_reset_between_calls():
    print("\n=== Тест 3: сброс last_messages между вызовами ===")
    prov = MockProvider([
        MockResp(MockMsg("первый ответ")),
        MockResp(MockMsg("второй ответ")),
    ])
    pg = MockPolygraph(prov)
    agent = Agent(pg)
    agent.run("первый вопрос")
    assert agent.last_messages[-1]["content"] == "первый ответ"
    first_len = len(agent.last_messages)
    agent.run("второй вопрос")
    assert agent.last_messages[-1]["content"] == "второй ответ"
    # last_messages должен содержать ТОЛЬКО второй turn, не накапливать.
    # NB: к user-message могут добавляться системные подсказки (про длину, ссылки),
    # поэтому проверяем startswith а не точное равенство.
    assert agent.last_messages[0]["content"].startswith("второй вопрос"), \
        f"last_messages должен начинаться со 'второй вопрос', а начинается с {agent.last_messages[0]}"
    print(f"first run: {first_len} msgs, second run: {len(agent.last_messages)} msgs")
    print("✅ ОК — last_messages сбрасывается на каждый run()")


if __name__ == "__main__":
    test_simple_response()
    test_with_tool_call()
    test_reset_between_calls()
    print("\n" + "=" * 50)
    print("✅ Все тесты Шага 1 прошли")
    print("=" * 50)
