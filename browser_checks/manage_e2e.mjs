// Панель управления вживую: вход временным админом ui-check (только локальная база; пароль — в файле,
// его создаёт run_all.mjs), действия по очереди с проверкой по базе и возвратом как было:
// перетаскивание (мышью, на телефоне — пальцем), скрыть/показать, переименовать, создать и удалить,
// тексты альбома с живым видом, перенос фото. В конце — сверка базы с тем, что было до проверки.
// Сам сообщает «прошло / не прошло». Запуск: node manage_e2e.mjs [ширина] [shots] — shots: ещё снимки manage_*.png
import { main, openChrome, sleep, sql, login } from './lib.mjs';

const W = +(process.argv[2] || 1280), PHONE = W < 700;
const SHOTS = process.argv.includes('shots');
const albumId = name => sql(`SELECT id FROM photos_album WHERE name='${name}'`);   // по имени: номера в базах разные
const TRAVEL = sql("SELECT id FROM photos_section WHERE name='Путешествия'");
const BALI = albumId('Бали'), KHARABALI = albumId('Харабали'), PITER24 = albumId('Питер 2024'), PITER25 = albumId('Питер 2025');
const TEST_NAME = 'Тестовый альбом ui-check';
const order = () => sql(`SELECT group_concat(id) FROM (SELECT id FROM photos_album WHERE section_id=${TRAVEL} ORDER BY "order", name)`);
// всё, что проверка трогает: до и после должно совпасть
const snapshot = () => sql(`SELECT group_concat(id||':'||"order"||':'||hidden||':'||name, '|') FROM photos_album WHERE section_id=${TRAVEL}`)
  + '#' + sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`)
  + '#' + sql(`SELECT group_concat(id) FROM photos_photo WHERE album_id=${PITER24} ORDER BY id`)
  + '#' + sql(`SELECT count(*) FROM photos_album WHERE name='${TEST_NAME}'`);
const csrf = "document.querySelector('[name=csrfmiddlewaretoken]').value";
const post = (url, fields) => `(() => { const fd=new FormData(); ${fields.map(([k, v]) => `fd.append(${JSON.stringify(k)}, ${JSON.stringify(String(v))});`).join('')} fd.append('csrfmiddlewaretoken', ${csrf}); return fetch(${JSON.stringify(url)},{method:'POST',body:fd}).then(r=>r.json()); })()`;

await main(`панель управления ${W}px`, async t => {
  t.ok(TRAVEL && BALI && KHARABALI && PITER24 && PITER25, 'в локальной базе есть «Путешествия», «Бали», «Харабали», «Питер 2024» и «Питер 2025»');
  const before = snapshot();
  const page = await openChrome({ width: W, height: 900, mobile: PHONE });
  const dialogs = [];
  page.on('Page.javascriptDialogOpening', p => { dialogs.push(p.type + ': ' + p.message); page.send('Page.handleJavaScriptDialog', { accept: true }).catch(() => {}); });
  const step = async (what, fn) => { try { await fn(); } catch (e) { t.ok(false, `${what}: оборвалось — ${e.message}`); } };
  try {
    // 1. вход
    t.ok(await login(page), '1. вход через страницу входа');
    await page.navigate('/admin/', 1500);
    t.ok(await page.js("location.pathname === '/admin/' && !!document.querySelector('.mg-albums')"), '1. открылась панель «Альбомы»');
    if (SHOTS) { await page.js("document.querySelectorAll('.fade-in').forEach(e=>e.classList.add('visible'));1"); await page.screenshot(`manage_${W}.png`); }

    // 2. порядок: первый альбом раздела «Путешествия» перетащить ниже второго, потом вернуть
    const was = order();
    await step('2. перетаскивание', async () => {
      await page.js(`document.querySelector('.mg-albums[data-section="${TRAVEL}"]').children[0].scrollIntoView({block:'center',behavior:'instant'}); 1`);
      await sleep(400);
      const p = await page.js(`(() => { const rows=[...document.querySelector('.mg-albums[data-section="${TRAVEL}"]').children]; const h=rows[0].querySelector('.js-handle').getBoundingClientRect(); const t=rows[1].querySelector('.mg-row').getBoundingClientRect(); return {hx:h.left+h.width/2, hy:h.top+h.height/2, ty:t.bottom-4, first:rows[0].dataset.id, second:rows[1].dataset.id}; })()`);
      if (PHONE) {  // палец: настоящие касания
        await page.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: p.hx, y: p.hy }] });
        for (let k = 1; k <= 6; k++) { await page.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: p.hx, y: p.hy + (p.ty - p.hy) * k / 6 + 2 }] }); await sleep(30); }
        await page.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      } else {
        await page.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: p.hx, y: p.hy, button: 'left', clickCount: 1 });
        for (let k = 1; k <= 6; k++) await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.hx, y: p.hy + (p.ty - p.hy) * k / 6 + 2, button: 'left', buttons: 1 });
        await page.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: p.hx, y: p.ty + 2, button: 'left', clickCount: 1 });
      }
      await sleep(1200);
      const now = order().split(',');
      t.ok(now[0] === p.second && now[1] === p.first, `2. перетаскивание ${PHONE ? 'пальцем' : 'мышью'} меняет порядок в базе`, `${was.split(',').slice(0, 3)} → ${now.slice(0, 3)}`);
      t.ok(/\S/.test(await page.js("document.querySelector('.js-toast').textContent")), '2. появилось уведомление', await page.js("document.querySelector('.js-toast').textContent"));
    });
    await step('2. возврат порядка', async () => {
      const r = await page.js(post('/admin/order/', [['kind', 'album'], ['section', TRAVEL], ...was.split(',').map(i => ['ids', i])]));
      t.ok(order() === was, '2. порядок возвращён как был', r);
    });

    // 3. скрыть / показать «Бали»
    await step('3. скрыть/показать', async () => {
      await page.navigate('/admin/', 1500);
      const h0 = sql(`SELECT hidden FROM photos_album WHERE id=${BALI}`);
      const toggle = () => page.js(`document.querySelector('.js-row[data-id="${BALI}"][data-kind="album"] .js-hidden').click(); 1`);
      await toggle(); await sleep(900);
      const h1 = sql(`SELECT hidden FROM photos_album WHERE id=${BALI}`);
      await toggle(); await sleep(900);
      const h2 = sql(`SELECT hidden FROM photos_album WHERE id=${BALI}`);
      t.ok(h1 !== h0, '3. «Бали»: первое нажатие меняет «скрыт» в базе', `${h0} → ${h1}`);
      t.ok(h2 === h0, '3. «Бали»: второе нажатие возвращает как было', h2);
    });

    // 4. переименовать «Харабали» и вернуть
    await step('4. переименование', async () => {
      const oldName = sql(`SELECT name FROM photos_album WHERE id=${KHARABALI}`);
      for (const nm of [oldName + ' тест', oldName]) {
        await page.js(`document.querySelector('.js-row[data-id="${KHARABALI}"][data-kind="album"] .js-rename').click(); 1`);
        await sleep(300);
        await page.js(`(() => { const i=document.querySelector('.mg-name-input'); i.value=${JSON.stringify(nm)}; i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); return 1; })()`);
        await sleep(900);
        const inDb = sql(`SELECT name FROM photos_album WHERE id=${KHARABALI}`);
        const onPage = await page.js(`document.querySelector('.js-row[data-id="${KHARABALI}"] .js-rename').textContent.trim()`);
        t.ok(inDb === nm && onPage === nm, `4. переименование в «${nm}» — в базе и на странице`, `база «${inDb}», страница «${onPage}»`);
      }
    });

    // 5. создать альбом и удалить
    await step('5. создать и удалить', async () => {
      await page.js(`(() => { const f=document.querySelector('.js-create[data-section="${TRAVEL}"]'); f.querySelector('input').value=${JSON.stringify(TEST_NAME)}; f.requestSubmit(); return 1; })()`);
      await sleep(2500);
      const newId = sql(`SELECT id FROM photos_album WHERE name='${TEST_NAME}'`);
      t.ok(newId && sql(`SELECT hidden FROM photos_album WHERE id=${newId}`) === '1', '5. создан новый альбом, сразу скрытый', newId);
      t.ok(newId && await page.js(`!!document.querySelector('.js-row[data-id="${newId}"]')`), '5. его строка появилась на странице');
      if (newId) {
        await page.js(`document.querySelector('.js-row[data-id="${newId}"] .js-delete').click(); 1`);
        await sleep(1200);
        t.ok(sql(`SELECT count(*) FROM photos_album WHERE id=${newId}`) === '0', '5. удаление (с подтверждением) убирает его из базы', dialogs.splice(0).join(' / '));
      }
    });

    // 6. тексты альбома «Питер 2024»: «Коротко» — живой вид, сохранить, вернуть
    await step('6. тексты альбома', async () => {
      const oldIntro = sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`);
      await page.navigate(`/admin/album/${PITER24}/`, 1500);
      await page.js(`(() => { const t=document.querySelector('[name=intro]'); t.value='Проверка живого вида'; t.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()`);
      t.ok(await page.js("document.querySelector('.js-pv-intro').textContent") === 'Проверка живого вида', '6. «Коротко»: живой вид меняется при наборе');
      t.info('строка:', await page.js("document.querySelector('.js-pv-line').textContent"), '| снято на:', await page.js("document.querySelector('.js-pv-gear').textContent"));
      if (SHOTS) await page.screenshot(`manage_album_${W}.png`);
      let loaded = page.once('Page.loadEventFired', 30000);
      await page.js("document.querySelector('.js-album-form').submit();1");
      await loaded; await sleep(500);
      t.ok(sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`) === 'Проверка живого вида', '6. «Коротко» сохранено в базе', await page.js("(document.querySelector('.alert')||{}).textContent||''"));
      loaded = page.once('Page.loadEventFired', 30000);
      await page.js(`(() => { document.querySelector('[name=intro]').value=${JSON.stringify(oldIntro)}; document.querySelector('.js-album-form').submit(); return 1; })()`);
      await loaded; await sleep(500);
      t.ok(sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`) === oldIntro, '6. «Коротко» возвращено как было');
    });

    // 7. перенос фото: один кадр из «Питер 2024» в «Питер 2025» и обратно
    await step('7. перенос фото', async () => {
      await page.navigate(`/album/${PITER24}/`, 3000);
      const pid = await page.js("document.querySelector('#masonry .photo-item').dataset.id");
      await page.js("document.querySelector('.js-select-toggle').click();1");
      await page.js(`document.querySelector('#masonry .photo-item[data-id="${pid}"]').click();1`);
      t.ok(await page.js("getComputedStyle(document.querySelector('.js-move')).display!=='none'"), `7. выбран кадр ${pid}, кнопка «Перенести» видна`);
      if (SHOTS) await page.screenshot(`move_${W}.png`, { clip: { x: 0, y: 0, width: W, height: 520 } });
      await page.js(`(() => { document.querySelector('.js-move-target').value='${PITER25}'; document.querySelector('.js-move-selected').click(); return 1; })()`);
      await sleep(1500);
      t.ok(sql(`SELECT album_id FROM photos_photo WHERE id=${pid}`) === PITER25, '7. кадр перенесён в «Питер 2025» в базе', dialogs.splice(0).join(' / '));
      t.ok(await page.js(`!document.querySelector('#masonry .photo-item[data-id="${pid}"]')`), '7. кадр убран со страницы');
      const r = await page.js(post('/admin/photos/move/', [['ids', pid], ['album', PITER24]]));
      t.ok(sql(`SELECT album_id FROM photos_photo WHERE id=${pid}`) === PITER24, '7. кадр возвращён в «Питер 2024»', r);
    });
  } finally {
    t.ok(snapshot() === before, 'в базе всё как до проверки (порядок, скрытость, названия, тексты, фото)');
  }
}, { timeout: 150 });
