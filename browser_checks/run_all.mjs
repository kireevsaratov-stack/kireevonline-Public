// Все проверки в браузере одной командой — на копии сайта на Mac (http://localhost:8100 уже запущен).
// По очереди, каждая — отдельным процессом со своим пределом времени. Для панели управления создаёт
// временного админа ui-check ТОЛЬКО в локальной базе (случайный пароль — в файле во временной папке системы)
// и в любом случае удаляет его и файл с паролем в конце.
// Запуск: node run_all.mjs [--no-admin]   (--no-admin — без панели управления и загрузки)
import { spawn, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { writeFileSync, rmSync } from 'node:fs';
import { HERE, BASE, PW_FILE } from './lib.mjs';

const NO_ADMIN = process.argv.includes('--no-admin');
const GALLERY = HERE + '..';
const PY = HERE + '../../.venv/bin/python';

// проверка → её запуски (все запуски должны пройти); admin — нужна панель управления
const CHECKS = [
  { name: '«Барабан»', runs: [['spin_check.mjs', '1280', '900', '2']] },
  { name: 'ленты барабанов', runs: [['reel_unique_check.mjs']] },
  { name: 'рычаг', runs: [['lever_check.mjs']] },
  { name: 'альбом', runs: [['album_check.mjs'], ['album_check.mjs', '/album/9/', 'phone']] },
  { name: 'шапка', runs: [['nav_check.mjs']] },
  { name: 'клавиатура', runs: [['keyboard_check.mjs']] },
  { name: 'панель управления', admin: true, runs: [['manage_e2e.mjs', '1280'], ['manage_e2e.mjs', '412']] },
  { name: 'загрузка фото', admin: true, runs: [['upload_check.mjs']] },
].filter(c => !(NO_ADMIN && c.admin));
const RUN_TIMEOUT = 240;  // с на один запуск; у каждого скрипта ещё свой предел внутри

const django = code => {
  const r = spawnSync(PY, ['manage.py', 'shell', '-c', code], { cwd: GALLERY, env: { ...process.env, DJANGO_DEBUG: 'True' }, encoding: 'utf8' });
  if (r.status !== 0) throw new Error('manage.py shell: ' + (r.stderr || r.stdout).trim().split('\n').pop());
};
const createAdmin = () => {
  writeFileSync(PW_FILE, randomBytes(18).toString('base64url') + '\n', { mode: 0o600 });
  django(`
import tempfile, os
from django.contrib.auth import get_user_model
pw = open(os.path.join(tempfile.gettempdir(), 'kireevonline-ui-check-pw.txt')).read().strip()
u, _ = get_user_model().objects.get_or_create(username='ui-check')
u.is_staff = u.is_superuser = True; u.set_password(pw); u.save()`);
};
let adminMade = false;
const removeAdmin = () => {
  if (!adminMade) return;
  adminMade = false;
  try {   // вместе с пользователем уходят и его записи журнала действий
    django("from django.contrib.auth import get_user_model; get_user_model().objects.filter(username='ui-check').delete()");
    console.log('временный админ ui-check удалён');
  } catch (e) { console.log('✗ НЕ удалось удалить временного админа ui-check:', e.message); process.exitCode = 1; }
  rmSync(PW_FILE, { force: true });
};
let child = null;
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => { console.log(`\nпрервано (${sig})`); if (child) child.kill('SIGTERM'); removeAdmin(); process.exit(1); });

function runOne(args) {
  return new Promise(resolve => {
    const t0 = Date.now();
    child = spawn(process.execPath, args, { cwd: HERE, stdio: ['ignore', 'pipe', 'pipe'] });
    const out = d => process.stdout.write(d.toString().replace(/^(?=.)/gm, '  '));
    child.stdout.on('data', out); child.stderr.on('data', out);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); setTimeout(() => child && child.kill('SIGKILL'), 3000); }, RUN_TIMEOUT * 1000);
    child.on('close', code => {
      clearTimeout(timer); child = null;
      resolve({ ok: code === 0 && !timedOut, secs: Math.round((Date.now() - t0) / 1000), timedOut });
    });
  });
}

const results = [];
try {
  try { await fetch(BASE + '/', { signal: AbortSignal.timeout(10000) }); }
  catch { console.log(`✗ копия сайта не отвечает на ${BASE} — сначала запустить её (скил browser-check, шаг 1)`); process.exit(1); }
  if (CHECKS.some(c => c.admin)) { createAdmin(); adminMade = true; console.log('временный админ ui-check создан в локальной базе'); }
  for (const c of CHECKS) {
    const runs = [];
    for (const args of c.runs) {
      console.log(`\n── ${c.name}: node ${args.join(' ')}`);
      runs.push({ args, ...(await runOne(args)) });
    }
    results.push({ ...c, runs });
  }
} finally {
  removeAdmin();
}

console.log('\n══ Итог');
for (const c of results) for (const r of c.runs)
  console.log(`${r.ok ? '✓' : '✗'} ${c.name.padEnd(18)} node ${r.args.join(' ')}  (${r.secs} с${r.timedOut ? ', время вышло' : ''})`);
const passed = results.filter(c => c.runs.every(r => r.ok)).length;
const runsTotal = results.reduce((n, c) => n + c.runs.length, 0);
console.log(`\n${passed} из ${results.length} прошли (запусков: ${runsTotal})${NO_ADMIN ? ' — без панели управления (--no-admin)' : ''}`);
if (passed < results.length) process.exitCode = 1;
