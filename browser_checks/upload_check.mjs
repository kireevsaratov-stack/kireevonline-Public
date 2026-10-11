// Загрузка фото через страницу панели вживую (только копия сайта на Mac, временный админ ui-check — как в manage_e2e.mjs).
// Создаёт временный скрытый альбом с «неудобным» названием, загружает в него сгенерированную картинку 2600×1800,
// проверяет по базе и файлу; затем «вход истёк» посреди загрузки — загрузчик должен остановиться;
// в конце стирает фото и альбом. Сам сообщает «прошло / не прошло». Запуск: node upload_check.mjs
import { execFileSync } from 'node:child_process';
import { main, openChrome, sleep, sql, login, BASE, HERE } from './lib.mjs';

const MEDIA = process.env.MEDIA || HERE + '../../backups/media/';
const NAME = 'Проверка загрузки \\ "кавычки" & <b>';
const csrf = "document.querySelector('[name=csrfmiddlewaretoken]').value";

// выбрать файлы в поле загрузки: картинки рисуются прямо на странице
const pickFiles = (section, album, files) => `(async () => {
  const s=document.getElementById('id_section'); s.value='${section}'; s.dispatchEvent(new Event('change'));
  document.getElementById('id_album').value='${album}';
  const dt=new DataTransfer();
  for (const [name, w, h] of ${JSON.stringify(files)}) {
    const c=document.createElement('canvas'); c.width=w; c.height=h;
    const g=c.getContext('2d'); g.fillStyle='#3a7'; g.fillRect(0,0,w,h); g.fillStyle='#fff'; g.fillRect(w/13,h/9,w/3,h/3);
    const blob=await new Promise(r=>c.toBlob(r,'image/jpeg',0.92));
    dt.items.add(new File([blob],name,{type:'image/jpeg'}));
  }
  const fi=document.getElementById('id_images'); fi.files=dt.files; fi.dispatchEvent(new Event('change'));
  return 1;
})()`;
// нажать «Загрузить» и ждать итог в строке состояния
const submitAndWait = done => `(async () => {
  document.getElementById('submit-btn').click();
  for (let i=0;i<60;i++){ await new Promise(r=>setTimeout(r,500)); const t=document.getElementById('upload-status').textContent; if(${done}.test(t)) return t; }
  return document.getElementById('upload-status').textContent;
})()`;

await main('загрузка фото', async t => {
  const page = await openChrome({ width: 1280, height: 900 });
  const errors = [];
  page.on('Runtime.exceptionThrown', p => errors.push(p.exceptionDetails.exception?.description || p.exceptionDetails.text));
  await page.send('Runtime.enable');
  const section = sql('SELECT id FROM photos_section ORDER BY "order" LIMIT 1');
  let albumId = null;
  try {
    t.ok(await login(page), 'вход через страницу входа');
    await page.navigate('/admin/', 1000);
    const created = await page.js(`(() => { const fd=new FormData(); fd.append('kind','album'); fd.append('section','${section}'); fd.append('name',${JSON.stringify(NAME)}); fd.append('csrfmiddlewaretoken',${csrf}); return fetch('/admin/create/',{method:'POST',body:fd}).then(r=>r.json()); })()`);
    albumId = created && created.id;
    t.ok(albumId, 'временный альбом создан');
    if (!albumId) return;

    await page.navigate('/admin/upload/', 1500);
    t.ok(errors.length === 0, 'страница загрузки без ошибок скриптов', errors[0]);
    const options = await page.js(`(() => { const s=document.getElementById('id_section'); s.value='${section}'; s.dispatchEvent(new Event('change')); return Array.from(document.getElementById('id_album').options).map(o=>o.textContent); })()`);
    t.ok(options.includes(NAME), 'название альбома в списке ровно как есть');

    await page.js(pickFiles(section, albumId, [['проверка-загрузки.jpg', 2600, 1800]]));
    const result = await page.js(submitAndWait('/^Готово/'), 40000);
    t.ok(/Готово: загружено 1/.test(result), 'загрузка прошла', result);

    const row = sql(`SELECT id, image, thumb, section_id FROM photos_photo WHERE album_id=${albumId}`).split('|');
    t.ok(row.length === 4 && row[3] === section, 'фото в базе, в нужном альбоме и разделе');
    if (row.length === 4) {
      const dims = execFileSync('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', MEDIA + row[1]]).toString();
      const w = +dims.match(/pixelWidth: (\d+)/)[1], h = +dims.match(/pixelHeight: (\d+)/)[1];
      t.ok(Math.max(w, h) === 1920, 'фото ужато до 1920 по длинной стороне', `${w}×${h}`);
      t.ok(!!row[2], 'превью создано');
      // убрать за собой: фото в корзину и из неё насовсем (это фото создала сама проверка)
      await page.js(`(() => { const t=${csrf}; const a=new FormData(); a.append('ids','${row[0]}'); a.append('csrfmiddlewaretoken',t); return fetch('/admin/photos/delete/',{method:'POST',body:a}).then(()=>{ const b=new FormData(); b.append('action','delete'); b.append('ids','${row[0]}'); b.append('csrfmiddlewaretoken',t); return fetch('/admin/trash/action/',{method:'POST',body:b}); }).then(r=>r.status); })()`);
    }

    // вход истёк посреди работы: загрузчик должен остановиться с понятным сообщением и не слать части дальше
    await page.navigate('/admin/upload/', 1500);
    await page.js(pickFiles(section, albumId, [['a.jpg', 1200, 800], ['b.jpg', 1200, 800]]));
    await page.send('Network.enable');
    await page.send('Network.deleteCookies', { name: 'sessionid', url: BASE });
    const lost = await page.js(submitAndWait('/^(Готово|Остановлено)/'), 40000);
    t.ok(/Остановлено/.test(lost) && /войдите снова/.test(lost), 'вход истёк — загрузка остановлена с понятным сообщением', lost);
    t.ok(sql(`SELECT count(*) FROM photos_photo WHERE album_id=${albumId}`) === '0', 'без входа ничего не загрузилось');
  } finally {
    // убрать временный альбом в любом случае (войти заново — сессия могла быть стёрта)
    if (albumId) {
      try {
        await login(page);
        await page.navigate('/admin/', 1000);
        await page.js(`(() => { const fd=new FormData(); fd.append('kind','album'); fd.append('id','${albumId}'); fd.append('csrfmiddlewaretoken',${csrf}); return fetch('/admin/delete/',{method:'POST',body:fd}).then(r=>r.status); })()`);
      } catch (e) { t.info('уборка через панель не удалась:', e.message); }
      t.ok(sql(`SELECT count(*) FROM photos_album WHERE id=${albumId}`) === '0' && sql(`SELECT count(*) FROM photos_photo WHERE album_id=${albumId}`) === '0', 'временный альбом и фото убраны');
    }
  }
}, { timeout: 120 });
