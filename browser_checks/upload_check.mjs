// Загрузка фото через страницу панели вживую (только копия сайта на Mac, временный админ — как в manage_e2e.mjs).
// Создаёт временный скрытый альбом с «неудобным» названием, загружает в него сгенерированную картинку 2600×1800,
// проверяет по базе и файлу, затем стирает фото и альбом. Ошибка — код выхода 1.
import { tmpdir } from 'node:os';
import { spawn, execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SP = decodeURIComponent(new URL('.', import.meta.url).pathname);
const DB = SP + '../db.sqlite3';
const MEDIA = process.env.MEDIA || SP + '../../backups/media/';
const PW = readFileSync(tmpdir() + '/kireevonline-ui-check-pw.txt', 'utf8').trim();
const BASE = 'http://localhost:8100';
const NAME = 'Проверка загрузки \\ "кавычки" & <b>';
const sql = q => execSync(`sqlite3 "${DB}" "${q.replace(/"/g, '\\"')}"`).toString().trim();
const PORT = 9351;
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${tmpdir()}/kireevonline-chrome-upload`,
  '--no-first-run', '--window-size=1280,900', 'about:blank',
], { stdio: 'ignore' });

const problems = [];
const check = (ok, what) => { console.log((ok ? '✔ ' : '✖ ') + what); if (!ok) problems.push(what); };
let albumId = null;
try {
  let pages;
  for (let i = 0; i < 50; i++) { try { pages = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (pages.length) break; } catch {} await sleep(200); }
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  let n = 0; const wait = new Map(); const errors = [];
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  });
  const send = (method, params = {}) => new Promise(r => { const i = ++n; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async e => { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }); return r.result.exceptionDetails ? 'ОШИБКА: ' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text) : r.result.result?.value; };
  const go = async (url, ms = 2500) => { await send('Page.navigate', { url: BASE + url }); await sleep(ms); };
  await send('Page.enable'); await send('Runtime.enable');

  await go('/admin/login/?next=/admin/');
  await js(`document.getElementById('id_username').value='ui-check';document.getElementById('id_password').value=${JSON.stringify(PW)};document.querySelector('form').submit();1`);
  await sleep(3000);

  // временный скрытый альбом с «неудобным» названием — в первом разделе
  const section = sql('SELECT id FROM photos_section ORDER BY "order" LIMIT 1');
  await go('/admin/');
  const created = await js(`(() => { const fd=new FormData(); fd.append('kind','album'); fd.append('section','${section}'); fd.append('name',${JSON.stringify(NAME)}); fd.append('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]').value); return fetch('/admin/create/',{method:'POST',body:fd}).then(r=>r.json()); })()`);
  albumId = created && created.id;
  check(!!albumId, 'временный альбом создан');

  await go('/admin/upload/');
  check(errors.length === 0, 'страница загрузки без ошибок скриптов' + (errors.length ? ': ' + errors[0] : ''));
  const options = await js(`(() => { const s=document.getElementById('id_section'); s.value='${section}'; s.dispatchEvent(new Event('change')); return Array.from(document.getElementById('id_album').options).map(o=>o.textContent); })()`);
  check(Array.isArray(options) && options.includes(NAME), 'название альбома в списке ровно как есть');

  const result = await js(`(async () => {
    document.getElementById('id_album').value='${albumId}';
    const c=document.createElement('canvas'); c.width=2600; c.height=1800;
    const g=c.getContext('2d'); g.fillStyle='#3a7'; g.fillRect(0,0,2600,1800); g.fillStyle='#fff'; g.fillRect(200,200,800,600);
    const blob=await new Promise(r=>c.toBlob(r,'image/jpeg',0.92));
    const dt=new DataTransfer(); dt.items.add(new File([blob],'проверка-загрузки.jpg',{type:'image/jpeg'}));
    const fi=document.getElementById('id_images'); fi.files=dt.files; fi.dispatchEvent(new Event('change'));
    document.getElementById('submit-btn').click();
    for (let i=0;i<60;i++){ await new Promise(r=>setTimeout(r,500)); const t=document.getElementById('upload-status').textContent; if(t.startsWith('Готово')) return t; }
    return document.getElementById('upload-status').textContent;
  })()`);
  check(/Готово: загружено 1/.test(result || ''), 'загрузка: «' + result + '»');

  const row = sql(`SELECT id, image, thumb, section_id FROM photos_photo WHERE album_id=${albumId || 0}`).split('|');
  check(row.length === 4 && row[3] === section, 'фото в базе, в нужном альбоме и разделе');
  if (row.length === 4) {
    const dims = execSync(`sips -g pixelWidth -g pixelHeight "${MEDIA}${row[1]}"`).toString();
    const w = +dims.match(/pixelWidth: (\d+)/)[1], h = +dims.match(/pixelHeight: (\d+)/)[1];
    check(Math.max(w, h) === 1920, `фото ужато до 1920 по длинной стороне (${w}×${h})`);
    check(!!row[2], 'превью создано');
    // убрать за собой: фото в корзину и навсегда, потом пустой альбом
    await js(`(() => { const t=document.querySelector('[name=csrfmiddlewaretoken]').value; const a=new FormData(); a.append('ids','${row[0]}'); a.append('csrfmiddlewaretoken',t); return fetch('/admin/photos/delete/',{method:'POST',body:a}).then(()=>{ const b=new FormData(); b.append('action','delete'); b.append('ids','${row[0]}'); b.append('csrfmiddlewaretoken',t); return fetch('/admin/trash/action/',{method:'POST',body:b}); }).then(r=>r.status); })()`);
  }
  if (albumId) {
    // вход истёк посреди работы: загрузчик должен остановиться с понятным сообщением и не слать части дальше
    await go('/admin/upload/');
    const count = () => sql(`SELECT count(*) FROM photos_photo WHERE album_id=${albumId}`);
    await js(`(async () => {
      const s=document.getElementById('id_section'); s.value='${section}'; s.dispatchEvent(new Event('change'));
      document.getElementById('id_album').value='${albumId}';
      const c=document.createElement('canvas'); c.width=1200; c.height=800; c.getContext('2d').fillRect(0,0,10,10);
      const blob=await new Promise(r=>c.toBlob(r,'image/jpeg',0.9));
      const dt=new DataTransfer(); dt.items.add(new File([blob],'a.jpg',{type:'image/jpeg'})); dt.items.add(new File([blob],'b.jpg',{type:'image/jpeg'}));
      const fi=document.getElementById('id_images'); fi.files=dt.files; fi.dispatchEvent(new Event('change'));
      return 1;
    })()`);
    await send('Network.enable');
    await send('Network.deleteCookies', { name: 'sessionid', url: BASE });  // «вход истёк»
    const lost = await js(`(async () => {
      document.getElementById('submit-btn').click();
      for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,500)); const t=document.getElementById('upload-status').textContent; if(/^(Готово|Остановлено)/.test(t)) return t; }
      return document.getElementById('upload-status').textContent;
    })()`);
    check(/Остановлено/.test(lost || '') && /войдите снова/.test(lost || ''), 'вход истёк — загрузка остановлена: «' + lost + '»');
    check(count() === '0', 'без входа ничего не загрузилось');
    // войти снова и убрать временный альбом
    await go('/admin/login/?next=/admin/');
    await js(`document.getElementById('id_username').value='ui-check';document.getElementById('id_password').value=${JSON.stringify(PW)};document.querySelector('form').submit();1`);
    await sleep(3000);
    await go('/admin/');
    await js(`(() => { const fd=new FormData(); fd.append('kind','album'); fd.append('id','${albumId}'); fd.append('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]').value); return fetch('/admin/delete/',{method:'POST',body:fd}).then(r=>r.status); })()`);
    check(sql(`SELECT count(*) FROM photos_album WHERE id=${albumId}`) === '0', 'временный альбом и фото убраны');
  }
} finally {
  chrome.kill();
}
console.log(problems.length ? `\n✖ НЕ ПРОШЛО: ${problems.length}` : '\n✔ Всё прошло');
process.exit(problems.length ? 1 : 0);
