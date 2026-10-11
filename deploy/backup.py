#!/usr/bin/env python3
"""Бэкап сайта kireevonline.ru на Mac — ТОЛЬКО ЧТЕНИЕ сервера.

    cd ~/"Claude Code/kireevonline/gallery" && python3 deploy/backup.py

Скачивает в папку kireevonline/backups:
- свежую копию базы (backups/db/db_<дата>_server.sqlite3);
- новые и изменённые фото (backups/media) — только недостающие, повторный запуск быстрый.
На Mac ничего не удаляется, даже если фото удалены на сервере.
Работает через шлюз только-для-чтения: на сервере ничего не создаётся и не меняется.
Запускать могут и Роман, и Claude.
    --db-only   только база, без фото
"""

import argparse

from server import BACKUPS, ReadOnly, fail, now_stamp, ok, say, warn


def backup_db(ro):
    say('База…')
    local = ro.download_db(BACKUPS / 'db' / ('db_%s_server.sqlite3' % now_stamp()))
    ok('backups/db/%s (%d КБ), совпадает с сервером' % (local.name, local.stat().st_size // 1024))


def backup_media(ro):
    say('Фото…')
    listing = ro.call('medialist')
    if not listing.get('ok'):
        fail('Не удалось получить список фото (%s):\n%s' % (listing.get('step'), listing.get('output')))
    dest = BACKUPS / 'media'
    dest.mkdir(parents=True, exist_ok=True)
    remote = {rel: size for rel, size in listing['files']}
    local = {str(p.relative_to(dest)): p.stat().st_size for p in dest.rglob('*') if p.is_file()}
    need = sorted(rel for rel, size in remote.items() if local.get(rel) != size)
    only_mac = len([rel for rel in local if rel not in remote and not rel.endswith('.DS_Store')])
    say(
        '  на сервере %d файлов, на Mac %d; скачать %d (%.0f МБ)'
        % (len(remote), len(local), len(need), sum(remote[r] for r in need) / 1e6)
    )
    for i in range(0, len(need), 300):
        ro.download_media(need[i : i + 300], dest)
        say('  …скачано %d из %d' % (min(i + 300, len(need)), len(need)))
    bad = [r for r in need if not (dest / r).is_file() or (dest / r).stat().st_size != remote[r]]
    if bad:
        fail('%d файлов скачались не полностью. Запустите ещё раз.' % len(bad))
    ok('фото на Mac совпадают с сервером (%d файлов)' % len(remote))
    if only_mac:
        warn('%d файлов есть только на Mac (удалены на сервере) — оставлены.' % only_mac)


def main():
    ap = argparse.ArgumentParser(description='Бэкап сайта kireevonline.ru на Mac')
    ap.add_argument('--db-only', action='store_true', help='только база')
    args = ap.parse_args()
    say('=== Бэкап kireevonline.ru → %s ===' % BACKUPS)
    ro = ReadOnly()
    if ro.fake:
        say('(ТЕСТОВЫЙ РЕЖИМ: «сервер» — папка %s)' % ro.fake)
    backup_db(ro)
    if not args.db_only:
        backup_media(ro)
    (BACKUPS / 'last-backup.txt').write_text(now_stamp() + '\n')
    say('')
    say('✔ Бэкап готов.')


if __name__ == '__main__':
    main()
