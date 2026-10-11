// Снимок первого экрана страницы. node view_shot.mjs адрес ширина высота файл [phone]
// Плотность точек — SCALE (по умолчанию 2; при ширине 1440 новый Chrome на ×2 зависает — тогда SCALE=1).
import { openChrome, sleep } from './lib.mjs';

const [URL_, W = '1280', H = '800', OUT = 'view.png', PHONE] = process.argv.slice(2);
if (!URL_) { console.log('Запуск: node view_shot.mjs адрес ширина высота файл [phone]'); process.exit(2); }
const timer = setTimeout(() => { console.log('✗ время вышло (90 с) — снимок не сделан'); process.exit(1); }, 90000);
const page = await openChrome({ width: +W, height: +H, scale: +(process.env.SCALE || 2), mobile: !!PHONE, fonts: true });
try {
  await page.navigate(URL_, 5000);
  await page.js("document.querySelectorAll('.fade-in').forEach(e => e.classList.add('visible')); 1");
  await sleep(900);
  await page.screenshot(OUT);
  console.log('снимок', OUT);
} catch (e) {
  console.log('✗ снимок не сделан:', e.message);
  process.exitCode = 1;
} finally {
  clearTimeout(timer);
  await page.close();
}
