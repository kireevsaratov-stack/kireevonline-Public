// Верхнее меню на ширинах 412–1440: гость и админ. Пункты не переносятся на две строки, меню влезает
// в строку или свёрнуто в гамбургер; на телефоне и узких окнах — гамбургер, и он раскрывает меню.
// Админ — временный ui-check (только локальная база), если есть файл с паролем (его создаёт run_all.mjs);
// нет файла — проверяется только гость. Сам сообщает «прошло / не прошло».
// Запуск: node nav_check.mjs [shots] — shots: ещё снимки шапки nav_*.png
import { main, openChrome, sleep, login, adminPassword } from './lib.mjs';

const SHOTS = process.argv.includes('shots');
const WIDTHS = [1440, 1280, 1100, 1000, 900, 800, 770, 760, 412];

await main('шапка на разных ширинах', async t => {
  const page = await openChrome({ width: 1440, height: 800 });
  const roles = ['гость'];
  if (adminPassword()) roles.push('админ'); else t.info('файла с паролем временного админа нет — меню админа не проверяется');
  for (const role of roles) {
    if (role === 'админ') t.ok(await login(page), 'вход временным админом');
    let openedOnce = false;
    for (const W of WIDTHS) {
      await page.setViewport({ width: W, height: 800, mobile: W < 700 });
      await page.navigate('/', 1500);
      const r = await page.js(`(async () => { if (document.fonts) await document.fonts.ready; await new Promise(r => setTimeout(r, 300));
        const h = document.querySelector('.js-header'); const navH = h.offsetHeight;
        const links = [...h.querySelectorAll('.menu-list > .menu-item > .link')];
        const burger = getComputedStyle(h.querySelector('.nav-toggle')).display !== 'none';
        const wrapped = burger ? 0 : links.filter(a => a.getBoundingClientRect().height > navH + 1).length;
        const list = h.querySelector('.menu-list').getBoundingClientRect(), inner = h.querySelector('.inner').getBoundingClientRect();
        return {пунктов: links.length, гамбургер: burger, переносов: wrapped, влезает: burger || list.right <= inner.right - 1,
                админ: [...links].some(a => a.textContent.trim().startsWith('Админ')), прокрутка_вбок: document.documentElement.scrollWidth > innerWidth}; })()`);
      const p = `${role} ${W}px:`;
      t.ok(r.переносов === 0 && r.влезает && !r.прокрутка_вбок, `${p} меню в одну строку без переносов или свёрнуто, страница не шире экрана`,
        `пунктов ${r.пунктов}, гамбургер ${r.гамбургер ? 'да' : 'нет'}, переносов ${r.переносов}`);
      if (W <= 760) t.ok(r.гамбургер, `${p} на узком экране — гамбургер`);
      if (role === 'гость' && W >= 1280) t.ok(!r.гамбургер, `${p} на широком экране меню целиком, без гамбургера`);
      if (role === 'админ' && W === WIDTHS[0]) t.ok(r.админ, `${p} у админа в меню есть «Админ»`);
      if (role === 'гость' && W === WIDTHS[0]) t.ok(!r.админ, `${p} у гостя пункта «Админ» нет`);
      if (r.гамбургер && !openedOnce) {
        openedOnce = true;
        const tag = `${role === 'админ' ? 'admin' : 'guest'}_${W}`;
        if (SHOTS) await page.screenshot(`nav_${tag}.png`, { clip: { x: 0, y: 0, width: W, height: 120 } });
        await page.js(`document.querySelector('.js-nav-toggle').click(); 1`);
        await sleep(600);
        const open = await page.js(`(() => { const m = document.querySelector('.js-header .menu'); const cs = getComputedStyle(m); return cs.visibility === 'visible' && +cs.opacity > 0.9 && m.getBoundingClientRect().height > 100; })()`);
        t.ok(open, `${p} гамбургер раскрывает меню`);
        if (SHOTS) await page.screenshot(`nav_${tag}_open.png`, { clip: { x: 0, y: 0, width: W, height: 560 } });
      }
    }
  }
}, { timeout: 120 });
