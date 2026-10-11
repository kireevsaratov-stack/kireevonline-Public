// «Барабан» в настоящем Chrome без окна, в реальном времени: барабаны трогаются и по очереди встают
// точно на кадр, кнопка снова свободна, сетка собрана и не прыгает, в окошках — первые 3 кадра сетки,
// анимация без долгих зависаний кадра. Сам сообщает «прошло / не прошло».
// Запуск: node spin_check.mjs [ширина] [высота] [прогонов]
import { main, openChrome, sleep } from './lib.mjs';

const [W = 1280, H = 900, RUNS = 3] = process.argv.slice(2).map(Number);
// мс: самый долгий промежуток между кадрами страницы. Обычно 16–50 мс; около 0,5 с после нажатия, когда
// пересобирается сетка, бывает ~230 мс — барабаны крутит сам браузер отдельно от страницы, глазом это не видно.
// Больше 400 мс — значит, страница зависла заметно (что-то новое тяжёлое во время вращения).
const MAX_GAP = 400;

await main(`«Барабан» ${W}×${H}`, async t => {
  const page = await openChrome({ width: W, height: H });
  await page.navigate('/shuffle/', 4000);
  for (let run = 1; run <= RUNS; run++) {
    const r = await page.js(`(${measure.toString()})()`);
    const p = `вращение ${run}:`;
    t.info(p, JSON.stringify({ тронулись: r.started, встали: r.stopped, 'от цели, px': r.offTarget, 'самый долгий кадр': r.gap + ' мс на ' + r.gapAt + ' мс', события: r.events.map(e => e.join(' ')) }));
    t.ok(r.started.every(s => s !== null && s < 500), `${p} все барабаны тронулись в первые 0,5 с`, r.started);
    t.ok(r.stopped.every(s => s > 1000 && s < 6500), `${p} все барабаны встали (через 1–6,5 с)`, r.stopped);
    t.ok(r.stopped[0] < r.stopped[1] && r.stopped[1] < r.stopped[2], `${p} встают по очереди слева направо`);
    t.ok(r.offTarget.every(d => Math.abs(d) <= 1), `${p} каждый встал на кадр точно (±1 px)`, r.offTarget);
    t.ok(r.free, `${p} кнопка снова свободна`);
    t.ok(r.assembled && r.revealed, `${p} сетка собрана заново и проявилась`);
    t.ok(r.noJump, `${p} сетка не прыгнула после появления`);
    t.ok(r.reelsMatchGrid, `${p} в окошках первые 3 кадра сетки`);
    t.ok(r.gap < MAX_GAP, `${p} анимация не спотыкается (самый долгий кадр < ${MAX_GAP} мс)`, r.gap + ' мс');
    await sleep(1500);
  }
}, { timeout: 60 + RUNS * 15 });

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
      S.push([t, strips.map(s => -new DOMMatrix(getComputedStyle(s).transform).m42)]);
      if (t < 7200) requestAnimationFrame(loop); else done();
    })();
    function done() {
      mo1.disconnect(); mo2.disconnect();
      let gap = 0, gapAt = 0;
      for (let i = 1; i < S.length; i++) { const g = S[i][0] - S[i - 1][0]; if (g > gap) { gap = g; gapAt = S[i - 1][0]; } }
      const grid = [...masonry.querySelectorAll('.photo-item img')].slice(0, 3).map(i => i.getAttribute('src'));
      resolve({
        events: ev,
        gap: Math.round(gap), gapAt,
        started: strips.map((s, k) => { const i = S.findIndex(x => x[1][k] > 0.01); return i < 0 ? null : S[i][0]; }),
        stopped: strips.map((s, k) => { let t = 0; for (let i = 1; i < S.length; i++) if (Math.abs(S[i][1][k] - S[i - 1][1][k]) > 0.01) t = S[i][0]; return t; }),
        offTarget: S[S.length - 1][1].map(v => +(v - 26 * H).toFixed(2)),  // цель — 27-й кадр ленты (см. spinReels)
        reelsMatchGrid: JSON.stringify(grid) === JSON.stringify(reels.map(r => r.dataset.src)),
        free: !document.querySelector('.js-spin').dataset.busy,
        assembled: has('сетка собрана'), revealed: has('сетка проявилась'),
        noJump: rectsAtReveal !== null && rectsAtReveal === rects(),
      });
    }
  });
}
