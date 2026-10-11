// Общее для всех проверок: Chrome без окна (свой временный профиль на каждый запуск, после — стирается),
// связь с ним по DevTools-протоколу, «прошло / не прошло» и общий предел времени.
// Без библиотек: только Google Chrome и Node 24 (fetch и WebSocket встроены).
//
//   import { main, openChrome } from './lib.mjs';
//   await main('название проверки', async t => {
//     const page = await openChrome({ width: 1280, height: 900 });
//     await page.navigate('/album/9/', 3000);
//     t.ok(await page.js('document.title') !== '', 'у страницы есть заголовок');
//   });
//
// main() сам закрывает Chrome, печатает итог («ПРОШЛО» / «НЕ ПРОШЛО (n из m)») и ставит код выхода.
// Предел времени — 120 с (или свой в main(…, { timeout }), или переменная TIMEOUT в секундах):
// зависший Chrome не держит скрипт вечно.
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

export { sleep };
export const HERE = decodeURIComponent(new URL('.', import.meta.url).pathname);
export const BASE = 'http://localhost:8100';                 // только копия сайта на Mac
export const DB = join(HERE, '../db.sqlite3');
export const PW_FILE = join(tmpdir(), 'kireevonline-ui-check-pw.txt');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const CALL_TIMEOUT = 30000;                                  // один вызов Chrome дольше 30 с — значит, завис

// ── уборка: все открытые Chrome и их профили — при любом выходе
const opened = new Set();
function killAll() {
  for (const c of opened) {
    try { c.proc.kill('SIGKILL'); } catch {}
    try { rmSync(c.profile, { recursive: true, force: true }); } catch {}
  }
  opened.clear();
}
process.on('exit', killAll);
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => { console.log(`\n✗ прервано (${sig})`); killAll(); process.exit(1); });

// ── база копии сайта (через sqlite3 без оболочки — кавычки в запросе не ломаются)
export const sql = q => execFileSync('sqlite3', [DB, q]).toString().trim();

// пароль временного админа ui-check (создаёт run_all.mjs или скил browser-check); нет файла — null
export const adminPassword = () => existsSync(PW_FILE) ? readFileSync(PW_FILE, 'utf8').trim() : null;

// ── Chrome
// width/height — размер экрана, scale — плотность точек (×2 при 1440 у нового Chrome вешает снимок),
// mobile — телефон (с касаниями), extraArgs — добавочные ключи Chrome, fonts — пускать к шрифтам Google
// (по умолчанию нет: проверка не должна зависеть от чужого сервера).
export async function openChrome({ width = 1280, height = 900, scale = 1, mobile = false, extraArgs = [], fonts = false } = {}) {
  const profile = mkdtempSync(join(tmpdir(), 'kireevonline-chrome-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', `--window-size=${width},${height}`,
    ...(fonts ? [] : ['--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND']),
    ...extraArgs, 'about:blank',
  ], { stdio: 'ignore' });
  const me = { proc, profile };
  opened.add(me);
  let exited = false;
  proc.on('exit', () => { exited = true; });

  // свободный порт выбирает сам Chrome и пишет его в DevToolsActivePort
  let port = null, pageInfo = null;
  for (let i = 0; i < 100 && !pageInfo; i++) {
    if (exited) throw new Error('Chrome не запустился');
    try {
      port ??= +readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0];
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      pageInfo = list.find(p => p.type === 'page');
    } catch {}
    if (!pageInfo) await sleep(100);
  }
  if (!pageInfo) throw new Error('Chrome не ответил за 10 с');

  const ws = new WebSocket(pageInfo.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.addEventListener('open', ok, { once: true }); ws.addEventListener('error', fail, { once: true }); });
  let n = 0;
  const wait = new Map(), listeners = new Map();
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); return; }
    for (const f of listeners.get(m.method) || []) f(m.params);
  });

  // send — любой вызов протокола; ошибка Chrome — исключение
  const send = (method, params = {}, ms = CALL_TIMEOUT) => new Promise((ok, fail) => {
    const i = ++n;
    const timer = setTimeout(() => { wait.delete(i); fail(new Error(`Chrome не ответил на ${method} за ${ms / 1000} с`)); }, ms);
    wait.set(i, m => { clearTimeout(timer); m.error ? fail(new Error(`${method}: ${m.error.message}`)) : ok(m.result); });
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  // on — подписка на событие Chrome (Network.requestWillBeSent, Page.javascriptDialogOpening…)
  const on = (method, f) => { if (!listeners.has(method)) listeners.set(method, []); listeners.get(method).push(f); };
  const once = (method, ms) => new Promise((ok, fail) => {
    const timer = setTimeout(() => fail(new Error(`не дождались ${method} за ${ms / 1000} с`)), ms);
    const f = p => { clearTimeout(timer); listeners.set(method, listeners.get(method).filter(x => x !== f)); ok(p); };
    on(method, f);
  });

  // js — выполнить выражение на странице и вернуть значение (обещания дожидается); ошибка на странице — исключение
  const js = async (expr, ms) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }, ms);
    if (r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('ошибка на странице: ' + (d.exception?.description || d.text).split('\n')[0]);
    }
    return r.result.value;
  };

  const setViewport = async ({ width: w = width, height: h = height, scale: s = scale, mobile: mob = mobile } = {}) => {
    await send('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: +s, mobile: !!mob });
    await send('Emulation.setTouchEmulationEnabled', { enabled: !!mob, maxTouchPoints: mob ? 5 : 1 });
  };

  // navigate — открыть адрес (свой — от BASE), дождаться загрузки и ещё waitMs (анимации, догрузка)
  const navigate = async (url, waitMs = 1000) => {
    const loaded = once('Page.loadEventFired', 30000);
    await send('Page.navigate', { url: /^https?:/.test(url) ? url : BASE + url });
    await loaded;
    await sleep(waitMs);
  };

  // screenshot — снимок в файл (относительный путь — в папку browser_checks); clip — {x,y,width,height}
  const screenshot = async (file, { clip, ms = 60000 } = {}) => {
    const s = await send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip: { scale: 1, ...clip } } : {}) }, ms);
    const path = file.startsWith('/') ? file : join(HERE, file);
    writeFileSync(path, Buffer.from(s.data, 'base64'));
    return path;
  };

  const close = async () => {
    try { ws.close(); } catch {}
    if (!exited) {
      proc.kill('SIGTERM');
      for (let i = 0; i < 30 && !exited; i++) await sleep(100);
      if (!exited) proc.kill('SIGKILL');
    }
    rmSync(profile, { recursive: true, force: true });
    opened.delete(me);
  };

  await send('Page.enable');
  await setViewport();
  return { send, on, once, js, navigate, screenshot, setViewport, close, ws };
}

// вход в панель через её страницу (сессию из manage.py shell сервер не примет — у него свой SECRET_KEY)
export async function login(page, password = adminPassword()) {
  if (!password) throw new Error(`нет файла с паролем временного админа (${PW_FILE}) — запускать через run_all.mjs`);
  await page.navigate('/admin/login/?next=/admin/', 500);
  const loaded = page.once('Page.loadEventFired', 30000);
  await page.js(`document.getElementById('id_username').value='ui-check';document.getElementById('id_password').value=${JSON.stringify(password)};document.querySelector('form').submit();1`);
  await loaded;
  await sleep(500);
  return !(await page.js('location.pathname')).includes('/login/');
}

// ── «прошло / не прошло»
export function checker(name) {
  const rows = [];
  const t = {
    name,
    // ok(условие, что проверено, подробности) — строка сразу в вывод, чтобы при зависании было видно, где
    ok(cond, what, details) {
      const pass = !!cond;
      rows.push({ pass, what });
      console.log(`${pass ? '✓' : '✗'} ${what}${details !== undefined ? ' — ' + (typeof details === 'string' ? details : JSON.stringify(details)) : ''}`);
      return pass;
    },
    info: (...a) => console.log('  ', ...a),       // замеры для человека, на итог не влияют
    get failed() { return rows.filter(r => !r.pass).length; },
    finish() {
      const bad = rows.filter(r => !r.pass);
      if (!rows.length) { bad.push({ what: 'ни одной проверки не выполнено' }); rows.push(bad[0]); }
      console.log(bad.length ? `\n${name}: НЕ ПРОШЛО (${bad.length} из ${rows.length})` : `\n${name}: ПРОШЛО (${rows.length} из ${rows.length})`);
      for (const r of bad) console.log('  ✗ ' + r.what);
      process.exitCode = bad.length ? 1 : 0;
      return !bad.length;
    },
  };
  return t;
}

// main — обёртка проверки: предел времени, исключение = «не прошло», Chrome закрыт в любом случае
export async function main(name, fn, { timeout = 120 } = {}) {
  const t = checker(name);
  const limit = +(process.env.TIMEOUT || timeout);
  const timer = setTimeout(() => {
    t.ok(false, `время вышло (${limit} с) — Chrome или страница зависли`);
    killAll();
    t.finish();
    process.exit(1);
  }, limit * 1000);
  try {
    await fn(t);
  } catch (e) {
    t.ok(false, 'проверка оборвалась: ' + (e && e.message || e));
  } finally {
    clearTimeout(timer);
    for (const c of [...opened]) { try { c.proc.kill('SIGKILL'); } catch {} }
    await sleep(200);
    killAll();
  }
  return t.finish();
}
