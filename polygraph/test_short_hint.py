"""
Тест: системная подсказка про длину добавляется к коротким размытым запросам,
но НЕ добавляется к длинным или к содержащим слова «подробно/гайд/план».
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Agent
from test_step1 import MockPolygraph, MockProvider, MockResp, MockMsg


def make_agent():
    prov = MockProvider([MockResp(MockMsg("ответ"))])
    return Agent(MockPolygraph(prov))


def get_last_user_msg(agent):
    """Что в итоге попало в user-сообщение, переданное модели."""
    for m in reversed(agent.last_messages):
        if m.get("role") == "user":
            return m["content"]
    return ""


def test_short_vague_gets_hint():
    """Короткий размытый вопрос → подсказка должна добавиться."""
    print("\n=== Тест: короткий размытый вопрос → подсказка ===")
    agent = make_agent()
    agent.run("как тебе прокачать навык дизайна?")  # 6 слов
    msg = get_last_user_msg(agent)
    print(f"User-msg: {msg[:150]}...")
    assert "[Система: вопрос короткий" in msg, "Подсказка должна быть!"
    print("✅ ОК — подсказка добавилась")


def test_long_no_hint():
    """Длинный (>15 слов) запрос → подсказку НЕ добавлять."""
    print("\n=== Тест: длинный вопрос → без подсказки ===")
    agent = make_agent()
    long_q = (
        "Объясни как работает квантовая криптография протокол BB84 "
        "и почему он считается стойким к атакам с точки зрения квантовой механики "
        "и какие у него ограничения в современных реализациях"
    )  # 30+ слов
    agent.run(long_q)
    msg = get_last_user_msg(agent)
    assert "[Система: вопрос короткий" not in msg, "Подсказки НЕ должно быть!"
    print(f"✅ ОК — подсказка НЕ добавлена (длина {len(long_q.split())} слов)")


def test_keyword_no_hint():
    """Короткий запрос со словом «подробно» → подсказку НЕ добавлять."""
    print("\n=== Тест: запрос со словом «подробно» → без подсказки ===")
    agent = make_agent()
    agent.run("расскажи подробно про Python")  # короткий, но пользователь явно хочет подробно
    msg = get_last_user_msg(agent)
    assert "[Система: вопрос короткий" not in msg, "Подсказки НЕ должно быть!"
    print("✅ ОК — подсказка НЕ добавлена (есть слово «подробно»)")


def test_gayd_keyword_no_hint():
    """Запрос со словом «гайд» → без подсказки."""
    print("\n=== Тест: запрос со словом «гайд» → без подсказки ===")
    agent = make_agent()
    agent.run("дай гайд по работе с WB")
    msg = get_last_user_msg(agent)
    assert "[Система: вопрос короткий" not in msg
    print("✅ ОК — подсказка НЕ добавлена (есть «гайд»)")


def test_youtube_hint_takes_priority():
    """YouTube-ссылка получает свою подсказку, длинной не добавляется."""
    print("\n=== Тест: YouTube-ссылка → только YouTube-подсказка ===")
    agent = make_agent()
    agent.run("https://youtu.be/abc1234XYZ_")  # 1 слово
    msg = get_last_user_msg(agent)
    assert "watch_youtube" in msg, "Должна быть YouTube-подсказка"
    assert "[Система: вопрос короткий" not in msg, \
        "Не должно быть подсказки про длину — она бы дублировала YouTube-подсказку"
    print("✅ ОК — только YouTube-подсказка")


if __name__ == "__main__":
    test_short_vague_gets_hint()
    test_long_no_hint()
    test_keyword_no_hint()
    test_gayd_keyword_no_hint()
    test_youtube_hint_takes_priority()
    print("\n" + "=" * 50)
    print("✅ Все тесты подсказки прошли")
    print("=" * 50)
