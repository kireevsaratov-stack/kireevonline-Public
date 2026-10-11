// Проверка «Барабана» в настоящем Chrome без окна (временный профиль), в реальном времени.
// Запуск: node spin_check.mjs [ширина] [высота] [прогонов]
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const [W = 1280, Hh = 900, RUNS = 3] = process.argv.slice(2).map(Number);
const PORT = 9333;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-2`,
  '--no-first-run', `--window-size=${W},${Hh}`,
  '--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND',
  'about:blank',
], { stdio: 'ignore' });

try {
  let pages;
  for (let i = 0; i < 50; i++) {
    try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {}
    await sleep(200);
  }
  const page = pages.find(p => p.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let id = 0; const wait = new Map();
  ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } });
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

  await send('Page.enable');
  await send('Page.navigate', { url: 'http://localhost:8100/shuffle/' });
  await sleep(5000);
  const results = [];
  for (let run = 1; run <= RUNS; run++) {
    const r = await send('Runtime.evaluate', { awaitPromise: true, returnByValue: true, expression: `(${measure.toString()})()` });
    results.push(r.result.result ? r.result.result.value : r.result);
    await sleep(1500);
  }
  console.log(JSON.stringify(results, null, 1));
  ws.close();
} finally {
  chrome.kill();
}

// выполняется внутри страницы
function measure() {
  return new Promise(resolve => {
    window.scrollTo(0, 0);
    const masonry = document.getElementById('masonry');
    const reels = [...document.querySelectorAll('.reel')], strips = reels.map(r => r.firstElementChild);
    const H = reels[0].clientHeight;
    const firstBefore = masonry.querySelector('.photo-item').dataset.id;
    const ev = [], t0 = performance.now(), T = () => Math.round(performance.now() - t0);
    const has = n => ev.some(e => e[1] === n);
    const mo1 = new MutationObserver(() => { if (!has('сетка собрана') && masonry.querySelector('.photo-item').dataset.id !== firstBefore) ev.push([T(), 'сетка собрана']); });
    mo1.observe(masonry, { childList: true });
    let rectsAtReveal = null;
    const rects = () => JSON.stringify([...masonry.querySelectorAll('.photo-item')].slice(0, 6).map(el => [el.offsetLeft, el.offsetTop, el.offsetWidth, el.offsetHeight].join(',')));
    const mo2 = new MutationObserver(() => {
      if (has('нажали') && !has('сетка проявилась') && !masonry.classList.contains('is-spinning')) {
        const imgs = [...masonry.querySelectorAll('.photo-item img')].slice(0, 6);
        ev.push([T(), 'сетка проявилась', imgs.filter(i => i.complete && i.naturalWidth).length + '/6 фото загружено']);
        rectsAtReveal = rects();
      }
    });
    mo2.observe(masonry, { attributes: true, attributeFilter: ['class'] });
    const S = [];
    ev.push([T(), 'нажали']);
    document.querySelector('.js-spin').click();
    (function loop() {
      const t = T();
      S.push([t, strips.map(s => -new DOMMatrix(getComputedStyle(s).transform).m42), parseFloat(getComputedStyle(masonry).opacity)]);
      if (t < 7200) requestAnimationFrame(loop); else done();
    })();
    function done() {
      mo1.disconnect(); mo2.disconnect();
      const res = { H, события: ev, кадров: S.length };
      let gap = 0, gapAt = 0;
      for (let i = 1; i < S.length; i++) { const g = S[i][0] - S[i - 1][0]; if (g > gap) { gap = g; gapAt = S[i - 1][0]; } }
      res['самый долгий кадр'] = Math.round(gap) + ' мс на ' + gapAt + ' мс';
      res['барабан тронулся, мс'] = strips.map((s, k) => { const i = S.findIndex(x => x[1][k] > 0.01); return i < 0 ? null : S[i][0]; });
      res['барабан встал, мс'] = strips.map((s, k) => { let t = 0; for (let i = 1; i < S.length; i++) if (Math.abs(S[i][1][k] - S[i - 1][1][k]) > 0.01) t = S[i][0]; return t; });
      res['макс. скорость, px/кадр'] = strips.map((s, k) => { let m = 0; for (let i = 1; i < S.length; i++) { const dt = S[i][0] - S[i - 1][0]; if (dt > 0) m = Math.max(m, (S[i][1][k] - S[i - 1][1][k]) / dt * 1000 / 60); } return +m.toFixed(1); });
      res['итог от цели, px'] = S[S.length - 1][1].map(v => +(v - 26 * H).toFixed(2));
      res['сетка видна во время вращения (макс. прозрачность 0,7–2,5 с)'] = Math.max(...S.filter(x => x[0] > 700 && x[0] < 2500).map(x => x[2]));
      const grid = [...masonry.querySelectorAll('.photo-item img')].slice(0, 3).map(i => i.getAttribute('src'));
      res['в окошках первые 3 кадра сетки'] = JSON.stringify(grid) === JSON.stringify(reels.map(r => r.dataset.src));
      res['кнопка снова свободна'] = !document.querySelector('.js-spin').dataset.busy;
      res['сетка не прыгнула после появления'] = rectsAtReveal === rects();
      resolve(res);
    }
  });
}
