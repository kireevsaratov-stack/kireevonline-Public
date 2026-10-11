// Альбом после правки загрузки: при открытии 40 превью, при прокрутке — следующие, без битых;
// кадр из догруженных открывается; на телефоне полный экран не включается. Chrome без окна, временный профиль.
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const URL_ = process.argv[2] || 'http://localhost:8100/album/9/';
const PHONE = process.argv[3] === 'phone';
const PORT = 9335;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-4`,
  '--no-first-run', '--window-size=1280,900',
  '--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND', 'about:blank',
], { stdio: 'ignore' });
try {
  let pages;
  for (let i = 0; i < 50; i++) { try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {} await sleep(200); }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let id = 0; const wait = new Map(); let imgReq = 0, imgFail = 0;
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); return; }
    if (m.method === 'Network.requestWillBeSent' && /\/media\/thumbs\//.test(m.params.request.url)) imgReq++;
    if (m.method === 'Network.loadingFailed') imgFail++;
  });
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result?.value;
  await send('Network.enable');
  if (PHONE) {
    await send('Emulation.setDeviceMetricsOverride', { width: 412, height: 915, deviceScaleFactor: 2.6, mobile: true });
    await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
    await send('Emulation.setEmitTouchEventsForMouse', { enabled: true, configuration: 'mobile' });
  }
  await send('Page.navigate', { url: URL_ });
  await sleep(6000);
  const state = () => js(`(() => { const items=[...document.querySelectorAll('#masonry .photo-item')]; const sh=items.filter(e=>!e.classList.contains('is-hidden')).map(e=>e.querySelector('img')); return {всего: items.length, показано: sh.length, загружено: sh.filter(i=>i.complete&&i.naturalWidth).length, битых: sh.filter(i=>i.complete&&!i.naturalWidth&&i.getAttribute('src')).length, видны_во_время_загрузки: sh.every(i=>getComputedStyle(i).opacity==='1')}; })()`);
  console.log('открыли альбом:', JSON.stringify(await state()), '| запросов превью:', imgReq);
  for (let i = 0; i < 4; i++) { await js('window.scrollTo(0, document.body.scrollHeight); 1'); await sleep(2500); }
  console.log('после прокрутки вниз:', JSON.stringify(await state()), '| запросов превью:', imgReq, '| сбоев:', imgFail);
  const lb = await js(`(() => { const items=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden)')]; const el=items[items.length-1]; el.scrollIntoView(); el.click(); return new Promise(r=>setTimeout(()=>r({просмотр_открыт: document.getElementById('lightbox').classList.contains('open'), кадр: (document.getElementById('lb-img').getAttribute('src')||'').split('/').pop(), счётчик: document.getElementById('lb-counter').textContent, полный_экран: !!document.fullscreenElement, мышь_или_тачпад: matchMedia('(hover:hover) and (pointer:fine)').matches}), 800)); })()`);
  console.log('открыли последний догруженный кадр:', JSON.stringify(lb));
  ws.close();
} finally { chrome.kill(); }
