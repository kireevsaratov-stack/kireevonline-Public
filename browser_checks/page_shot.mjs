// Снимок верха страницы альбома с раскрытыми записками (или «Обо мне»). node page_shot.mjs адрес ширина файл [phone]
// Плотность точек — SCALE (по умолчанию 2; при ширине 1440 новый Chrome на ×2 зависает — тогда SCALE=1).
import { openChrome, sleep } from './lib.mjs';

const [URL_, W = '412', OUT = 'shot.png', PHONE] = process.argv.slice(2);
if (!URL_) { console.log('Запуск: node page_shot.mjs адрес ширина файл [phone]'); process.exit(2); }
const timer = setTimeout(() => { console.log('✗ время вышло (90 с) — снимок не сделан'); process.exit(1); }, 90000);
const page = await openChrome({ width: +W, height: 900, scale: +(process.env.SCALE || 2), mobile: !!PHONE, fonts: true });
try {
  await page.navigate(URL_, 4000);
  const h = await page.js(`(() => { document.querySelectorAll('.fade-in').forEach(e => e.classList.add('visible'));
    const t = document.querySelector('.js-intro-toggle'); if (t) t.click();
    return new Promise(r => setTimeout(() => { const el = document.querySelector('.album-intro') || document.querySelector('.about'); const b = el.getBoundingClientRect(); r(Math.ceil(b.bottom + window.scrollY + 40)); }, 900)); })()`);
  await page.setViewport({ height: h });
  await sleep(800);
  await page.screenshot(OUT, { clip: { x: 0, y: 0, width: +W, height: h } });
  console.log('снимок', OUT, W + '×' + h);
} catch (e) {
  console.log('✗ снимок не сделан:', e.message);
  process.exitCode = 1;
} finally {
  clearTimeout(timer);
  await page.close();
}
