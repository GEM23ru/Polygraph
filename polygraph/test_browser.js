// Реальный браузерный тест через jsdom — имитируем полную загрузку страницы.
const fs = require('fs');
const { JSDOM } = require('jsdom');

const py = fs.readFileSync('./web.py', 'utf-8');
// PAGE = """...""" — вытащим
const m = py.match(/PAGE\s*=\s*"""([\s\S]*?)"""/);
if(!m){ console.error('PAGE не найдена'); process.exit(1); }
const fullHtml = m[1];

// Мокаем fetch чтобы вернуть тестовые чаты
const dom = new JSDOM(fullHtml, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:5000/',
  beforeParse(win) {
    win.fetch = (url, opts) => {
      const reply = (data) => Promise.resolve({
        json: () => Promise.resolve(data),
        ok: true, status: 200,
      });
      if(url === '/api/chats') return reply({chats:[
        {id:'abc', title:'Тестовый чат 1', ts:Date.now()},
        {id:'def', title:'Чат 2', ts:Date.now()-1000},
      ]});
      if(url === '/api/status') return reply({providers:[
        {name:'Mistral', ok:true},
        {name:'Groq (VPN)', ok:false, reason:'VPN?'},
      ]});
      if(url === '/api/stay') return reply({});
      if(url.startsWith('/api/chat/')) return reply({messages:[]});
      return reply({});
    };
  },
});

// Дадим скриптам отработать (там есть async)
setTimeout(() => {
  const errors = [];
  const win = dom.window;
  // Перехватываем все ошибки уже после загрузки — если что-то упало во время выполнения, jsdom выкинул в console
  // Проверим состояние DOM:
  const chatList = win.document.getElementById('chatList');
  const status = win.document.getElementById('status');
  const statusLabel = status?.querySelector('.label');

  console.log('=== Состояние UI после загрузки ===');
  console.log('chatList children:', chatList?.children?.length ?? 'NULL');
  console.log('chatList HTML:', (chatList?.innerHTML || '').substring(0, 200));
  console.log('status label text:', statusLabel?.textContent);
  console.log('status classes:', status?.className);

  // Если ошибок не было и список появился — всё ок
  const ok = chatList && chatList.children.length >= 1;
  if(ok){
    console.log('\n✅ UI отрисовался корректно');
    process.exit(0);
  } else {
    console.log('\n❌ chatList ПУСТ — UI сломан');
    process.exit(1);
  }
}, 500);

dom.window.addEventListener('error', e => {
  console.error('❌ Window error:', e.message);
});

// Перехватываем console.error из скриптов
const origErr = console.error;
dom.window.console.error = (...args) => {
  console.error('[browser]', ...args);
};
