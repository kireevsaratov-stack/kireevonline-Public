---
name: browser-check
description: Проверить kireevonline.ru в настоящем браузере на копии сайта на Mac — «Барабан», альбом, панель управления (временным админом в локальной базе), шапка; снимки на компьютере и телефоне для Романа. Использовать перед выкладкой и после правок вида или скриптов страниц.
---

# Проверка в браузере

Всё — на копии сайта на Mac (база `gallery/db.sqlite3`, фото из `../backups/media`). Настоящий сайт не трогается.
Скрипты — `browser_checks/` (описание в `browser_checks/README.md`): Chrome без окна, временный профиль
во временной папке системы.

## 1. Копия сайта
Встроенный браузер: `preview_start` с именем `kireevonline` (конфиг `~/Claude Code/kireevonline/.claude/launch.json`).
Или вручную из `gallery/`:
`DJANGO_DEBUG=True DJANGO_MEDIA_ROOT=../backups/media ../.venv/bin/python manage.py runserver 127.0.0.1:8100`.
Свёрнутая панель браузера останавливает анимации — «Барабан» проверять только скриптами ниже.

## 2. Публичные страницы
Из `browser_checks/`:
- `node spin_check.mjs 1280 900 2` и `node reel_unique_check.mjs` — «Барабан»;
- `node album_check.mjs` и `node album_check.mjs http://localhost:8100/album/9/ phone` — альбом;
- `node lever_check.mjs` — рычаг;
- `node keyboard_check.mjs` — клавиатура (сам говорит «прошло / не прошло»).

## 3. Панель управления — временным админом ТОЛЬКО в локальной базе
```bash
T=$(python3 -c 'import tempfile;print(tempfile.gettempdir())')
python3 -c "import secrets;print(secrets.token_urlsafe(18))" > "$T/kireevonline-ui-check-pw.txt"
../.venv/bin/python manage.py shell -c "
import tempfile, os
from django.contrib.auth import get_user_model
pw = open(os.path.join(tempfile.gettempdir(), 'kireevonline-ui-check-pw.txt')).read().strip()
u, _ = get_user_model().objects.get_or_create(username='ui-check')
u.is_staff = u.is_superuser = True; u.set_password(pw); u.save()"
cd browser_checks && node manage_e2e.mjs 1280 && node manage_e2e.mjs 412 && node upload_check.mjs; cd ..
```
Сразу после — удалить пользователя (вместе с его записями журнала) и файл с паролем:
```bash
../.venv/bin/python manage.py shell -c "from django.contrib.auth import get_user_model; get_user_model().objects.filter(username='ui-check').delete()"
rm -f "$T/kireevonline-ui-check-pw.txt"
```
Сессию, созданную в `manage.py shell`, сервер не примет (у локального сервера случайный SECRET_KEY) — только вход
через форму, как делает скрипт.

## 4. Снимки для Романа
`node view_shot.mjs <адрес> 1280 800 <файл>.png` и `node view_shot.mjs <адрес> 412 900 <файл>.png phone`,
для альбома с раскрытыми записками — `page_shot.mjs`. Посмотреть самому, затем отправить Роману (SendUserFile).
Роман смотрит с MacBook и телефона Fold 7. Снимки в `browser_checks/` в git не попадают.
