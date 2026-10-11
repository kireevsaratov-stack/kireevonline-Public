"""Подготовка загруженного фото: проверка, сжатие, превью — ДО записи в базу.

Любая проблема — ValueError с понятной причиной, загрузка отклоняется; молча сохранить
битый или чужой файл нельзя (внешний аудит 09.10.2026, A01/A06).
"""

import io
import os

from PIL import (  # noqa: F401 — форматы ниже
    Image,
    ImageOps,
    JpegImagePlugin,
    MpoImagePlugin,
    PngImagePlugin,
    WebPImagePlugin,
)

# Pillow разбирает только эти форматы — до разбора, а не после (иначе файл другого формата
# под видом фото мог «повесить» обработку; CVE в разборщике EPS). JPEG некоторых камер (MPO)
# открывается через JPEG — для этого и подключён MpoImagePlugin.
FORMATS = ['JPEG', 'PNG', 'WEBP']
MAX_PIXELS = 120_000_000  # ~120 Мп: больше любой камеры владельца; защита от «бомбы» из пикселей
MAX_SIDE = 30_000  # и каждая сторона — от 1 до 30 000 px: нулевая или огромная сторона пройдёт проверку площади
MAX_EDGE, QUALITY = 1920, 85
THUMB_EDGE, THUMB_QUALITY = 1080, 82


def _to_jpeg(img, edge, quality):
    img = img.copy()
    img.thumbnail((edge, edge), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)  # без exif= — данные камеры не сохраняются
    return buf.getvalue()


def prepare(fp):
    """Возвращает (JPEG фото, JPEG превью) или поднимает ValueError."""
    try:
        with Image.open(fp, formats=FORMATS) as img:
            if not (0 < img.width <= MAX_SIDE and 0 < img.height <= MAX_SIDE) or img.width * img.height > MAX_PIXELS:
                raise ValueError('слишком большое изображение')
            img.load()  # полный разбор: обрезанный или повреждённый файл не пройдёт
            img = ImageOps.exif_transpose(img)  # повернуть по метке камеры, раз саму метку не сохраняем
            if img.mode != 'RGB':
                img = img.convert('RGB')
            return _to_jpeg(img, MAX_EDGE, QUALITY), _to_jpeg(img, THUMB_EDGE, THUMB_QUALITY)
    except ValueError:
        raise
    except Image.DecompressionBombError:
        raise ValueError('слишком большое изображение') from None
    except Exception:
        raise ValueError('это не фотография или файл повреждён') from None


def jpeg_name(name):
    """Безопасное имя: только имя файла, расширение .jpg (сайт хранит фото в JPEG)."""
    return (os.path.splitext(os.path.basename(name or ''))[0] or 'photo') + '.jpg'
