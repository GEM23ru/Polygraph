// Тест парсера fmt() — работаем со старым парсером (без <p>-тегов).
const fs = require('fs');
const html = fs.readFileSync(__dirname + '/web.py', 'utf-8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
const jsCode = scriptMatch[1];

// Вытаскиваем функции по их регуляркам
const eval2 = (name) => {
  const m = jsCode.match(new RegExp('function\\s+' + name + '\\s*\\([^)]*\\)\\s*{[\\s\\S]*?\\n}', 'g'));
  return m ? m[0] : null;
};

eval(eval2('esc'));
eval(eval2('renderTable'));
eval(eval2('fmt'));

let passed = 0, failed = 0;
function check(name, input, expectIncludes, expectNotIncludes){
  const result = fmt(input);
  let ok = true;
  for(const need of (expectIncludes||[])){
    if(!result.includes(need)){
      ok = false;
      console.log(`  ❌ "${name}": не нашёл "${need}"`);
      console.log(`     Получено: ${result.substring(0, 300)}`);
      break;
    }
  }
  if(ok){
    for(const bad of (expectNotIncludes||[])){
      if(result.includes(bad)){
        ok = false;
        console.log(`  ❌ "${name}": нашёл недопустимое "${bad}"`);
        console.log(`     Получено: ${result.substring(0, 300)}`);
        break;
      }
    }
  }
  if(ok){ console.log(`  ✅ ${name}`); passed++; }
  else { failed++; }
}

console.log('\n=== Тесты fmt() (старый парсер) ===\n');

// 1. Простой текст — остаётся без тегов (только esc)
check('простой текст', 'Привет', ['Привет'], ['<p>', '<br>']);

// 2. Жирный текст
check('жирный текст',
  'Это **очень** важно.',
  ['Это <b>очень</b> важно.'], []);

// 3. NEW! Заголовок # / ## → <h3>
check('## заголовок → h3',
  '## Что сделал автор?',
  ['<h3>Что сделал автор?</h3>'], ['<h4>']);

// 4. NEW! Заголовок ### → <h4>
check('### заголовок → h4',
  '### Подраздел',
  ['<h4>Подраздел</h4>'], ['<h3>']);

// 5. NEW! #### всё ещё работает как h4 (для совместимости со старыми чатами)
check('#### заголовок → h4',
  '#### Старый стиль',
  ['<h4>Старый стиль</h4>'], []);

// 6. NEW! Один # → h3
check('# заголовок → h3',
  '# Главное',
  ['<h3>Главное</h3>'], ['<h4>']);

// 7. Маркированный список
check('список',
  '- Один\n- Два',
  ['<ul>', '<li>Один</li>', '<li>Два</li>', '</ul>'], []);

// 8. Нумерованный список
check('нумерованный',
  '1. A\n2. B',
  ['<ol>', '<li>A</li>', '<li>B</li>', '</ol>'], []);

// 9. Таблица
check('таблица',
  '| A | B |\n|---|---|\n| 1 | 2 |',
  ['<table>', '<th>A</th>', '<td>1</td>'], []);

// 10. Реальный фрагмент со скрина — модель использует жирный И ##
check('смешанный текст',
  'Привет.\n\n## Что я делаю?\n\nПишу **программу** в **Python**.',
  ['<h3>Что я делаю?</h3>', 'Пишу <b>программу</b> в <b>Python</b>.'], []);

// 11. КРИТИЧНО: жирный текст внутри строки НЕ должен превращаться в заголовок
check('жирный НЕ заголовок',
  '**Hixfield** (агрегатор)',
  ['<b>Hixfield</b>'], ['<h3>', '<h4>']);

// 12. Ссылка
check('ссылка',
  'См. https://example.com',
  ['<a href="https://example.com"'], []);

// 13. Инлайн-код
check('код',
  'Команда `ls -la`',
  ['<code>ls -la</code>'], []);

// 14. NEW! Курсив *текст* → <i>
check('курсив *South Park*',
  'фильм в стиле *South Park* классный',
  ['<i>South Park</i>'], ['*South Park*']);

// 15. NEW! Курсив с скобками вокруг
check('курсив (*ChatGPT*)',
  'тип нейросети (*ChatGPT*)',
  ['<i>ChatGPT</i>'], ['*ChatGPT*']);

// 16. КРИТИЧНО: жирный **текст** не должен путаться с курсивом
check('жирный остаётся жирным',
  'это **жирный** а это *курсив*',
  ['<b>жирный</b>', '<i>курсив</i>'], []);

// 17. КРИТИЧНО: математика 2*3*4 НЕ должна стать курсивом
check('математика не курсив',
  'формула 2*3*4 = 24',
  ['2*3*4 = 24'], ['<i>']);

// 18. Несколько курсивов в одной строке
check('несколько курсивов',
  'есть *FixField* и *Perplexity* и *ChatGPT*',
  ['<i>FixField</i>', '<i>Perplexity</i>', '<i>ChatGPT</i>'], []);

// 19. NEW! Цитата "> текст" → <blockquote>
check('цитата простая',
  '> Это совет автора',
  ['<blockquote>Это совет автора</blockquote>'], []);

// 20. NEW! Многострочная цитата
check('цитата многострочная',
  '> Первая строка\n> Вторая строка',
  ['<blockquote>Первая строка<br>Вторая строка</blockquote>'], []);

// 21. NEW! Цитата с жирным
check('цитата с жирным',
  '> ⚠️ **Совет**: сохраняй файлы',
  ['<blockquote>', '<b>Совет</b>', '</blockquote>'], []);

// 22. НЕ цитата: > внутри текста, не в начале строки
check('> в середине НЕ цитата',
  'A > B это сравнение',
  ['A &gt; B'], ['<blockquote>']);

// 23. NEW! HR теперь не рендерится визуально (но в HTML остаётся)
//     Просто убедимся что код не падает
check('HR разделитель',
  'Текст\n\n---\n\nЕщё текст',
  ['<hr>'], []);  // в HTML <hr> есть, но CSS его прячет

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
