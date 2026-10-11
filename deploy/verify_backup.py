#!/usr/bin/env python3
"""Проверка бэкапа или распакованного архива сайта: у каждой фотографии в базе
есть файл фото и превью, сколько фото в каждом альбоме. Только стандартный Python,
Django не нужен, ничего не меняет.

    python3 deploy/verify_backup.py <папка с db/db.sqlite3 и media/>
    python3 deploy/verify_backup.py --db <файл базы> --media <папка фото>
Код возврата 0 — всё на месте, 1 — чего-то не хватает.
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def verify(db, media, quiet=False):
    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # база с 08.10.2026: разделы и альбомы; в старых архивах — «категории» и «подкатегории»
    sec, alb, sec_id, alb_id = (
        ('photos_section', 'photos_album', 'section_id', 'album_id')
        if 'photos_album' in tables
        else ('photos_category', 'photos_subcategory', 'category_id', 'subcategory_id')
    )
    rows = con.execute(f'''
        SELECT p.id, c.name, s.name, s.hidden, p.image, p.thumb, p.is_deleted
        FROM photos_photo p JOIN {sec} c ON c.id = p.{sec_id}
        LEFT JOIN {alb} s ON s.id = p.{alb_id}
        ORDER BY c."order", c.name, s."order", s.name, p."order"''').fetchall()
    con.close()
    active = [r for r in rows if not r[6]]
    trash = [r for r in rows if r[6]]
    missing = [r[4] for r in rows if not (media / r[4]).is_file()]
    missing += [r[5] for r in rows if r[5] and not (media / r[5]).is_file()]
    albums = {}
    for r in active:
        key = (r[1], r[2] or '(без альбома)', bool(r[3]))
        albums[key] = albums.get(key, 0) + 1
    if not quiet:
        print('База:  %s' % db)
        print('Фото:  %s' % media)
        loose = sum(n for (_, sub, _), n in albums.items() if sub == '(без альбома)')
        print(
            'Фото на сайте: %d, в корзине: %d, альбомов: %d%s'
            % (
                len(active),
                len(trash),
                len([k for k in albums if k[1] != '(без альбома)']),
                ', фото без альбома: %d' % loose if loose else '',
            )
        )
        for (cat, sub, hidden), n in albums.items():
            print('  %s / %s: %d%s' % (cat, sub, n, '  (скрыт на сайте)' if hidden else ''))
        if missing:
            print('\n✖ НЕ ХВАТАЕТ ФАЙЛОВ: %d, например: %s' % (len(missing), ', '.join(missing[:5])))
        else:
            print('\n✔ У всех фото (и в корзине тоже) есть файл и превью.')
    return {'active': len(active), 'trash': len(trash), 'albums': albums, 'missing': missing}


def main():
    ap = argparse.ArgumentParser(description='Проверка бэкапа сайта kireevonline.ru')
    ap.add_argument('folder', nargs='?', help='папка с db/db.sqlite3 и media/')
    ap.add_argument('--db')
    ap.add_argument('--media')
    args = ap.parse_args()
    if args.folder:
        db, media = Path(args.folder) / 'db' / 'db.sqlite3', Path(args.folder) / 'media'
    elif args.db and args.media:
        db, media = Path(args.db), Path(args.media)
    else:
        ap.error('укажите папку или --db и --media')
    if not db.is_file() or not media.is_dir():
        sys.exit('Не найдены база %s или папка фото %s' % (db, media))
    sys.exit(1 if verify(db, media)['missing'] else 0)


if __name__ == '__main__':
    main()
