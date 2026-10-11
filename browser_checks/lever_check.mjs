// Рычаг «Барабана»: в покое, на трети хода, в нижней точке и на возврате шарик круглый (не сжимается),
// двигается только вниз и возвращается на место, стержень только укорачивается.
// Сам сообщает «прошло / не прошло». Запуск: node lever_check.mjs [shots] — shots: ещё снимки в lever/
import { mkdirSync } from 'node:fs';
import { main, openChrome, sleep, HERE } from './lib.mjs';

const SHOTS = process.argv.includes('shots');

await main('рычаг «Барабана»', async t => {
  const page = await openChrome({ width: 1280, height: 900, scale: SHOTS ? 3 : 1 });
  await page.navigate('/shuffle/', 3000);
  const rect = await page.js(`(() => { window.scrollTo(0,0); const r=document.querySelector('.slot').getBoundingClientRect(); return {x:r.right-40,y:r.top-20,width:56,height:r.height+40}; })()`);
  if (SHOTS) mkdirSync(HERE + 'lever', { recursive: true });
  const shot = name => SHOTS && page.screenshot('lever/' + name, { clip: rect });
  // шарик — ::before, стержень — ::after; в анимации — их текущие преобразования
  const knob = () => page.js(`(() => { const l=document.querySelector('.lever'); const b=getComputedStyle(l,'::before'), a=getComputedStyle(l,'::after');
    const m=new DOMMatrix(b.transform==='none'?undefined:b.transform), n=new DOMMatrix(a.transform==='none'?undefined:a.transform);
    return {w: parseFloat(b.width), h: parseFloat(b.height), sx: +m.a.toFixed(3), sy: +m.d.toFixed(3), skew: +(Math.abs(m.b)+Math.abs(m.c)).toFixed(3), dx: +m.e.toFixed(2), dy: +m.f.toFixed(2), armY: +n.d.toFixed(3)}; })()`);
  const round = k => Math.abs(k.w - k.h) < 0.5 && Math.abs(k.sx - 1) < 0.01 && Math.abs(k.sy - 1) < 0.01 && k.skew < 0.01;

  await shot('0_rest.png');
  const rest = await knob();
  t.info('в покое:', JSON.stringify(rest));
  t.ok(round(rest) && rest.dx === 0 && rest.dy === 0, 'в покое шарик круглый и на месте', `${rest.w}×${rest.h}`);

  await page.js(`document.querySelector('.js-spin').click(); 1`);
  const anims = await page.js(`document.getAnimations().filter(a => a.animationName && a.animationName.startsWith('lever')).length`);
  t.ok(anims >= 2, 'нажатие запускает анимацию шарика и стержня', anims);
  let bottom = 0;
  for (const [ms, name] of [[120, '1_120ms.png'], [360, '2_360ms_bottom.png'], [650, '3_650ms.png'], [900, '4_900ms.png']]) {
    await page.js(`(() => { document.getAnimations().filter(a => a.animationName && a.animationName.startsWith('lever')).forEach(a => { a.pause(); a.currentTime = ${ms}; }); return 1; })()`);
    await sleep(150);
    await shot(name);
    const k = await knob();
    t.info(ms + ' мс:', JSON.stringify(k));
    t.ok(round(k), `${ms} мс: шарик круглый, не сжат`, `${k.w}×${k.h}, масштаб ${k.sx}×${k.sy}`);
    t.ok(k.dx === 0 && k.dy >= 0, `${ms} мс: шарик сдвинут только вниз`, `вбок ${k.dx}, вниз ${k.dy}`);
    t.ok(k.armY > 0 && k.armY <= 1, `${ms} мс: стержень только укорачивается`, k.armY);
    if (ms === 360) bottom = k.dy;
  }
  t.ok(bottom > 15, 'в нижней точке шарик заметно опустился (> 15 px)', bottom + ' px');
  await page.js(`document.getAnimations().filter(a => a.animationName && a.animationName.startsWith('lever')).forEach(a => a.finish()); 1`);
  await sleep(150);
  const end = await knob();
  t.ok(round(end) && end.dx === 0 && end.dy === 0, 'после хода шарик вернулся на место');
  if (SHOTS) t.info('снимки — в папке lever/');
}, { timeout: 60 });
