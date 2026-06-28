const fs = require('fs');
const { JSDOM } = require('jsdom');
const py = fs.readFileSync('./web.py', 'utf-8');
const m = py.match(/PAGE\s*=\s*"""([\s\S]*?)"""/);
const fullHtml = m[1];

const dom = new JSDOM(fullHtml, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:5000/',
  beforeParse(win) {
    win.fetch = () => Promise.resolve({ json: () => Promise.resolve({chats:[],providers:[]}), ok:true });
    win.localStorage = { getItem: () => null, setItem: () => null };
  },
});

setTimeout(() => {
  const cards = dom.window.document.querySelectorAll('.card');
  console.log('=== Welcome cards ===');
  cards.forEach((c, i) => {
    const ttl = c.querySelector('.ttl')?.textContent || '?';
    const hasIco = !!c.querySelector('.ico svg');
    console.log(`  [${i}] "${ttl}" — иконка SVG: ${hasIco ? 'ДА' : 'НЕТ'}`);
  });

  const themeOpts = dom.window.document.querySelectorAll('.theme-toggle .opt');
  console.log('\n=== Theme toggle ===');
  console.log(`  Опций в переключателе: ${themeOpts.length}`);
  themeOpts.forEach((o, i) => {
    console.log(`  [${i}] data-theme-opt="${o.getAttribute('data-theme-opt')}" active=${o.classList.contains('active')}`);
  });
}, 500);
