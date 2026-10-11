// Ленты барабанов: у каждого свои картинки? Повторы подряд? Пересечения с прошлым вращением?
// И задержка старта. Chrome без окна (временный профиль), экран как у Fold, медленная сеть.
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const URL_ = process.argv[2] || 'http://localhost:8100/shuffle/';
const FIRST_WAIT = +(process.argv[3] || 6000);
const PORT = 9336;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-5`,
  '--no-first-run', '--window-size=412,915',
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
  await send('Network.enable');
  await send('Network.emulateNetworkConditions', { offline: false, latency: 120, downloadThroughput: 1000 * 1024, uploadThroughput: 300 * 1024 });
  await send('Emulation.setDeviceMetricsOverride', { width: 412, height: 915, deviceScaleFactor: 2.6, mobile: true });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  await send('Page.navigate', { url: URL_ });
  await sleep(FIRST_WAIT);
  let prev = null;
  for (let run = 1; run <= 3; run++) {
    const r = await js(`new Promise(resolve => {
      window.scrollTo(0,0);
      const pool = [...document.querySelectorAll('#masonry .photo-item img')].filter(i=>i.complete&&i.naturalWidth).length;
      const t0 = performance.now(); let last = t0, gap = 0, gapAt = 0;
      document.querySelector('.js-spin').click();
      const strips = [...document.querySelectorAll('.reel .strip')].map(s => [...s.querySelectorAll('img')].map(i => i.getAttribute('src')));
      (function f(){ const now = performance.now(); if (now - last > gap) { gap = now - last; gapAt = last - t0; } last = now; if (now - t0 < 1500) requestAnimationFrame(f); else resolve({pool, strips, gap: Math.round(gap), gapAt: Math.round(gapAt)}); })();
    })`);
    // ленты: [текущий, 25 кадров, итоговый, буфер]
    const body = r.strips.map(s => s.slice(1, 26));
    const sets = body.map(s => new Set(s));
    const cross = [[0, 1], [1, 2], [0, 2]].map(([a, b]) => [...sets[a]].filter(u => sets[b].has(u)).length);
    const consecutive = body.map(s => s.filter((u, i) => i && u === s[i - 1]).length);
    const tailDistinct = body.map(s => new Set(s.slice(-8)).size);
    const all = new Set(body.flat());
    const fromPrev = prev ? [...all].filter(u => prev.has(u)).length : '—';
    console.log(`вращение ${run}: загружено превью ${r.pool} | разных картинок на барабан ${sets.map(s => s.size).join('/')} | общих у соседей ${cross.join('/')} | повторов подряд ${consecutive.join('/')} | разных среди 8 последних ${tailDistinct.join('/')} | из прошлого вращения ${fromPrev} | самый долгий кадр ${r.gap} мс на ${r.gapAt} мс`);
    prev = all;
    await sleep(7000);
  }
  const g = await js(`(() => { const sh=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden) img')]; return {показано: sh.length, загружено: sh.filter(i=>i.complete&&i.naturalWidth).length, битых: sh.filter(i=>i.complete&&!i.naturalWidth&&i.getAttribute('src')).length}; })()`);
  console.log('сетка в конце:', JSON.stringify(g));
  ws.close();
} finally { chrome.kill(); }
