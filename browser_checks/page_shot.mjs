// Снимок верха страницы альбома с раскрытыми записками. node page_shot.mjs URL ширина файл [телефон]
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const [URL_, W = '412', OUT = 'shot.png', PHONE] = process.argv.slice(2);
const PORT = 9338;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-7`,
  '--no-first-run', `--window-size=${W},900`, 'about:blank',
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
  await send('Emulation.setDeviceMetricsOverride', { width: +W, height: 900, deviceScaleFactor: +(process.env.SCALE || 2), mobile: !!PHONE });
  await send('Page.navigate', { url: URL_ });
  await sleep(5000);
  const h = await js(`(() => { document.querySelectorAll('.fade-in').forEach(e => e.classList.add('visible'));
    const t = document.querySelector('.js-intro-toggle'); if (t) t.click();
    return new Promise(r => setTimeout(() => { const el = document.querySelector('.album-intro') || document.querySelector('.about'); const b = el.getBoundingClientRect(); r(Math.ceil(b.bottom + window.scrollY + 40)); }, 900)); })()`);
  await send('Emulation.setDeviceMetricsOverride', { width: +W, height: h, deviceScaleFactor: +(process.env.SCALE || 2), mobile: !!PHONE });
  await sleep(800);
  const s = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: +W, height: h, scale: 1 } });
  writeFileSync(SP + OUT, Buffer.from(s.result.data, 'base64'));
  console.log('снимок', OUT, W + '×' + h);
  ws.close();
} finally { chrome.kill(); }
