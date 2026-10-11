// Клавиатура: фото и раскрытие меню доступны клавишей Tab, открываются Enter, просмотр закрывается Esc.
// Сам сообщает «прошло / не прошло» (код выхода). Запуск: node keyboard_check.mjs [адрес альбома]
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const URL_ = process.argv[2] || 'http://localhost:8100/album/9/';
const PORT = 9353;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-keys`,
  '--no-first-run', '--window-size=1280,900', 'about:blank',
], { stdio: 'ignore' });
const problems = [];
const check = (ok, what) => { console.log((ok ? '✔ ' : '✖ ') + what); if (!ok) problems.push(what); };
try {
  let pages;
  for (let i = 0; i < 50; i++) { try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {} await sleep(200); }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let n = 0; const wait = new Map();
  ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } });
  const send = (method, params = {}) => new Promise(r => { const i = ++n; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async e => (await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result.result?.value;
  const key = async (k, code) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: k, code, windowsVirtualKeyCode: { Tab: 9, Enter: 13, Escape: 27 }[k] }); };
  await send('Page.enable'); await send('Network.setCacheDisabled', { cacheDisabled: true });
  await send('Page.navigate', { url: URL_ }); await sleep(3000);

  const info = await js(`(() => { const it=document.querySelector('.photo-item'); const acc=document.querySelector('.js-acc-toggle');
    return { tab: it && it.getAttribute('tabindex'), role: it && it.getAttribute('role'), label: it && it.getAttribute('aria-label'),
             acc: acc ? acc.getAttribute('tabindex') : 'нет на странице' }; })()`);
  check(info.tab === '0' && info.role === 'button' && !!info.label, `фото доступны клавишей Tab (${info.label})`);
  check(info.acc === '0' || info.acc === 'нет на странице', 'раскрытие меню доступно клавишей Tab');

  await js(`document.querySelector('.photo-item').focus(); 1`);
  await key('Enter', 'Enter'); await sleep(700);
  check(await js(`document.getElementById('lightbox').classList.contains('open')`), 'Enter открывает фото');
  await key('Escape', 'Escape'); await sleep(500);
  check(!(await js(`document.getElementById('lightbox').classList.contains('open')`)), 'Esc закрывает просмотр');
} finally {
  chrome.kill();
}
console.log(problems.length ? `\n✖ НЕ ПРОШЛО: ${problems.length}` : '\n✔ Всё прошло');
process.exit(problems.length ? 1 : 0);
