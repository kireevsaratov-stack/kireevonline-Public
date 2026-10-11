// Ленты барабанов на телефоне (экран как у Fold, медленная сеть): у каждого барабана свои картинки,
// одна и та же не мелькает в двух сразу, подряд кадры не повторяются, следующее вращение берёт в
// первую очередь другие картинки; старт без зависания; в конце битых превью нет.
// Сам сообщает «прошло / не прошло». Запуск: node reel_unique_check.mjs [адрес] [пауза перед первым вращением, мс]
import { main, openChrome, sleep } from './lib.mjs';

const URL_ = process.argv[2] || '/shuffle/';
const FIRST_WAIT = +(process.argv[3] || 6000);
const MAX_GAP = 400;   // мс — как в spin_check (там же — почему столько)

await main('ленты барабанов (телефон)', async t => {
  const page = await openChrome({ width: 412, height: 915, scale: 2.6, mobile: true });
  await page.send('Network.enable');
  await page.send('Network.emulateNetworkConditions', { offline: false, latency: 120, downloadThroughput: 1000 * 1024, uploadThroughput: 300 * 1024 });
  await page.navigate(URL_, FIRST_WAIT);
  let prev = null;
  for (let run = 1; run <= 3; run++) {
    const r = await page.js(`new Promise(resolve => {
      window.scrollTo(0,0);
      const pool = [...document.querySelectorAll('#masonry .photo-item img')].filter(i=>i.complete&&i.naturalWidth).length;
      const t0 = performance.now(); let last = t0, gap = 0, gapAt = 0;
      document.querySelector('.js-spin').click();
      const strips = [...document.querySelectorAll('.reel .strip')].map(s => [...s.querySelectorAll('img')].map(i => i.getAttribute('src')));
      (function f(){ const now = performance.now(); if (now - last > gap) { gap = now - last; gapAt = last - t0; } last = now; if (now - t0 < 1500) requestAnimationFrame(f); else resolve({pool, strips, gap: Math.round(gap), gapAt: Math.round(gapAt)}); })();
    })`);
    // лента: [текущий, 25 своих кадров, итоговый, кадр под итоговым]
    const body = r.strips.map(s => s.slice(1, 26));
    const sets = body.map(s => new Set(s));
    const cross = [[0, 1], [1, 2], [0, 2]].map(([a, b]) => [...sets[a]].filter(u => sets[b].has(u)).length);
    const consecutive = body.map(s => s.filter((u, i) => i && u === s[i - 1]).length);
    const all = new Set(body.flat());
    const fromPrev = prev ? [...all].filter(u => prev.has(u)).length : null;
    const p = `вращение ${run}:`;
    t.info(p, `загружено превью ${r.pool} | разных на барабан ${sets.map(s => s.size).join('/')} | из прошлого вращения ${fromPrev ?? '—'} | самый долгий кадр ${r.gap} мс на ${r.gapAt} мс`);
    t.ok(body.every(s => s.length === 25 && s.every(Boolean)), `${p} у каждого барабана лента из 25 кадров`);
    t.ok(cross.every(c => c === 0), `${p} ни одна картинка не попала в два барабана сразу`, 'общих у соседей ' + cross.join('/'));
    // подряд одинаковые допустимы, только если на барабан досталась одна картинка (превью почти не загрузились)
    t.ok(sets.every((s, k) => s.size < 2 || consecutive[k] === 0), `${p} нет одинаковых кадров подряд`, 'повторов подряд ' + consecutive.join('/'));
    t.ok(sets.every(s => s.size >= Math.min(8, Math.floor(r.pool / 3) - 2)), `${p} на ленту хватает разных картинок (≥ 8, если загружено превью хотя бы на 30)`, sets.map(s => s.size).join('/'));
    if (fromPrev !== null) {
      // сначала берутся картинки, которых не было в прошлом вращении: повториться могут не больше, чем
      // не хватило свежих. Ленты — по 26 кадров (25 видны + 1 под итоговым), исключены 6 кадров в окошках.
      const fresh = r.pool - 6 - (prev.size + 3);
      const allowed = Math.max(0, 78 - fresh);
      t.ok(fromPrev <= allowed, `${p} сначала берутся картинки, которых не было в прошлом вращении`, `из прошлого ${fromPrev}, допустимо ≤ ${allowed}`);
    }
    t.ok(r.gap < MAX_GAP, `${p} старт без зависания (самый долгий кадр < ${MAX_GAP} мс)`, r.gap + ' мс на ' + r.gapAt + ' мс');
    prev = all;
    await sleep(7000);
  }
  const g = await page.js(`(() => { const sh=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden) img')]; return {показано: sh.length, загружено: sh.filter(i=>i.complete&&i.naturalWidth).length, битых: sh.filter(i=>i.complete&&!i.naturalWidth&&i.getAttribute('src')).length}; })()`);
  t.ok(g.битых === 0, 'в конце битых превью в сетке нет', g);
}, { timeout: 90 });
