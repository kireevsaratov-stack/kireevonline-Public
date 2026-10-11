// «Управление» вживую: вход тестовым админом (только локальная база), действия по очереди с проверкой по базе и откатом.
import { tmpdir } from 'node:os';
import { spawn, execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const DB = SP + '../db.sqlite3';
const PW = readFileSync(tmpdir() + '/kireevonline-ui-check-pw.txt', 'utf8').trim();
const BASE = 'http://localhost:8100';
const sql = q => execSync(`sqlite3 "${DB}" "${q}"`).toString().trim();
const id = name => sql(`SELECT id FROM photos_album WHERE name='${name}'`);
const TRAVEL = sql("SELECT id FROM photos_section WHERE name='Путешествия'");
const BALI = id('Бали'), KHARABALI = id('Харабали'), PITER24 = id('Питер 2024'), PITER25 = id('Питер 2025');
const PORT = 9342;
const W = +(process.argv[2] || 1280), PHONE = W < 700;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-11-${W}`,
  '--no-first-run', `--window-size=${W},900`,
  '--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND', 'about:blank',
], { stdio: 'ignore' });
const log = (...a) => console.log(...a);
try {
  let pages;
  for (let i = 0; i < 50; i++) { try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {} await sleep(200); }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let id = 0; const wait = new Map(); const dialogs = [];
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); return; }
    if (m.method === 'Page.javascriptDialogOpening') {
      dialogs.push(m.params.type + ': ' + m.params.message);
      ws.send(JSON.stringify({ id: ++id, method: 'Page.handleJavaScriptDialog', params: { accept: true } }));
    }
  });
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async e => { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }); return r.result.exceptionDetails ? 'ОШИБКА: ' + r.result.exceptionDetails.text + ' ' + (r.result.exceptionDetails.exception?.description || '') : r.result.result?.value; };
  const go = async (url, ms = 2500) => { await send('Page.navigate', { url: BASE + url }); await sleep(ms); };
  const shot = async (name, h) => { const s = await send('Page.captureScreenshot', { format: 'png', ...(h ? { clip: { x: 0, y: 0, width: W, height: h, scale: 1 } } : {}) }); writeFileSync(SP + name, Buffer.from(s.result.data, 'base64')); };
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: 900, deviceScaleFactor: 2, mobile: PHONE });
  if (PHONE) await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });

  // вход
  await go('/admin/login/?next=/admin/');
  await js(`document.getElementById('id_username').value='ui-check';document.getElementById('id_password').value=${JSON.stringify(PW)};document.querySelector('#login-form, form').submit();1`);
  await sleep(3000);
  await go('/admin/');
  log('1. вход:', await js('location.pathname'), '| заголовок:', await js("document.querySelector('h1')&&document.querySelector('h1').textContent"));
  await js("document.querySelectorAll('.fade-in').forEach(e=>e.classList.add('visible'));1");
  await shot(`manage_${W}.png`);

  // порядок: первые два альбома раздела «Путешествия» (id 3) — перетащить первый ниже второго, потом вернуть
  const before = sql("SELECT group_concat(id) FROM (SELECT id FROM photos_album WHERE section_id=" + TRAVEL + " ORDER BY \\\"order\\\", name)");
  const pos = await js(`(() => { const list=document.querySelector('.mg-albums[data-section=\"3\"]'); const rows=[...list.children]; const h=rows[0].querySelector('.js-handle').getBoundingClientRect(); const t=rows[1].querySelector('.mg-row').getBoundingClientRect(); rows[0].scrollIntoView({block:'center',behavior:'instant'}); return null; })()`);
  await sleep(400);
  const p2 = await js(`(() => { const rows=[...document.querySelector('.mg-albums[data-section=\"3\"]').children]; const h=rows[0].querySelector('.js-handle').getBoundingClientRect(); const t=rows[1].querySelector('.mg-row').getBoundingClientRect(); return {hx:h.left+h.width/2, hy:h.top+h.height/2, ty:t.bottom-4, first:rows[0].dataset.id, second:rows[1].dataset.id}; })()`);
  if (PHONE) {  // палец: настоящие касания
    await send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: p2.hx, y: p2.hy }] });
    for (let k = 1; k <= 6; k++) { await send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: p2.hx, y: p2.hy + (p2.ty - p2.hy) * k / 6 + 2 }] }); await sleep(30); }
    await send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  } else {
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: p2.hx, y: p2.hy, button: 'left', clickCount: 1 });
    for (let k = 1; k <= 6; k++) await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p2.hx, y: p2.hy + (p2.ty - p2.hy) * k / 6 + 2, button: 'left', buttons: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: p2.hx, y: p2.ty + 2, button: 'left', clickCount: 1 });
  }
  await sleep(1200);
  const after = sql("SELECT group_concat(id) FROM (SELECT id FROM photos_album WHERE section_id=" + TRAVEL + " ORDER BY \\\"order\\\", name)");
  log('2. перетаскивание:', before.split(',').slice(0, 3).join(','), '→', after.split(',').slice(0, 3).join(','), '| уведомление:', await js("document.querySelector('.js-toast').textContent"));
  // вернуть исходный порядок через тот же адрес
  log('   откат порядка:', await js(`(() => { const fd=new FormData(); fd.append('kind','album'); fd.append('section','${TRAVEL}'); ${JSON.stringify(before.split(','))}.forEach(i=>fd.append('ids',i)); fd.append('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]').value); return fetch('/admin/order/',{method:'POST',body:fd}).then(r=>r.json()).then(d=>JSON.stringify(d)); })()`),
      '| теперь:', sql("SELECT group_concat(id) FROM (SELECT id FROM photos_album WHERE section_id=" + TRAVEL + " ORDER BY \\\"order\\\", name)") === before ? 'как было' : 'НЕ как было');

  // скрыть / показать: альбом «Бали» (id 9)
  await go('/admin/');
  await js(`(() => { const cb=document.querySelector('.js-row[data-id=\"${BALI}\"][data-kind=\"album\"] .js-hidden'); cb.click(); return 1; })()`);
  await sleep(900);
  const hid1 = sql(`SELECT hidden FROM photos_album WHERE id=${BALI}`);
  await js(`(() => { document.querySelector('.js-row[data-id=\"${BALI}\"][data-kind=\"album\"] .js-hidden').click(); return 1; })()`);
  await sleep(900);
  log('3. скрыть/показать «Бали»: после 1-го нажатия hidden =', hid1, ', после 2-го =', sql(`SELECT hidden FROM photos_album WHERE id=${BALI}`));

  // переименовать и вернуть: «Харабали» (id 15)
  const oldName = sql(`SELECT name FROM photos_album WHERE id=${KHARABALI}`);
  for (const nm of ['Харабали тест', oldName]) {
    await js(`(() => { document.querySelector('.js-row[data-id=\"${KHARABALI}\"][data-kind=\"album\"] .js-rename').click(); return 1; })()`);
    await sleep(300);
    await js(`(() => { const i=document.querySelector('.mg-name-input'); i.value=${JSON.stringify(nm)}; i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); return 1; })()`);
    await sleep(900);
    log('4. переименование →', sql(`SELECT name FROM photos_album WHERE id=${KHARABALI}`), '| на странице:', await js(`document.querySelector('.js-row[data-id=\"${KHARABALI}\"] .js-rename').textContent`));
  }

  // создать альбом и удалить
  await js(`(() => { const f=document.querySelector('.js-create[data-section=\"3\"]'); f.querySelector('input').value='Тестовый альбом'; f.requestSubmit(); return 1; })()`);
  await sleep(2500);
  const newId = sql("SELECT id FROM photos_album WHERE name='Тестовый альбом'");
  log('5. создан альбом id', newId, '| скрыт:', sql(`SELECT hidden FROM photos_album WHERE id=${newId || 0}`), '| строка на странице:', await js(`!!document.querySelector('.js-row[data-id=\"${newId}\"]')`));
  await js(`(() => { document.querySelector('.js-row[data-id=\"${newId}\"] .js-delete').click(); return 1; })()`);
  await sleep(1200);
  log('   удалён:', sql(`SELECT count(*) FROM photos_album WHERE id=${newId || 0}`) === '0', '| диалоги:', dialogs.splice(0).join(' / '));

  // тексты альбома: «Питер 2024» — поменять «Коротко», проверить вид, сохранить, вернуть
  const oldIntro = sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`);
  await go(`/admin/album/${PITER24}/`);
  await js(`(() => { const t=document.querySelector('[name=intro]'); t.value='Проверка живого вида'; t.dispatchEvent(new Event('input',{bubbles:true})); return 1; })()`);
  log('6. живой вид «Коротко»:', await js("document.querySelector('.js-pv-intro').textContent"), '| строка:', await js("document.querySelector('.js-pv-line').textContent"), '| снято на:', await js("document.querySelector('.js-pv-gear').textContent"));
  await shot(`manage_album_${W}.png`);
  await js("document.querySelector('.js-album-form').submit();1");
  await sleep(2500);
  log('   сохранено:', sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`), '| сообщение:', await js("(document.querySelector('.alert')||{}).textContent"));
  await js(`(() => { const t=document.querySelector('[name=intro]'); t.value=${JSON.stringify(oldIntro)}; document.querySelector('.js-album-form').submit(); return 1; })()`);
  await sleep(2500);
  log('   возвращено:', sql(`SELECT intro FROM photos_album WHERE id=${PITER24}`) === oldIntro);

  // перенос фото: из «Питер 2024» один кадр в «Питер 2025» и обратно
  await go(`/album/${PITER24}/`, 4000);
  const pid = await js("document.querySelector('#masonry .photo-item').dataset.id");
  await js("document.querySelector('.js-select-toggle').click();1");
  await js(`document.querySelector('#masonry .photo-item[data-id=\"${pid}\"]').click();1`);
  log('7. выбран кадр', pid, '| «Перенести» видно:', await js("getComputedStyle(document.querySelector('.js-move')).display!=='none'"));
  await shot(`move_${W}.png`, 520);
  await js("(() => { const s=document.querySelector('.js-move-target'); s.value='" + PITER25 + "'; document.querySelector('.js-move-selected').click(); return 1; })()");
  await sleep(1500);
  log('   в базе альбом кадра:', sql(`SELECT album_id FROM photos_photo WHERE id=${pid}`), '| кадр убран со страницы:', await js(`!document.querySelector('#masonry .photo-item[data-id=\"${pid}\"]')`), '| диалоги:', dialogs.splice(0).join(' / '));
  log('   обратно:', await js(`(() => { const fd=new FormData(); fd.append('ids','${pid}'); fd.append('album','${PITER24}'); fd.append('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]').value); return fetch('/admin/photos/move/',{method:'POST',body:fd}).then(r=>r.json()).then(d=>JSON.stringify(d)); })()`), '| в базе:', sql(`SELECT album_id FROM photos_photo WHERE id=${pid}`));
  ws.close();
} finally { chrome.kill(); }
