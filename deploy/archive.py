#!/usr/bin/env python3
"""Полный архив сайта «под ключ» для облака — из него сайт поднимается с нуля,
без этого Mac, без GitHub и без нынешнего хостинга. Сервер только читается.

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/backup.py && python3 deploy/archive.py

Кладёт в ../backups/archives/kireevonline-backup-<дата>.zip:
  ВОССТАНОВЛЕНИЕ.md, ПАСПОРТ-САЙТА.md — что делать и что где;
  code/gallery.bundle (весь git с историей) и code/gallery/ (код файлами);
  db/db.sqlite3 — база (без учётных записей и сессий входа — паролей в архиве нет);
  media/ — все фото и превью ровно как на сервере;
  server/ — шаблоны настроек хостинга; deploy/verify_backup.py; SHA256SUMS.txt.
"""

import datetime
import hashlib
import io
import shutil
import sqlite3
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

from server import BACKUPS, REPO, ReadOnly, fail, git, git_ok, last_migration, ok, say, warn
from verify_backup import verify

ARCHIVES = BACKUPS / 'archives'
STORE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bundle', '.zip'}
ACCOUNT_TABLES = ['auth_user_user_permissions', 'auth_user_groups', 'django_admin_log', 'django_session', 'auth_user']

HTACCESS = """DirectoryIndex site.wsgi
Options +ExecCGI
AddHandler wsgi-script .wsgi
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^(.*)$ /site.wsgi/$1 [QSA,PT,L]
"""

SITE_WSGI = """# Пример public_html/site.wsgi для хостинга с Apache mod_wsgi (как на Sprinthost).
# Пути и значения в <угловых скобках> заменить. Секретный ключ — НОВЫЙ:
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
import os, sys

activate_this = '/home/<пользователь>/python/bin/activate_this.py'
with open(activate_this) as f:
    exec(f.read(), {'__file__': activate_this})

sys.path.insert(0, '/home/<пользователь>/domains/kireevonline.ru/gallery')

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['ALLOWED_HOSTS'] = 'kireevonline.ru,www.kireevonline.ru'
os.environ['DJANGO_SECRET_KEY'] = '<НОВЫЙ СЕКРЕТНЫЙ КЛЮЧ>'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
"""


def restore_md(d):
    return f"""# Восстановление сайта kireevonline.ru из архива

Архив собран {d['when']}. На сайте в этот момент: {d['active']} фото в {d['albums']} альбомах
(+{d['trash']} в корзине), код версии {d['server_head']}.

## Роману

1. Скачайте этот архив из облака на любой компьютер.
2. Откройте Claude Code и скажите: «Вот архив бэкапа сайта kireevonline.ru, восстанови его»,
   укажите, где лежит файл.
3. Понадобится: доступ к хостингу (старому или новому) и к регистратору домена —
   см. ПАСПОРТ-САЙТА.md. Пароль администратора сайта вы зададите новый: учётных записей
   в архиве нет намеренно, чтобы в облаке не лежали пароли.

## Для Claude / разработчика

0. Целостность: распаковать архив, из его корня `shasum -a 256 -c SHA256SUMS.txt`, затем
   `python3 deploy/verify_backup.py .` — должно быть «У всех фото есть файл и превью»,
   {d['active']} фото на сайте.
1. Код: `git clone code/gallery.bundle gallery && cd gallery && git checkout {d['server_head_full']}`
   — именно эта версия работала на сервере и согласована с базой архива (вся история — в bundle).
   Та же версия файлами — `code/gallery/`.
   Правила работы и устройство — `gallery/CLAUDE.md`, для человека — `gallery/README.md`.
2. Python 3.13+ (как в pyproject.toml; на сервере был {d['server_python']}):
   `python3 -m venv .venv && .venv/bin/pip install -r gallery/requirements.txt`.
   Если со свежими версиями что-то не так — точные проверенные версии:
   `.venv/bin/pip install -r code/requirements-tested.txt`.
3. База: `cp db/db.sqlite3 gallery/db.sqlite3`, затем в gallery/:
   `../.venv/bin/python manage.py migrate` (ожидается «No migrations to apply») и
   `../.venv/bin/python manage.py createsuperuser` — пароль вводит Роман сам.
4. Фото: папка `media/` целиком. Локально: `DJANGO_MEDIA_ROOT=<путь>/media`;
   на хостинге — `public_html/media` рядом с кодом (settings.py сам находит public_html).
5. Проверка на компьютере: `DJANGO_DEBUG=True DJANGO_MEDIA_ROOT=../media ../.venv/bin/python manage.py runserver`
   (без DJANGO_DEBUG=True сайт работает в «боевом» режиме и уводит на https),
   открыть альбомы — фото на местах, порядок сохранён (он в базе).
6. Хостинг (схема Sprinthost, Apache mod_wsgi):
   `~/domains/kireevonline.ru/gallery/` — код + db.sqlite3;
   `~/domains/kireevonline.ru/public_html/` — media/, static/, site.wsgi, .htaccess
   (шаблоны — в `server/`, секретный ключ сгенерировать новый);
   `manage.py collectstatic --noinput`. Если системный SQLite на хостинге старый —
   `pip install pysqlite3-binary` (settings.py подхватит сам).
   Перезапуск сайта — обновить время файла site.wsgi.
7. После восстановления: инструменты выкладки/отката/бэкапа — `gallery/deploy/`
   (в архивах до 08.10.2026 — `gallery/tools/`), пути хостинга в `deploy/server.py` поправить
   под новый сервер; ключ доступа только для чтения — заново через `deploy/setup_readonly.py`.
"""


def passport_md(d):
    albums = '\n'.join(
        '| %s | %s | %d |%s' % (c, s, n, ' скрыт |' if h else ' |') for (c, s, h), n in d['album_list'].items()
    )
    return f"""# Паспорт сайта kireevonline.ru

Состояние на {d['when']}. Паролей и ключей здесь и в архиве нет.

## Без чего сайт не вернуть (архив это не заменит)

| Что | Где | Важно |
|---|---|---|
| Домен kireevonline.ru | регистратор SPRINTNAMES-RU (Sprinthost) | оплачен до {d['paid_till']}, освобождается {d['free_date']} — **продлевать!** |
| Хостинг | Sprinthost, аккаунт владельца | тот же аккаунт, что и домен |
| Облако с этим архивом | ваше облако | помнить логин и пароль |
| Почта для восстановления паролей | ваша основная почта | к ней привязаны Sprinthost и GitHub |

## Где что было

- Код: приватный репозиторий на GitHub + полная копия в этом архиве.
- Сервер (на момент архива): <адрес сервера>; код `/home/user/domains/kireevonline.ru/gallery`,
  фото `/home/user/domains/kireevonline.ru/public_html/media`, Python-окружение `/home/user/python`.
- Mac: `~/Claude Code/kireevonline/` (gallery — код, backups — бэкапы).

## Версии

Python на сервере {d['server_python']}, Django {d['server_django']}.
Библиотеки, с которыми сайт проверен на Mac:
```
{d['freeze']}
```

## Содержимое

{d['active']} фото на сайте, {d['trash']} в корзине, {d['files']} файлов фото и превью ({d['media_mb']} МБ).

| Раздел | Альбом | Фото | |
|---|---|---|---|
{albums}
"""


def sanitized_db(src, dst):
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ACCOUNT_TABLES:
        if t in names:
            con.execute('DELETE FROM "%s"' % t)
    con.commit()
    bad = con.execute('PRAGMA foreign_key_check').fetchall()
    con.execute('VACUUM')
    con.close()
    if bad:
        fail('После удаления учётных записей нарушились связи в базе: %s' % bad[:3])


def applied_migration(db):
    """Последний применённый шаг базы приложения photos в этой копии базы."""
    import sqlite3

    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    row = con.execute("SELECT name FROM django_migrations WHERE app='photos' ORDER BY name DESC LIMIT 1").fetchone()
    con.close()
    return row[0] if row else None


def referenced_files(db):
    """Все файлы фото и превью, на которые ссылается база (и в корзине тоже)."""
    import sqlite3

    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    rows = con.execute('SELECT image, thumb FROM photos_photo').fetchall()
    con.close()
    return {name for row in rows for name in row if name}


def main():
    stamp = datetime.datetime.now().strftime('%Y-%m-%d')
    say('=== Полный архив kireevonline.ru ===')
    ro = ReadOnly()
    st = ro.call('state')
    listing = ro.call('medialist')
    if not st.get('ok') or not listing.get('ok'):
        fail('Не удалось прочитать сервер: %s' % (st.get('output') or listing.get('output')))

    dbs = sorted((BACKUPS / 'db').glob('db_*_server.sqlite3'))
    if not dbs or time.time() - dbs[-1].stat().st_mtime > 6 * 3600:
        fail('Нет свежей копии базы (моложе 6 часов). Сначала: python3 deploy/backup.py')
    media = BACKUPS / 'media'
    server_files = {rel: size for rel, size in listing['files']}
    stale = [r for r, s in server_files.items() if not (media / r).is_file() or (media / r).stat().st_size != s]
    if stale:
        fail('На Mac нет %d актуальных фото с сервера. Сначала: python3 deploy/backup.py' % len(stale))
    if git('status', '--porcelain', '--untracked-files=no'):
        warn('В коде на Mac есть несохранённые правки — в архив попадёт последняя сохранённая версия.')

    ARCHIVES.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVES / ('.tmp-' + stamp)
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        db = tmp / 'db.sqlite3'
        sanitized_db(dbs[-1], db)
        ok('база: %s без учётных записей и сессий' % dbs[-1].name)
        info = verify(db, media, quiet=True)
        if info['missing']:
            fail('У %d записей в базе нет файлов: %s' % (len(info['missing']), info['missing'][:3]))
        # В архив — все файлы сервера И все файлы, на которые ссылается эта копия базы (если фото успели
        # стереть на сервере после копии базы, его файл берётся из бэкапа на Mac): база и фото согласованы.
        referenced = referenced_files(db)
        archive_files = sorted(set(server_files) | referenced)
        server_head = st['head']
        if not git_ok('cat-file', '-e', server_head + '^{commit}'):
            fail('Версия кода на сервере (%s) неизвестна этому Mac — сначала git fetch.' % server_head[:7])
        # копия базы должна подходить к этому коду: последний шаг базы в копии = последний шаг в коде
        # (иначе, например после отката, архив соединил бы старый код с более новой базой — аудит 2)
        db_step, code_step = applied_migration(db), last_migration(server_head)
        if db_step != code_step:
            fail(
                'Копия базы (шаг %s) не подходит к коду на сервере (шаг %s) — между ними была выкладка или откат.\n'
                'Сначала свежая копия: python3 deploy/backup.py --db-only' % (db_step, code_step)
            )
        bundle = tmp / 'gallery.bundle'
        git('bundle', 'create', str(bundle), '--all')
        ok('код: вся история git (%d КБ)' % (bundle.stat().st_size // 1024))

        whois = subprocess.run(
            ['whois', '-h', 'whois.tcinet.ru', 'kireevonline.ru'], capture_output=True, text=True, timeout=30
        ).stdout

        def field(k):
            return next(
                (line.split(':', 1)[1].strip()[:10] for line in whois.splitlines() if line.lower().startswith(k + ':')),
                'не удалось узнать',
            )

        freeze = subprocess.run(
            [str(REPO.parent / '.venv' / 'bin' / 'python'), '-m', 'pip', 'freeze'], capture_output=True, text=True
        ).stdout.strip()
        d = {
            'when': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
            'active': info['active'],
            'trash': info['trash'],
            'album_list': info['albums'],
            'albums': len([k for k in info['albums'] if k[1] != '(без альбома)']),
            'server_head': st['head'][:7],
            'server_head_full': st['head'],
            'server_python': st['python'],
            'server_django': st['django'],
            'paid_till': field('paid-till'),
            'free_date': field('free-date'),
            'freeze': freeze,
            'files': len(server_files),
            'media_mb': round(sum(server_files.values()) / 1e6),
        }

        root = 'kireevonline-backup-%s/' % stamp
        out = ARCHIVES / ('kireevonline-backup-%s.zip' % stamp)
        part = out.with_suffix('.zip.part')
        sums = []

        def add(zf, name, path=None, data=None):
            comp = zipfile.ZIP_STORED if Path(name).suffix.lower() in STORE_EXT else zipfile.ZIP_DEFLATED
            h = hashlib.sha256()
            if path is not None:
                with open(path, 'rb') as src, zf.open(_info(root + name, comp), 'w') as dst:
                    for chunk in iter(lambda: src.read(1 << 20), b''):
                        h.update(chunk)
                        dst.write(chunk)
            else:
                h.update(data)
                zf.writestr(_info(root + name, comp), data)
            sums.append('%s  %s' % (h.hexdigest(), name))

        say('Собираю архив (~%d МБ)…' % d['media_mb'])
        with zipfile.ZipFile(part, 'w', allowZip64=True) as zf:
            add(zf, 'ВОССТАНОВЛЕНИЕ.md', data=restore_md(d).encode())
            add(zf, 'ПАСПОРТ-САЙТА.md', data=passport_md(d).encode())
            add(zf, 'db/db.sqlite3', path=db)
            add(zf, 'code/gallery.bundle', path=bundle)
            add(zf, 'code/requirements-tested.txt', data=(freeze + '\n').encode())
            code_tar = subprocess.run(
                ['git', 'archive', '--format=tar', server_head], cwd=REPO, capture_output=True, check=True
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(code_tar)) as tar:
                for m in tar.getmembers():
                    if m.isfile():
                        add(zf, 'code/gallery/' + m.name, data=tar.extractfile(m).read())
            add(zf, 'deploy/verify_backup.py', path=REPO / 'deploy' / 'verify_backup.py')
            add(zf, 'server/.htaccess', data=HTACCESS.encode())
            add(zf, 'server/site.wsgi.example', data=SITE_WSGI.encode())
            for i, rel in enumerate(archive_files, 1):
                add(zf, 'media/' + rel, path=media / rel)
                if i % 1000 == 0:
                    say('  …фото %d из %d' % (i, len(archive_files)))
            zf.writestr(_info(root + 'SHA256SUMS.txt', zipfile.ZIP_DEFLATED), '\n'.join(sums) + '\n')
        with zipfile.ZipFile(part) as zf:
            broken = zf.testzip()
            packed = {n[len(root + 'media/') :] for n in zf.namelist() if n.startswith(root + 'media/')}
        if broken:
            fail('Архив повреждён при записи (%s). Запустите ещё раз.' % broken)
        lost = sorted(referenced - packed)
        if lost:  # проверка уже собранного архива, а не папки на Mac
            fail('В собранном архиве нет %d файлов, на которые ссылается база: %s' % (len(lost), lost[:3]))
        part.replace(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    say('')
    say('✔ Архив готов: %s' % out)
    say(
        '  %d МБ, %d файлов; внутри %d фото на сайте в %d альбомах (+%d в корзине)'
        % (out.stat().st_size // 1_000_000, len(sums) + 1, d['active'], d['albums'], d['trash'])
    )
    say('  Загрузите этот файл в облако. Паролей и ключей в нём нет.')


def _info(name, comp):
    zi = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    zi.compress_type = comp
    zi.external_attr = 0o644 << 16
    return zi


if __name__ == '__main__':
    main()
