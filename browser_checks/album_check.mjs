// Альбом: при открытии — не больше 40 превью (и запросов к серверу), при прокрутке догружаются следующие,
// битых нет, кадр из догруженных открывается в просмотре; на телефоне полный экран не включается.
// Сам сообщает «прошло / не прошло». Запуск: node album_check.mjs [адрес] [phone]
import { main, openChrome, sleep } from './lib.mjs';

const URL_ = process.argv[2] || '/album/9/';
const PHONE = process.argv[3] === 'phone';
const BATCH = 40;   // порция превью (BATCH в static/js/site.js)

await main(`альбом ${URL_}${PHONE ? ' (телефон)' : ''}`, async t => {
  const page = PHONE ? await openChrome({ width: 412, height: 915, scale: 2.6, mobile: true }) : await openChrome({ width: 1280, height: 900 });
  let thumbReq = 0, thumbFail = 0;
  const reqUrl = new Map();
  page.on('Network.requestWillBeSent', p => { if (/\/media\/thumbs\//.test(p.request.url)) { thumbReq++; reqUrl.set(p.requestId, p.request.url); } });
  page.on('Network.loadingFailed', p => { if (reqUrl.has(p.requestId)) thumbFail++; });
  page.on('Network.responseReceived', p => { if (reqUrl.has(p.requestId) && p.response.status >= 400) thumbFail++; });
  await page.send('Network.enable');
  if (PHONE) await page.send('Emulation.setEmitTouchEventsForMouse', { enabled: true, configuration: 'mobile' });
  await page.navigate(URL_, 5000);
  const state = () => page.js(`(() => { const items=[...document.querySelectorAll('#masonry .photo-item')]; const sh=items.filter(e=>!e.classList.contains('is-hidden')).map(e=>e.querySelector('img'));
    return {всего: items.length, показано: sh.length, загружено: sh.filter(i=>i.complete&&i.naturalWidth).length, битых: sh.filter(i=>i.complete&&!i.naturalWidth&&i.getAttribute('src')).length,
            с_адресом: items.filter(e=>e.querySelector('img').getAttribute('src')).length, видны: sh.every(i=>getComputedStyle(i).opacity==='1')}; })()`);

  const s1 = await state();
  t.info('открыли альбом:', JSON.stringify(s1), '| запросов превью:', thumbReq);
  t.ok(s1.всего > BATCH, `в альбоме больше ${BATCH} кадров (иначе догрузку не проверить)`, s1.всего);
  t.ok(s1.показано === Math.min(BATCH, s1.всего), `при открытии показаны первые ${BATCH}`, s1.показано);
  t.ok(s1.с_адресом <= BATCH && thumbReq <= BATCH, `при открытии сервер просят не больше чем о ${BATCH} превью`, `адресов ${s1.с_адресом}, запросов ${thumbReq}`);
  t.ok(s1.видны, 'превью видны сразу, без прозрачности');

  for (let i = 0; i < 4; i++) { await page.js('window.scrollTo(0, document.body.scrollHeight); 1'); await sleep(2500); }
  const s2 = await state();
  t.info('после прокрутки вниз:', JSON.stringify(s2), '| запросов превью:', thumbReq, '| сбоев:', thumbFail);
  t.ok(s2.показано > s1.показано, 'прокрутка догружает следующие кадры', `${s1.показано} → ${s2.показано}`);
  t.ok(s2.битых === 0 && thumbFail === 0, 'битых превью нет', `битых ${s2.битых}, сбоев загрузки ${thumbFail}`);

  const lb = await page.js(`(() => { const items=[...document.querySelectorAll('#masonry .photo-item:not(.is-hidden)')]; const el=items[items.length-1]; el.scrollIntoView(); el.click();
    return new Promise(r=>setTimeout(()=>r({открыт: document.getElementById('lightbox').classList.contains('open'), кадр: (document.getElementById('lb-img').getAttribute('src')||'').split('/').pop(),
      ждали: (el.dataset.full||'').split('/').pop(), счётчик: document.getElementById('lb-counter').textContent, полный_экран: !!document.fullscreenElement,
      мышь: matchMedia('(hover:hover) and (pointer:fine)').matches, номер: items.length}), 800)); })()`);
  t.info('открыли последний догруженный кадр:', JSON.stringify(lb));
  t.ok(lb.открыт, 'кадр из догруженных открывается в просмотре');
  t.ok(lb.кадр && lb.кадр === lb.ждали, 'в просмотре тот самый кадр', lb.кадр);
  t.ok(lb.счётчик.startsWith(lb.номер + ' / '), 'счётчик показывает его номер', lb.счётчик);
  if (PHONE) {
    t.ok(!lb.мышь, 'телефон определяется как экран без мыши');
    t.ok(!lb.полный_экран, 'на телефоне полный экран не включается');
  }
}, { timeout: 90 });
