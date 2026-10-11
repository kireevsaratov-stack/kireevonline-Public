// Рычаг «Барабана»: снимки в покое, на трети хода, в нижней точке и на возврате; шарик не сжимается?
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const OUT = SP + 'lever/';
mkdirSync(OUT, { recursive: true });
const PORT = 9337;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-6`,
  '--no-first-run', '--window-size=1280,900',
  '--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND', 'about:blank',
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
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 3, mobile: false });
  await send('Page.navigate', { url: 'http://localhost:8100/shuffle/' });
  await sleep(4000);
  const rect = await js(`(() => { window.scrollTo(0,0); const r=document.querySelector('.slot').getBoundingClientRect(); return {x:r.right-40,y:r.top-20,width:56,height:r.height+40}; })()`);
  const shot = async name => { const s = await send('Page.captureScreenshot', { format: 'png', clip: { ...rect, scale: 1 } }); writeFileSync(OUT + name, Buffer.from(s.result.data, 'base64')); };
  await shot('0_rest.png');
  const knob = () => js(`(() => { const l=document.querySelector('.lever'); const cs=getComputedStyle(l,'::before'), ca=getComputedStyle(l,'::after'); return {шарик: cs.transform + ' ' + cs.width + '×' + cs.height, стержень: ca.transform}; })()`);
  console.log('в покое:', JSON.stringify(await knob()));
  await js(`document.querySelector('.js-spin').click(); 1`);
  for (const [t, name] of [[120, '1_120ms.png'], [360, '2_360ms_bottom.png'], [650, '3_650ms.png'], [900, '4_900ms.png']]) {
    await js(`(() => { document.getAnimations().filter(a => a.animationName && a.animationName.startsWith('lever')).forEach(a => { a.pause(); a.currentTime = ${t}; }); return 1; })()`);
    await sleep(150);
    await shot(name);
    console.log(t + ' мс:', JSON.stringify(await knob()));
  }
  ws.close();
} finally { chrome.kill(); }
