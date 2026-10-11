// Диагностика «Барабана» на живом сайте: Chrome без окна (временный профиль), как телефон на Android.
// Только просмотр страницы (GET), как обычный посетитель. Снимки окошек барабана и журнал загрузки картинок.
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const OUT = SP + (process.env.OUTDIR || 'diag') + '/';
mkdirSync(OUT, { recursive: true });
const URL_ = process.argv[2] || 'https://kireevonline.ru/shuffle/';
const PORT = 9334;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-3`,
  '--no-first-run', '--window-size=412,915',
  '--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND',
  'about:blank',
], { stdio: 'ignore' });

try {
  let pages;
  for (let i = 0; i < 50; i++) {
    try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {}
    await sleep(200);
  }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let id = 0; const wait = new Map(); const net = new Map(); let t0 = 0;
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); return; }
    const p = m.params || {};
    if (m.method === 'Network.requestWillBeSent' && /\.(jpe?g|png|webp)/i.test(p.request.url))
      net.set(p.requestId, { url: p.request.url.replace(/^https?:\/\/[^/]+/, ''), start: Date.now() - t0 });
    if (m.method === 'Network.responseReceived' && net.has(p.requestId)) Object.assign(net.get(p.requestId), { status: p.response.status, fromCache: p.response.fromDiskCache || p.response.fromMemoryCache });
    if (m.method === 'Network.loadingFinished' && net.has(p.requestId)) Object.assign(net.get(p.requestId), { end: Date.now() - t0, kb: Math.round(p.encodedDataLength / 1024) });
    if (m.method === 'Network.loadingFailed' && net.has(p.requestId)) Object.assign(net.get(p.requestId), { end: Date.now() - t0, failed: p.errorText + (p.canceled ? ' (отменён)' : '') });
  });
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJs = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result?.value;

  await send('Network.enable');
  await send('Page.enable');
  if (process.env.THROTTLE) await send('Network.emulateNetworkConditions', { offline: false, latency: 120, downloadThroughput: 1000 * 1024, uploadThroughput: 300 * 1024 });
  await send('Emulation.setDeviceMetricsOverride', { width: 412, height: 915, deviceScaleFactor: 2.6, mobile: true });
  await send('Emulation.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (Linux; Android 15; SM-F966B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36' });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  t0 = Date.now();
  await send('Page.navigate', { url: URL_ });
  await sleep(12000);
  const reqBefore = net.size;
  const before = await evalJs(`(() => { const imgs=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden) img')]; return {shown: imgs.length, loaded: imgs.filter(i=>i.complete&&i.naturalWidth).length, broken: imgs.filter(i=>i.complete&&!i.naturalWidth).length}; })()`);
  console.log('до вращения (12 с после открытия), сетка:', JSON.stringify(before), '| картинок запрошено при открытии:', reqBefore);

  const slotRect = await evalJs(`(() => { const r=document.querySelector('.slot').getBoundingClientRect(); window.scrollTo(0,0); return {x:r.left-6,y:r.top-6,width:r.width+12,height:r.height+12}; })()`);
  const clickAt = Date.now() - t0;
  await evalJs(`(() => { window.__finals=null; const orig=window.__spinAnimate; window.__spinAnimate=function(nf,done){ window.__finals=nf.map(el=>{const i=el.querySelector('img');return i.getAttribute('src')||i.dataset.src;}); return orig(nf,done); }; document.querySelector('.js-spin').click(); return 1; })()`);
  const shots = [];
  for (let i = 0; i < 20; i++) {
    const t = Date.now() - t0 - clickAt;
    const s = await send('Page.captureScreenshot', { format: 'png', clip: { ...slotRect, scale: 1 } });
    const name = `reel_${String(i).padStart(2, '0')}_${t}ms.png`;
    writeFileSync(OUT + name, Buffer.from(s.result.data, 'base64'));
    shots.push(name);
    await sleep(250);
  }
  await sleep(2500);
  const finals = await evalJs('window.__finals');
  const after = await evalJs(`(() => { const imgs=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden) img')]; return {shown: imgs.length, loaded: imgs.filter(i=>i.complete&&i.naturalWidth).length, broken: imgs.filter(i=>i.complete&&!i.naturalWidth).length, loading: imgs.filter(i=>!i.complete).length, revealed: !document.getElementById('masonry').classList.contains('is-spinning')}; })()`);
  console.log('после вращения, сетка:', JSON.stringify(after));
  const grid = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(OUT + 'grid_after.png', Buffer.from(grid.result.data, 'base64'));
  console.log('нажали на', clickAt, 'мс; снимков окошек:', shots.length);
  for (const f of finals || []) {
    const r = [...net.values()].filter(x => f.endsWith(x.url) || x.url.endsWith(f));
    console.log('итоговая картинка', f, '→', JSON.stringify(r.map(x => ({ начало_от_нажатия: x.start - clickAt, конец_от_нажатия: x.end - clickAt, kb: x.kb, status: x.status, cache: x.fromCache, failed: x.failed }))));
  }
  const all = [...net.values()];
  const bad = all.filter(x => x.failed || (x.status && x.status !== 200));
  const done = all.filter(x => x.end && !x.failed);
  console.log('картинок запрошено:', all.length, '| с ошибкой:', bad.length, bad.slice(0, 8).map(x => `${x.url} ${x.status || ''} ${x.failed || ''}`));
  if (done.length) {
    const d = done.map(x => x.end - x.start).sort((a, b) => a - b);
    const kb = done.map(x => x.kb).filter(Boolean).sort((a, b) => a - b);
    console.log('время загрузки, мс: медиана', d[d.length >> 1], 'макс', d[d.length - 1], '| размер, КБ: медиана', kb[kb.length >> 1], 'макс', kb[kb.length - 1]);
  }
  ws.close();
} finally {
  chrome.kill();
}
