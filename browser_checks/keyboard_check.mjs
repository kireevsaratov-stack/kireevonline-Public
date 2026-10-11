// Клавиатура: фото и раскрытие меню доступны клавишей Tab, открываются Enter, просмотр закрывается Esc.
// Сам сообщает «прошло / не прошло». Запуск: node keyboard_check.mjs [адрес альбома]
import { main, openChrome, sleep } from './lib.mjs';

const URL_ = process.argv[2] || '/album/9/';

await main('клавиатура', async t => {
  const page = await openChrome({ width: 1280, height: 900 });
  const key = async k => { for (const type of ['keyDown', 'keyUp']) await page.send('Input.dispatchKeyEvent', { type, key: k, code: k, windowsVirtualKeyCode: { Tab: 9, Enter: 13, Escape: 27 }[k] }); };
  await page.send('Network.setCacheDisabled', { cacheDisabled: true });
  await page.navigate(URL_, 2000);

  const info = await page.js(`(() => { const it=document.querySelector('.photo-item'); const acc=document.querySelector('.js-acc-toggle');
    return { tab: it && it.getAttribute('tabindex'), role: it && it.getAttribute('role'), label: it && it.getAttribute('aria-label'),
             acc: acc ? acc.getAttribute('tabindex') : 'нет на странице' }; })()`);
  t.ok(info.tab === '0' && info.role === 'button' && !!info.label, 'фото доступны клавишей Tab', info.label);
  t.ok(info.acc === '0' || info.acc === 'нет на странице', 'раскрытие меню доступно клавишей Tab');

  await page.js(`document.querySelector('.photo-item').focus(); 1`);
  await key('Enter'); await sleep(700);
  t.ok(await page.js(`document.getElementById('lightbox').classList.contains('open')`), 'Enter открывает фото');
  await key('Escape'); await sleep(500);
  t.ok(!(await page.js(`document.getElementById('lightbox').classList.contains('open')`)), 'Esc закрывает просмотр');
}, { timeout: 60 });
