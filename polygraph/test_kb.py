"""
Тест базы знаний: remember / recall / list_knowledge / forget.
"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import default_tools


def get_tool(tools, name):
    for t in tools:
        if t.name == name:
            return t
    raise KeyError(f"tool {name} not found")


def test_remember_creates_file():
    """remember создаёт файл и записывает данные."""
    print("\n=== Тест: remember создаёт knowledge.json ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    remember = get_tool(tools, "remember")

    result = remember.call(
        content="Тренды 2026: минимализм, бирюзовые акценты",
        topic="дизайн-тренды",
        tags="инфографика, тренды",
        source="youtu.be/abc123"
    )
    print(f"Результат: {result}")
    assert "Сохранено в базу" in result, f"Ожидали успех: {result}"

    # Проверим что файл создан
    kb_path = os.path.join(tmp, "knowledge.json")
    assert os.path.exists(kb_path), "Файл knowledge.json не создан"

    with open(kb_path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1, f"Ожидали 1 запись, есть {len(data)}"
    assert data[0]["topic"] == "дизайн-тренды"
    assert data[0]["content"] == "Тренды 2026: минимализм, бирюзовые акценты"
    assert "инфографика" in data[0]["tags"]
    print("✅ ОК — файл создан, запись сохранена правильно")


def test_recall_finds_by_word():
    """recall находит запись по словам."""
    print("\n=== Тест: recall ищет по словам ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    remember = get_tool(tools, "remember")
    recall = get_tool(tools, "recall")

    remember.call(content="FBS парфюм на WB 36%", topic="wb-тарифы", tags="парфюм, fbs")
    remember.call(content="FBW парфюм на WB 32.5%", topic="wb-тарифы", tags="парфюм, fbw")
    remember.call(content="Тренды дизайна: минимализм", topic="дизайн", tags="тренды")

    # Ищем "парфюм" — должно найти первые две
    result = recall.call(query="парфюм")
    print(f"Поиск 'парфюм': найдено упоминаний — {result.count('[k_')}")
    assert "k_0001" in result, "Должна быть найдена k_0001 (FBS парфюм)"
    assert "k_0002" in result, "Должна быть найдена k_0002 (FBW парфюм)"
    assert "k_0003" not in result, "k_0003 (дизайн) не должна найтись по 'парфюм'"
    print("✅ ОК — найдены только релевантные записи")


def test_recall_empty_base():
    """recall на пустой базе."""
    print("\n=== Тест: recall на пустой базе ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    recall = get_tool(tools, "recall")
    result = recall.call(query="что угодно")
    assert "пуста" in result
    print("✅ ОК — корректное сообщение для пустой базы")


def test_list_knowledge():
    """list_knowledge показывает группировку по темам."""
    print("\n=== Тест: list_knowledge ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    remember = get_tool(tools, "remember")
    list_kb = get_tool(tools, "list_knowledge")

    remember.call(content="A", topic="тема1")
    remember.call(content="B", topic="тема1")
    remember.call(content="C", topic="тема2")

    result = list_kb.call()
    print(result)
    assert "тема1 (2)" in result, "Должна быть тема1 с 2 записями"
    assert "тема2 (1)" in result, "Должна быть тема2 с 1 записью"
    print("✅ ОК — группировка по темам работает")


def test_forget():
    """forget удаляет запись по id."""
    print("\n=== Тест: forget ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    remember = get_tool(tools, "remember")
    forget = get_tool(tools, "forget")
    recall = get_tool(tools, "recall")

    remember.call(content="Запись 1", topic="т")
    remember.call(content="Запись 2", topic="т")

    result = forget.call(record_id="k_0001")
    assert "удалена" in result, f"Ожидали удаление: {result}"

    # k_0001 не должна больше находиться
    found = recall.call(query="Запись")
    assert "k_0001" not in found
    assert "k_0002" in found
    print("✅ ОК — запись удалена, остальные на месте")


def test_forget_nonexistent():
    """forget на несуществующий id."""
    print("\n=== Тест: forget несуществующего id ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    forget = get_tool(tools, "forget")
    result = forget.call(record_id="k_9999")
    assert "не найдена" in result
    print("✅ ОК")


def test_persistence():
    """База сохраняется между разными вызовами default_tools."""
    print("\n=== Тест: персистентность ===")
    tmp = tempfile.mkdtemp()

    # Первый "сеанс" — сохраняем
    tools1 = default_tools(workdir=tmp)
    get_tool(tools1, "remember").call(content="Сохранено в сеансе 1", topic="т")

    # Второй "сеанс" — читаем
    tools2 = default_tools(workdir=tmp)
    result = get_tool(tools2, "recall").call(query="Сохранено")
    assert "Сохранено в сеансе 1" in result, "База не сохранилась между сеансами"
    print("✅ ОК — данные сохраняются между перезапусками")


if __name__ == "__main__":
    test_remember_creates_file()
    test_recall_finds_by_word()
    test_recall_empty_base()
    test_list_knowledge()
    test_forget()
    test_forget_nonexistent()
    test_persistence()
    print("\n" + "=" * 50)
    print("✅ Все тесты базы знаний прошли")
    print("=" * 50)
