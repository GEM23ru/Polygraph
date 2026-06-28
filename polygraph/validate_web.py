#!/usr/bin/env python3
"""
Валидатор web.py — гоняем перед каждой сборкой UI-правок.

Проверки (в порядке возрастания строгости):
1. py_compile самого web.py
2. Python извлекает PAGE = "..." и распарсивает её
3. В скомпилированном PAGE: нет реальных переносов строк ВНУТРИ JS-строковых литералов и regex
   (это была главная боль 10 июня — \n в Python-литерале JS превращался в реальный перенос)
4. Node.js принимает извлечённый JS как валидный синтаксис (new Function(js))
5. jsdom: реально загружаем HTML, проверяем что chatList отрисовался

Использование:
    python3 validate_web.py
Exit code 0 если всё ок, 1 если что-то упало.
"""
import sys, os, re, subprocess, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_PY = os.path.join(SCRIPT_DIR, 'web.py')

def fail(stage, msg):
    print(f"❌ {stage}: {msg}")
    sys.exit(1)

def ok(stage):
    print(f"✅ {stage}")

# === 1) py_compile ===
result = subprocess.run([sys.executable, '-m', 'py_compile', WEB_PY],
                        capture_output=True, text=True)
if result.returncode != 0:
    fail("py_compile", result.stderr or result.stdout)
ok("py_compile")

# === 2) Извлечение PAGE ===
text = open(WEB_PY, encoding='utf-8').read()
m = re.search(r'PAGE\s*=\s*"""(.*?)"""', text, re.DOTALL)
if not m:
    fail("PAGE extraction", "не нашёл PAGE = \"\"\"...\"\"\" в web.py")
page_raw = m.group(1)
try:
    ns = {}
    exec(f'PAGE = """{page_raw}"""', ns)
    page = ns['PAGE']
except Exception as e:
    fail("PAGE parsing", str(e))
ok("PAGE extraction")

# === 3) Проверка JS-литералов на разорванность ===
sm = re.search(r'<script>(.*?)</script>', page, re.DOTALL)
if not sm:
    fail("JS extraction", "не нашёл <script>...</script> внутри PAGE")
js = sm.group(1)

# Идём по строкам JS — все строковые литералы должны закрываться на той же строке
# (template literals `...` могут переноситься — их пока не используем)
js_lines = js.split('\n')
broken_strings = []
for i, ln in enumerate(js_lines, 1):
    in_str = None
    j = 0
    while j < len(ln):
        c = ln[j]
        if c == '\\':
            j += 2
            continue
        if in_str:
            if c == in_str:
                in_str = None
        else:
            if c in ("'", '"'):
                in_str = c
            elif c == '/' and j+1 < len(ln) and ln[j+1] == '/':
                break  # line comment
        j += 1
    if in_str:
        broken_strings.append((i, ln.strip()[:100]))
if broken_strings:
    msg = "разорваны строковые литералы:\n"
    for i, ln in broken_strings:
        msg += f"   JS строка {i}: {ln}\n"
    fail("JS string literals", msg)
ok("JS string literals (нет переносов внутри строк)")

# === 4) Node.js синтаксис ===
result = subprocess.run(
    ['node', '-e', f'try {{ new Function({json.dumps(js)}); console.log("OK"); }} catch(e) {{ console.error("ERR:" + e.message); process.exit(1); }}'],
    capture_output=True, text=True, timeout=15
)
if result.returncode != 0:
    fail("Node syntax", (result.stderr or result.stdout).strip())
ok("Node.js синтаксис JS")

# === 5) jsdom рендеринг ===
test_browser = os.path.join(SCRIPT_DIR, 'test_browser.js')
if os.path.exists(test_browser):
    # Проверим, что jsdom есть
    check = subprocess.run(['node', '-e', 'require("jsdom")'], capture_output=True, text=True, cwd=SCRIPT_DIR)
    if check.returncode != 0:
        print("⚠️  jsdom не установлен — пропускаю браузерный тест. (npm install jsdom)")
    else:
        result = subprocess.run(['node', test_browser], capture_output=True, text=True, timeout=15, cwd=SCRIPT_DIR)
        if '✅ UI отрисовался корректно' not in result.stdout:
            fail("jsdom render", (result.stdout + result.stderr)[-500:])
        ok("jsdom рендеринг (chatList, status)")
else:
    print("⚠️  test_browser.js не найден — пропускаю браузерный тест")

print()
print("🟢 Все проверки прошли — web.py готов к сборке zip")
