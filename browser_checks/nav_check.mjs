// Верхнее меню на разных ширинах: гость и админ. Пункты не переносятся? Меню влезает или свёрнуто в гамбургер?
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const SESSION = readFileSync(SP + 'staff_session.txt', 'utf8').trim();
const PORT = 9340;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-9`,
  '--no-first-run', '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore' });
try {
  let pages;
  for (let i = 0; i < 50; i++) { try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {} await sleep(200); }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let id = 0; const wait = new Map();
  ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } });
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result?.value;
  await send('Network.enable');
  for (const role of ['гость', 'админ']) {
    const PAGE = role === 'админ' ? 'http://localhost:8100/static/_nav_admin.html' : 'http://localhost:8100/';
    for (const W of [1440, 1280, 1100, 1000, 900, 800, 770, 412]) {
      await send('Emulation.setDeviceMetricsOverride', { width: W, height: 800, deviceScaleFactor: 2, mobile: W < 700 });
      await send('Page.navigate', { url: PAGE });
      await sleep(3500);
      const r = await js(`(async () => { if (document.fonts) await document.fonts.ready; await new Promise(r => setTimeout(r, 300));
        const h = document.querySelector('.js-header'); const navH = h.offsetHeight;
        const links = [...h.querySelectorAll('.menu-list > .menu-item > .link')];
        const compact = h.classList.contains('nav-compact'), burger = getComputedStyle(h.querySelector('.nav-toggle')).display !== 'none';
        const wrapped = burger ? 0 : links.filter(a => a.getBoundingClientRect().height > navH + 1).length;
        const list = h.querySelector('.menu-list').getBoundingClientRect(), inner = h.querySelector('.inner').getBoundingClientRect();
        const fits = burger || list.right <= inner.right - 1;
        return {пунктов: links.length, гамбургер: burger, nav_compact: compact, переносов: wrapped, влезает: fits}; })()`);
      console.log(`${role} ${W}px:`, JSON.stringify(r));
      if ((role === 'админ' && W === 1000) || (role === 'гость' && W === 800)) {
        const s = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: W, height: 120, scale: 1 } });
        writeFileSync(SP + `nav_${role === 'админ' ? 'admin' : 'guest'}_${W}.png`, Buffer.from(s.result.data, 'base64'));
        await js(`document.querySelector('.js-nav-toggle').click(); 1`);
        await sleep(600);
        const s2 = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: W, height: 560, scale: 1 } });
        writeFileSync(SP + `nav_${role === 'админ' ? 'admin' : 'guest'}_${W}_open.png`, Buffer.from(s2.result.data, 'base64'));
      }
    }
  }
  ws.close();
} finally { chrome.kill(); }
