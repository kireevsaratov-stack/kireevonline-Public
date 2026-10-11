"""«Диск»: сколько места занимают фото, поиск и уборка лишних файлов (только для администратора)."""

import os

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import Album, Photo, Section
from .access import staff_member_required


def _human(n):
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if n < 1024 or unit == 'ГБ':
            return f'{n:.0f} {unit}' if unit == 'Б' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} ГБ'


@staff_member_required
def disk(request):
    media_root = settings.MEDIA_ROOT
    # Все файлы на диске в media/
    disk_files = {}
    total_disk = 0
    for root, _dirs, files in os.walk(media_root):
        for name in files:
            fp = os.path.join(root, name)
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            rel = os.path.relpath(fp, media_root)
            disk_files[rel] = size
            total_disk += size

    # Файлы, на которые ссылается база
    db_files = set()
    db_size = 0
    photos = Photo.objects.all()
    for p in photos:
        if p.image:
            db_files.add(p.image.name)
            try:
                db_size += os.path.getsize(p.image.path)
            except (OSError, ValueError):
                pass
        if p.thumb:
            db_files.add(p.thumb.name)
            try:
                db_size += os.path.getsize(p.thumb.path)
            except (OSError, ValueError):
                pass

    orphans = [(rel, sz) for rel, sz in disk_files.items() if rel not in db_files]
    orphans.sort(key=lambda x: -x[1])
    orphan_size = sum(sz for _, sz in orphans)

    # Корзина: сколько фото и сколько весят их файлы (фото + превью)
    trash_count = 0
    trash_size = 0
    for p in photos.filter(is_deleted=True):
        trash_count += 1
        for f in (p.image, p.thumb):
            try:
                if f and f.name:
                    trash_size += os.path.getsize(f.path)
            except (OSError, ValueError):
                pass

    # Свободное место аккаунта (тариф ~2 ГБ). Считаем сумму файлов в домашней папке.
    QUOTA = 2 * 1024**3
    home = os.path.expanduser('~')
    account_used = 0
    for root, _dirs, files in os.walk(home):
        for name in files:
            try:
                account_used += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    account_free = max(QUOTA - account_used, 0)
    account_pct = round(account_used / QUOTA * 100) if QUOTA else 0

    ctx = {
        'photo_count': photos.filter(is_deleted=False).count(),
        'trash_count': trash_count,
        'trash_size_h': _human(trash_size),
        'section_count': Section.objects.count(),
        'album_count': Album.objects.count(),
        'total_disk_h': _human(total_disk),
        'db_size_h': _human(db_size),
        'orphan_count': len(orphans),
        'orphan_size_h': _human(orphan_size),
        'orphans': [{'name': r, 'size_h': _human(s)} for r, s in orphans[:50]],
        'account_used_h': _human(account_used),
        'account_free_h': _human(account_free),
        'quota_h': _human(QUOTA),
        'account_pct': account_pct,
    }
    return render(request, 'photos/panel/disk.html', ctx)


ORPHAN_MIN_AGE = 24 * 3600


@staff_member_required
@require_POST
def clean_orphans(request):
    """Удаляет файлы в media/, на которые не ссылается ни одно фото в базе.
    Только файлы старше суток: свежий файл может принадлежать загрузке, которая ещё не записала фото
    в базу (внешний аудит 09.10.2026, A05)."""
    import time

    media_root = settings.MEDIA_ROOT
    too_fresh = time.time() - ORPHAN_MIN_AGE
    db_files = set()
    for p in Photo.objects.all():
        if p.image:
            db_files.add(p.image.name)
        if p.thumb:
            db_files.add(p.thumb.name)
    removed = 0
    freed = 0
    for root, _dirs, files in os.walk(media_root):
        for name in files:
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, media_root)
            if rel not in db_files:
                try:
                    if os.path.getmtime(fp) > too_fresh:
                        continue
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    removed += 1
                    freed += sz
                except OSError:
                    pass
    return JsonResponse({'ok': True, 'removed': removed, 'freed': _human(freed)})
