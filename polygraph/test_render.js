const fs = require('fs');
const html = fs.readFileSync('./web.py', 'utf-8');
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// Минимальный DOM-эмулятор
const fakeEl = () => {
  const el = {
    _children: [], _attrs: {}, classList: { _set: new Set(), add(c){this._set.add(c);}, remove(c){this._set.delete(c);}, toggle(c){this._set.has(c)?this._set.delete(c):this._set.add(c);}, contains(c){return this._set.has(c);} },
    style: {}, _events: {}, innerHTML: '', textContent: '', value: '', scrollHeight: 0, scrollTop: 0, dataset: {},
    appendChild(c){ this._children.push(c); }, removeChild(c){}, remove(){}, contains(c){return false;},
    addEventListener(e,h){this._events[e]=h;}, removeEventListener(e,h){}, dispatchEvent(){},
    setAttribute(k,v){this._attrs[k]=v;}, getAttribute(k){return this._attrs[k];},
    querySelector(){return fakeEl();}, querySelectorAll(){return [];},
    onclick:null, focus(){}, click(){},
  };
  return el;
};

global.document = {
  getElementById: (id) => fakeEl(),
  querySelector: () => fakeEl(),
  querySelectorAll: () => [],
  createElement: () => fakeEl(),
  addEventListener: () => null,
  documentElement: { setAttribute: () => null, getAttribute: () => 'dark' },
};
global.window = { addEventListener: () => null, location:{} };
global.localStorage = { getItem: () => null, setItem: () => null };
global.navigator = { sendBeacon: () => null, clipboard: { writeText: () => Promise.resolve() } };
global.fetch = (url) => {
  // Симулируем ответ /api/chats и /api/status
  if(url === '/api/chats') return Promise.resolve({ json: () => Promise.resolve({chats:[{id:'1',title:'Тест чат',ts:0}]}) });
  if(url === '/api/status') return Promise.resolve({ json: () => Promise.resolve({providers:[{name:'Mistral',ok:true}]}) });
  if(url === '/api/stay') return Promise.resolve({ json: () => Promise.resolve({}) });
  return Promise.resolve({ json: () => Promise.resolve({}) });
};
global.setInterval = () => null;
global.setTimeout = (fn) => { try{fn();}catch(e){console.error('setTimeout err:', e.message);} return null; };
global.clearInterval = () => null;
global.confirm = () => true;
global.alert = (m) => console.log('alert:', m);
global.Event = class { constructor(t){this.type=t;} };
global.FormData = class { append(){} };

// Выполняем JS целиком
try {
  eval(js);
  console.log('JS RUNTIME: OK');
} catch(e) {
  console.error('JS RUNTIME ERROR:', e.message);
  console.error(e.stack.split('\n').slice(0,5).join('\n'));
}
