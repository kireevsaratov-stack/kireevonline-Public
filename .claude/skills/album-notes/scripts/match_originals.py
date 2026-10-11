"""Сверка фото сайта с оригиналами в ~/Фото по изображению (dHash) — сайт стирает данные камеры при загрузке.
Из найденного оригинала читаются ТОЛЬКО дата съёмки, камера и объектив (разрешение Романа 01.10.2026);
координаты и прочее не читаются. Только чтение: в ~/Фото ничего не меняется.

Запуск из gallery/:
    [ALBUM=<id>] ../.venv/bin/python manage.py shell < .claude/skills/album-notes/scripts/match_originals.py
Результат по каждому фото — JSON во временной папке системы (путь печатается), сводка — на экран.
"""

import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from photos.models import Photo

ROOT = Path.home() / 'Фото'
MEDIA = Path('../backups/media').resolve()
OUT = Path(os.environ.get('OUT') or Path(tempfile.gettempdir()) / 'kireevonline-originals.json')
ALBUM = os.environ.get('ALBUM')
EXIF_IFD, DATE_ORIG, LENS, MODEL, DATE_IFD0 = 0x8769, 0x9003, 0xA434, 0x0110, 0x0132
MAX_DIST = 10


def dhash(path):
    try:
        with Image.open(path) as im:
            im.draft('L', (64, 64))
            px = list(im.convert('L').resize((9, 8), Image.BILINEAR).getdata())
    except Exception:
        return None
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    return bits


def meta(path):
    """Только дата, камера, объектив."""
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            sub = ex.get_ifd(EXIF_IFD)
            d = str(sub.get(DATE_ORIG) or ex.get(DATE_IFD0) or '')[:10].replace(':', '-')
            return d, str(ex.get(MODEL) or '').strip(), str(sub.get(LENS) or '').strip()
    except Exception:
        return '', '', ''


originals = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if not d.startswith('.') and not d.endswith('.lrdata')]
    for fn in filenames:
        if fn.lower().endswith(('.jpg', '.jpeg')):
            p = Path(dirpath) / fn
            h = dhash(p)
            if h is not None:
                originals.append((h, p))
print('оригиналов JPEG с отпечатком:', len(originals))
by_stem = defaultdict(list)
for h, p in originals:
    by_stem[p.stem.lower()].append((h, p))

photos = Photo.objects.filter(is_deleted=False, album__isnull=False).select_related('album__section')
if ALBUM:
    photos = photos.filter(album_id=int(ALBUM))
albums = defaultdict(list)
for ph in photos:
    albums[(ph.album.section.name, ph.album.name, ph.album.pk)].append(ph)

result = {}
for (section, name, pk), items in sorted(albums.items()):
    rows = []
    for ph in items:
        h = dhash(MEDIA / ph.image.name)
        if h is None:
            rows.append(dict(photo=ph.pk, title=ph.title, match=None))
            continue
        pool = by_stem.get((ph.title or '').lower()) or []
        best = min(((bin(h ^ oh).count('1'), str(op)) for oh, op in pool), default=(99, None))
        if best[0] > MAX_DIST:  # по имени не нашлось — ищем по изображению среди всех
            best = min(((bin(h ^ oh).count('1'), str(op)) for oh, op in originals), default=(99, None))
        if best[0] <= MAX_DIST:
            d, model, lens = meta(best[1])
            rows.append(
                dict(photo=ph.pk, title=ph.title, match=best[1], dist=best[0], date=d, model=model, lens=lens,
                     folder=Path(best[1]).relative_to(ROOT).parts[0])
            )  # fmt: skip
        else:
            rows.append(dict(photo=ph.pk, title=ph.title, match=None, dist=best[0]))
    result[f'{section} / {name}'] = dict(id=pk, rows=rows)

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
for key, r in result.items():
    rows = r['rows']
    ok = [x for x in rows if x['match']]
    dates = Counter(x['date'] for x in ok if x['date'])
    gear = Counter(f'{x["model"]} | {x["lens"]}' for x in ok if x['model'])
    print(f'\n— {key} (id {r["id"]}): найдено {len(ok)}/{len(rows)}')
    print(f'   даты: {sorted(dates.items())[:8]}')
    print(f'   камера + объектив: {gear.most_common(6)}')
print('\nподробно:', OUT)
