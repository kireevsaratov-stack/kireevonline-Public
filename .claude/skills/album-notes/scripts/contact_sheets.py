"""Листы со ВСЕМИ фото одного альбома подряд, как на сайте: по 30 на лист, с порядковым номером и № фото.

Запуск из gallery/:
    ALBUM=<id альбома> ../.venv/bin/python manage.py shell < .claude/skills/album-notes/scripts/contact_sheets.py
Листы — во временную папку системы (путь печатается), фото берутся из ../backups/media.
"""

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from photos.models import Album

ALBUM = int(os.environ['ALBUM'])
MEDIA = Path('../backups/media').resolve()
OUT = Path(os.environ.get('OUT') or Path(tempfile.gettempdir()) / 'kireevonline-album-sheets')
OUT.mkdir(parents=True, exist_ok=True)
COLS, ROWS, TILE, HEAD = 6, 5, 190, 22

album = Album.objects.get(pk=ALBUM)
photos = list(album.photos.filter(is_deleted=False))
per = COLS * ROWS
parts = (len(photos) + per - 1) // per
for part in range(parts):
    chunk = photos[part * per : (part + 1) * per]
    sheet = Image.new('RGB', (COLS * TILE, ROWS * TILE + HEAD), 'white')
    draw = ImageDraw.Draw(sheet)
    draw.text((6, 5), f'{album.name}  лист {part + 1}/{parts}  ({len(photos)} фото)', fill='black')
    for i, p in enumerate(chunk):
        src = MEDIA / (p.thumb.name if p.thumb else p.image.name)
        x0, y0 = (i % COLS) * TILE, HEAD + (i // COLS) * TILE
        try:
            with Image.open(src) as im:
                im.draft('RGB', (TILE * 2, TILE * 2))
                im = im.convert('RGB')
                im.thumbnail((TILE - 4, TILE - 4))
                sheet.paste(im, (x0 + (TILE - im.width) // 2, y0 + (TILE - im.height) // 2))
        except Exception as e:
            print('нет файла', p.pk, e)
        n = part * per + i + 1
        draw.rectangle((x0 + 2, y0 + 2, x0 + 62, y0 + 16), fill='black')
        draw.text((x0 + 5, y0 + 3), f'{n} #{p.pk}', fill='white')
    sheet.save(OUT / f'{album.pk:02d}-{part + 1}.jpg', quality=85)
print(album.pk, album.name, len(photos), 'фото, листов:', parts, '→', OUT)
