"""
Шаг 3 Фазы 3 — тесты конвертера OpenAI messages → Gemini contents.

Проверяем, что _openai_msgs_to_gemini корректно преобразует
все типы сообщений (user, assistant с tool_calls, tool-результат).

Без реального обращения к Gemini API — просто проверяем структуру выхода.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Agent
from test_step1 import MockPolygraph, MockProvider, MockResp, MockMsg


# Проверим, доступен ли google-genai (он нужен для конвертера).
# Если нет — тесты пропустятся (это нормально на машине без зависимости).
try:
    from google.genai import types as gt
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    print("⚠️ google-genai не установлен — тесты Шага 3 пропущены.")


def make_agent():
    """Создаёт Agent с мок-провайдером, чтобы можно было дёргать методы."""
    prov = MockProvider([MockResp(MockMsg("ok"))])
    pg = MockPolygraph(prov)
    return Agent(pg)


def test_convert_simple_user():
    print("\n=== Тест 8: конвертер — простой user-message ===")
    agent = make_agent()
    msgs = [{"role": "user", "content": "привет"}]
    contents = agent._openai_msgs_to_gemini(msgs)
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert len(contents[0].parts) == 1
    # text есть в части
    assert contents[0].parts[0].text == "привет"
    print("✅ ОК")


def test_convert_assistant_text():
    print("\n=== Тест 9: конвертер — assistant с обычным текстом ===")
    agent = make_agent()
    msgs = [
        {"role": "user", "content": "2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    contents = agent._openai_msgs_to_gemini(msgs)
    assert len(contents) == 2
    assert contents[0].role == "user"
    assert contents[1].role == "model"  # в Gemini assistant = "model"
    assert contents[1].parts[0].text == "4"
    print("✅ ОК")


def test_convert_tool_call_and_response():
    print("\n=== Тест 10: конвертер — assistant tool_call + tool response ===")
    agent = make_agent()
    msgs = [
        {"role": "user", "content": "что на картинке?"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "analyze_image",
                                      "arguments": '{"image": "foo.png"}'}}]},
        {"role": "tool", "tool_call_id": "c1",
         "content": "Таблица тарифов: FBS 36%"},
        {"role": "assistant", "content": "На скриншоте таблица тарифов WB"},
    ]
    contents = agent._openai_msgs_to_gemini(msgs)
    assert len(contents) == 4, f"Ожидали 4 Content, получили {len(contents)}"

    # [0] user
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "что на картинке?"

    # [1] model с function_call (текста нет, только call)
    assert contents[1].role == "model"
    fc_part = contents[1].parts[0]
    assert hasattr(fc_part, "function_call") and fc_part.function_call is not None
    assert fc_part.function_call.name == "analyze_image"
    # args — словарь
    args = dict(fc_part.function_call.args)
    assert args == {"image": "foo.png"}, f"args={args!r}"

    # [2] tool response (Gemini ставит роль "user" для function_response)
    assert contents[2].role == "user"
    fr_part = contents[2].parts[0]
    assert hasattr(fr_part, "function_response") and fr_part.function_response is not None
    assert fr_part.function_response.name == "analyze_image"
    # ВНИМАНИЕ: response.response может быть proto, проверим как dict
    resp_field = dict(fr_part.function_response.response)
    assert resp_field == {"result": "Таблица тарифов: FBS 36%"}, f"resp={resp_field!r}"

    # [3] model с финальным текстом
    assert contents[3].role == "model"
    assert contents[3].parts[0].text == "На скриншоте таблица тарифов WB"

    print("✅ ОК — tool_call ↔ tool_response корректно сопоставлены")


def test_convert_system_skipped():
    print("\n=== Тест 11: конвертер — system сообщение пропускается ===")
    agent = make_agent()
    msgs = [
        {"role": "system", "content": "Ты — помощник."},
        {"role": "user", "content": "привет"},
    ]
    contents = agent._openai_msgs_to_gemini(msgs)
    # system должен быть пропущен — только user
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "привет"
    print("✅ ОК — system пропущен (он идёт в system_instruction отдельно)")


def test_convert_empty_user_skipped():
    print("\n=== Тест 12: конвертер — пустой user пропускается ===")
    agent = make_agent()
    msgs = [
        {"role": "user", "content": ""},
        {"role": "user", "content": "привет"},
    ]
    contents = agent._openai_msgs_to_gemini(msgs)
    # пустой пропущен
    assert len(contents) == 1
    assert contents[0].parts[0].text == "привет"
    print("✅ ОК")


def test_convert_assistant_text_plus_tool_call():
    print("\n=== Тест 13: конвертер — assistant с текстом И tool_call одновременно ===")
    agent = make_agent()
    msgs = [
        {"role": "user", "content": "посчитай 2+2 и скажи привет"},
        {"role": "assistant", "content": "Сейчас посчитаю.",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "calculator",
                                      "arguments": '{"expression": "2+2"}'}}]},
    ]
    contents = agent._openai_msgs_to_gemini(msgs)
    assert len(contents) == 2
    # У assistant — две части: текст + function_call
    parts = contents[1].parts
    assert len(parts) == 2
    assert hasattr(parts[0], "text") and parts[0].text == "Сейчас посчитаю."
    assert hasattr(parts[1], "function_call") and parts[1].function_call.name == "calculator"
    print("✅ ОК — текст и tool_call оба попали в один Content")


if __name__ == "__main__":
    if not HAS_GENAI:
        print("Пропускаем тесты Шага 3 — нет google-genai.")
        sys.exit(0)
    test_convert_simple_user()
    test_convert_assistant_text()
    test_convert_tool_call_and_response()
    test_convert_system_skipped()
    test_convert_empty_user_skipped()
    test_convert_assistant_text_plus_tool_call()
    print("\n" + "=" * 50)
    print("✅ Все тесты Шага 3 прошли")
    print("=" * 50)
