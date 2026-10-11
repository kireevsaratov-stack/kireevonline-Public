"""Замена 4 фото, повреждённых при загрузке 04.06.2026 (до исправления «гонки при загрузке»):
низ кадра залит серым. Решение Романа 02.10.2026 — сделать это вместе с выкладкой описаний.

- №3614 DSC02339 — сломанный дубль №4203 из «Фотовыезда 2025» → в корзину;
- №3615 IMG_1277 — новый файл из оригинала и перенос в «Фотовыезд 2023» (кадр оттуда);
- №3616 6Q0A9921, №3619 6Q0A9974 («Прогулки 2024») — новые файлы из оригиналов.

Новые файлы лежат в photos/migrations/files_0009/ уже в виде, как их сохраняет сайт (до 1920 px,
JPEG 85); при миграции копируются в MEDIA_ROOT/photos/replaced-2026-10/, превью — как у сайта.
Старые файлы не удаляются: откат (обратная миграция) возвращает прежние пути и альбом.
Фото, которое уже не в исходном состоянии (например, поправили руками), пропускается.
"""
import io
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import migrations
from django.utils import timezone

SRC = Path(__file__).resolve().parent / 'files_0009'
NEW_DIR = 'replaced-2026-10'
REPLACE = {  # №: (файл, старое фото, старое превью, альбом был, альбом станет)
    3615: ('IMG_1277.jpg', 'photos/2026/06/IMG_1277.jpg', 'thumbs/2026/06/IMG_1277_t.jpg', 5, 19),
    3616: ('6Q0A9921.jpg', 'photos/2026/06/6Q0A9921.jpg', 'thumbs/2026/06/6Q0A9921_t.jpg', 12, 12),
    3619: ('6Q0A9974.jpg', 'photos/2026/06/6Q0A9974.jpg', 'thumbs/2026/06/6Q0A9974_t.jpg', 12, 12),
}
TRASH = {3614: 'photos/2026/06/DSC02339.jpg'}


def _thumb(data):
    """Превью как у Photo.make_thumb: до 1080 px, JPEG 82."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        img.draft('RGB', (1080, 1080))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((1080, 1080), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=82)
    return buf.getvalue()


def forward(apps, schema_editor):
    Photo = apps.get_model('photos', 'Photo')
    for pk, (name, old_image, _old_thumb, old_album, new_album) in REPLACE.items():
        if not Photo.objects.filter(pk=pk, image=old_image, subcategory_id=old_album).exists():
            continue
        data = (SRC / name).read_bytes()
        image = default_storage.save(f'photos/{NEW_DIR}/{name}', ContentFile(data))
        thumb = default_storage.save(f'thumbs/{NEW_DIR}/{Path(name).stem}_t.jpg', ContentFile(_thumb(data)))
        Photo.objects.filter(pk=pk).update(image=image, thumb=thumb, subcategory_id=new_album)
    for pk, image in TRASH.items():
        Photo.objects.filter(pk=pk, image=image, is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())


def backward(apps, schema_editor):
    Photo = apps.get_model('photos', 'Photo')
    for pk, (_name, old_image, old_thumb, old_album, _new_album) in REPLACE.items():
        photo = Photo.objects.filter(pk=pk, image__startswith=f'photos/{NEW_DIR}/').first()
        if not photo:
            continue
        for f in (photo.image.name, photo.thumb.name):
            if f and f.split('/')[1] == NEW_DIR and default_storage.exists(f):
                default_storage.delete(f)
        Photo.objects.filter(pk=pk).update(image=old_image, thumb=old_thumb, subcategory_id=old_album)
    for pk, image in TRASH.items():
        Photo.objects.filter(pk=pk, image=image, is_deleted=True).update(is_deleted=False, deleted_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0008_album_details'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
