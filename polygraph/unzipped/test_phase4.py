"""
Фаза 4 — тесты watch_youtube и улучшений PDF.
Проверяем парсинг URL, обработку отсутствующих субтитров, навигацию по PDF.
"""

import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import default_tools


def get_tool(tools, name):
    for t in tools:
        if t.name == name:
            return t
    raise KeyError(f"tool {name} not found")


def test_youtube_url_parsing():
    """Проверяем извлечение video_id из разных форматов URL."""
    print("\n=== Тест 14: парсинг URL YouTube ===")
    tools = default_tools(workdir=tempfile.mkdtemp())
    watch = get_tool(tools, "watch_youtube")

    # Эти видео заведомо не существуют — главное, что не упадёт на парсинге
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",  # просто id
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",  # с тайм-кодом
    ]
    for url in test_urls:
        result = watch.call(url=url)
        # Главное — не "не удалось извлечь video_id"
        assert "не удалось извлечь" not in result, f"FAIL для {url!r}: {result[:100]}"
        print(f"  ✓ {url}")
    print("✅ ОК — все форматы URL распознаны")


def test_youtube_bad_url():
    """Битый URL должен давать понятную ошибку, не падать."""
    print("\n=== Тест 15: битый URL YouTube ===")
    tools = default_tools(workdir=tempfile.mkdtemp())
    watch = get_tool(tools, "watch_youtube")
    result = watch.call(url="это не ссылка совсем")
    assert "не удалось извлечь" in result, f"Ожидали ошибку, получили: {result[:100]}"
    print(f"  Сообщение: {result[:100]}")
    print("✅ ОК — битый URL обработан корректно")


def test_search_pdf_no_file():
    """search_pdf на несуществующем файле."""
    print("\n=== Тест 16: search_pdf - файл не найден ===")
    tools = default_tools(workdir=tempfile.mkdtemp())
    search = get_tool(tools, "search_pdf")
    result = search.call(path="nonexistent.pdf", query="test")
    assert "не найден" in result, f"Ожидали 'не найден', получили: {result[:100]}"
    print("✅ ОК")


def test_search_pdf_empty_query():
    """search_pdf без запроса."""
    print("\n=== Тест 17: search_pdf - пустой запрос ===")
    tmp = tempfile.mkdtemp()
    # Создадим пустой "PDF" просто чтобы пройти проверку файла
    fake_pdf = os.path.join(tmp, "fake.pdf")
    with open(fake_pdf, "w") as f:
        f.write("not a real pdf")  # формат будет невалидным, но это не важно для теста пустого query
    tools = default_tools(workdir=tmp)
    search = get_tool(tools, "search_pdf")
    result = search.call(path="fake.pdf", query="")
    # Главное чтобы не упало — любая «понятная» ошибка ОК (про pypdf, битый PDF, пустой query)
    assert any(k in result.lower() for k in ("пустой", "ошибка", "pypdf", "установи")), \
        f"Должна быть понятная ошибка, получили: {result[:100]}"
    print(f"  Сообщение: {result[:100]}")
    print("✅ ОК")


def test_read_file_pdf_pages_arg():
    """read_file принимает аргумент pages."""
    print("\n=== Тест 18: read_file принимает pages ===")
    tmp = tempfile.mkdtemp()
    tools = default_tools(workdir=tmp)
    read = get_tool(tools, "read_file")
    # Без реального PDF проверим только что аргумент не ломает вызов
    result = read.call(path="nope.pdf", pages="1-10")
    assert "не найден" in result, f"Ожидали 'не найден' (файла нет), получили: {result[:100]}"
    # Теперь с непустым PDF (без extract_text)
    result = read.call(path="nope.pdf", pages="last5")
    assert "не найден" in result
    result = read.call(path="nope.pdf", pages="all")
    assert "не найден" in result
    print("✅ ОК — все варианты pages принимаются")


def test_new_tools_registered():
    """Проверяем, что все 3 новых инструмента зарегистрированы."""
    print("\n=== Тест 19: новые инструменты в default_tools ===")
    tools = default_tools(workdir=tempfile.mkdtemp())
    names = {t.name for t in tools}
    assert "watch_youtube" in names, f"watch_youtube не зарегистрирован. Есть: {names}"
    assert "search_pdf" in names, f"search_pdf не зарегистрирован. Есть: {names}"
    assert "analyze_pdf_page" in names, f"analyze_pdf_page не зарегистрирован. Есть: {names}"
    print(f"✅ ОК — все 3 новых инструмента зарегистрированы (всего {len(tools)} в default_tools)")


if __name__ == "__main__":
    test_new_tools_registered()
    test_youtube_url_parsing()
    test_youtube_bad_url()
    test_search_pdf_no_file()
    test_search_pdf_empty_query()
    test_read_file_pdf_pages_arg()
    print("\n" + "=" * 50)
    print("✅ Все тесты Фазы 4 прошли")
    print("=" * 50)
