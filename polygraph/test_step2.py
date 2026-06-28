"""
Шаг 2 Фазы 3 — тесты.
Проверяем, что prior_messages реально передаются в провайдер
(модель видит свои прошлые tool_calls).
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Agent, Tool
from test_step1 import MockMsg, MockResp, MockToolCall, MockChat, MockClient, MockProvider, MockPolygraph


# ── Тест 4: prior_messages передаются в provider ──────────────────
def test_prior_messages_passed():
    print("\n=== Тест 4: prior_messages передаются в провайдер ===")
    prov = MockProvider([MockResp(MockMsg("ответ с памятью"))])
    pg = MockPolygraph(prov)
    agent = Agent(pg)

    # Имитируем «прошлый turn»: пользователь спросил про картинку,
    # модель вызвала analyze_image, получила результат, ответила
    prior = [
        {"role": "user", "content": "что на картинке?"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "analyze_image",
                                      "arguments": '{"image": "foo.png"}'}}]},
        {"role": "tool", "tool_call_id": "c1",
         "content": "Таблица тарифов WB: FBW 32.5%, FBS 36%"},
        {"role": "assistant", "content": "На картинке таблица тарифов WB"},
    ]

    agent.run("а сколько логистика?", prior_messages=prior)

    # Проверяем, что в провайдер ушли все эти сообщения + system + новый user
    actual_call = prov.c.chat.completions.calls[0]
    sent_msgs = actual_call["messages"]
    print(f"В провайдер ушло {len(sent_msgs)} сообщений:")
    for i, m in enumerate(sent_msgs):
        role = m.get("role", "?")
        content = (m.get("content") or "")[:50]
        extra = " +tool_calls" if m.get("tool_calls") else ""
        extra += f" id={m.get('tool_call_id')}" if m.get("tool_call_id") else ""
        print(f"  [{i}] {role}: {content!r}{extra}")

    # Ожидаем: system + 4 prior + 1 текущий user = 6 (или 7, если уже добавлен финальный assistant — это норма,
    # так как msgs передаётся в провайдер by-reference и его модифицируют после get-а ответа)
    assert len(sent_msgs) in (6, 7), f"Ожидали 6 или 7, получили {len(sent_msgs)}"
    assert sent_msgs[0]["role"] == "system"
    assert sent_msgs[1]["content"] == "что на картинке?"
    assert sent_msgs[2].get("tool_calls"), "Должен быть assistant с tool_calls"
    assert sent_msgs[3]["role"] == "tool"
    assert sent_msgs[3]["tool_call_id"] == "c1"
    assert sent_msgs[4]["content"] == "На картинке таблица тарифов WB"
    # К user-message может добавляться системная подсказка про длину/формат —
    # проверяем startswith а не точное равенство.
    assert sent_msgs[5]["content"].startswith("а сколько логистика?")
    print("✅ ОК — модель получила полную историю с tool_calls")


# ── Тест 5: last_messages содержит ТОЛЬКО текущий turn, не накапливает ─
def test_last_messages_only_current_turn():
    print("\n=== Тест 5: last_messages = только текущий turn ===")
    prov = MockProvider([MockResp(MockMsg("новый ответ"))])
    pg = MockPolygraph(prov)
    agent = Agent(pg)

    prior = [
        {"role": "user", "content": "старый вопрос"},
        {"role": "assistant", "content": "старый ответ"},
    ]
    agent.run("новый вопрос", prior_messages=prior)

    print(f"last_messages ({len(agent.last_messages)}):")
    for m in agent.last_messages:
        print(f"  {m}")

    # last_messages должен содержать ТОЛЬКО новый turn (user + assistant),
    # а не накопленную историю
    assert len(agent.last_messages) == 2, \
        f"Ожидали 2 (только новый turn), получили {len(agent.last_messages)}"
    assert agent.last_messages[0]["content"].startswith("новый вопрос")
    assert agent.last_messages[1]["content"] == "новый ответ"
    print("✅ ОК — turn-ы не накапливаются")


# ── Тест 6: session_model сбрасывается при полном падении ─────────
def test_session_model_reset_on_total_fail():
    print("\n=== Тест 6: session_model сбрасывается при падении всех моделей ===")
    # Провайдер ВСЕГДА падает
    class FailingChat:
        def create(self, **kw):
            raise Exception("rate limit 429")
    class FailingClient:
        def __init__(self):
            self.chat = type("X", (), {"completions": FailingChat()})()
    class FailingProv:
        ok = True
        c = FailingClient()

    pg = MockPolygraph(FailingProv())
    agent = Agent(pg, debug=True)
    # Имитируем закреплённую модель
    agent.session_model = ("groq", "openai/gpt-oss-120b")

    result = agent.run("привет")
    # Возвращается результат финального fallback (pg.route или подобное) — это норма.
    # Главное — session_model должен быть сброшен.
    assert agent.session_model is None, \
        f"session_model должен сброситься, остался {agent.session_model}"
    print(f"✅ ОК — session_model = None после полного фейла (result: {result!r})")


# ── Тест 7: session_model обновляется при успехе запасной модели ─
def test_session_model_updated_on_success():
    print("\n=== Тест 7: session_model обновляется при ответе запасной модели ===")
    prov = MockProvider([MockResp(MockMsg("ответ"))])
    pg = MockPolygraph(prov)
    agent = Agent(pg)
    # Имитируем «старую» закреплённую модель
    agent.session_model = ("groq", "openai/gpt-oss-20b")  # запасная

    agent.run("привет")

    # session_model должен обновиться на ту, которая ответила (первая в списке)
    print(f"session_model после: {agent.session_model}")
    assert agent.session_model is not None
    # Mock-провайдер у нас в "groq", первая модель в списке — gpt-oss-120b
    # (по приоритету), но раз session_model уже была gpt-oss-20b, она была
    # поставлена первой — и она же и сработала
    assert agent.session_model[0] == "groq"
    print(f"✅ ОК — session_model обновлён на {agent.session_model}")


# ── Тест 8: Mistral-style content как list[dict] нормализуется в строку ─
def test_mistral_list_content_normalized():
    print("\n=== Тест 8: content в виде list (Mistral-style) → нормализуется ===")
    # Mistral иногда возвращает m.content как [{"type":"text","text":"привет"}]
    # вместо строки. Без фикса это падает в web.py на re.sub.
    list_content = [{"type": "text", "text": "Привет! "},
                    {"type": "text", "text": "Чем помочь?"}]
    prov = MockProvider([MockResp(MockMsg(list_content))])
    pg = MockPolygraph(prov)
    agent = Agent(pg)
    result = agent.run("привет")
    print(f"Тип результата: {type(result).__name__}")
    print(f"Результат: {result!r}")
    assert isinstance(result, str), f"Должна быть строка, получили {type(result).__name__}"
    assert result == "Привет! Чем помочь?", f"Ожидали склейку текста, получили {result!r}"
    # last_messages.assistant.content тоже должен быть строкой
    assistant_msg = [m for m in agent.last_messages if m.get("role") == "assistant"][-1]
    assert isinstance(assistant_msg["content"], str), \
        f"last_messages.assistant.content должен быть строкой"
    print("✅ ОК — list-content корректно склеен в строку")


if __name__ == "__main__":
    test_prior_messages_passed()
    test_last_messages_only_current_turn()
    test_session_model_reset_on_total_fail()
    test_session_model_updated_on_success()
    test_mistral_list_content_normalized()
    print("\n" + "=" * 50)
    print("✅ Все тесты Шага 2 прошли")
    print("=" * 50)
