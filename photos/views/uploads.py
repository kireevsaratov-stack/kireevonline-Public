"""Загрузка фото частями (только для администратора)."""

import json
import logging
import os
import re
import time

from django.conf import settings
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import Album, Photo, Section
from .access import staff_member_required
from .params import to_id

logger = logging.getLogger(__name__)


@staff_member_required
def upload_page(request):
    sections = Section.objects.prefetch_related('albums').all()
    backup_pending = 0
    backup_never = False
    try:
        import datetime

        mark = os.path.join(settings.BASE_DIR, 'last_backup.txt')
        if os.path.exists(mark):
            epoch = int(open(mark).read().strip())
            last = datetime.datetime.fromtimestamp(epoch, datetime.UTC)
            backup_pending = Photo.objects.filter(is_deleted=False, created_at__gt=last).count()
        else:
            backup_never = True
    except Exception:
        pass
    return render(
        request,
        'photos/panel/upload.html',
        {
            'sections': sections,
            'albums_by_section': {
                str(sec.pk): [{'id': str(a.pk), 'name': a.name} for a in sec.albums.all()] for sec in sections
            },
            'backup_pending': backup_pending,
            'backup_never': backup_never,
        },
    )


CHUNK_DIR_NAME = 'chunk_tmp'
MAX_CHUNKS = 2000  # по 400 КБ — до ~800 МБ на файл, с запасом
MAX_CHUNK_SIZE = 8 * 1024 * 1024
MAX_FILE_SIZE = 300 * 1024 * 1024
KEEP_SECONDS = 24 * 3600  # незавершённые куски и отметки о готовых загрузках живут сутки


def _err(text, status=400, fatal=False):
    return JsonResponse({'ok': False, 'error': text, 'fatal': fatal}, status=status)


def _clean_old(tmp_dir):
    now = time.time()
    for fn in os.listdir(tmp_dir):
        path = os.path.join(tmp_dir, fn)
        try:
            if now - os.path.getmtime(path) > KEEP_SECONDS:
                os.remove(path)
        except OSError:
            pass


@staff_member_required
@require_POST
def upload_chunk(request):
    """Приём одного файла по частям (внешний аудит 09.10.2026, A06/A07).

    - Параметры загрузки (раздел, альбом, имя, число частей, размер части) запоминаются при первой части;
      последующие части с другими параметрами отклоняются.
    - Часть пишется по своему смещению; повтор части безопасен. Полученные части отмечаются.
    - Фото собирается, только когда пришли ВСЕ части и размер файла сходится.
    - Сборка — один раз: фото хранит номер своей загрузки (upload_key, уникален в базе). Повтор любой части
      после успешной сборки — даже после обрыва связи или перезапуска — возвращает то же фото, второго не будет.
      Собирает тот, кто взял «замок» `.lock`; замок старше LOCK_STALE секунд считается брошенным.
    - Фото проверяется и сжимается до записи в базу (Photo.from_upload); не фото — отказ, без повторов.
    """
    upload_id = re.sub(r'[^a-zA-Z0-9]', '', request.POST.get('upload_id', ''))[:64]
    index, total, chunk_size = (to_id(request.POST.get(k)) for k in ('index', 'total', 'chunk_size'))
    chunk = request.FILES.get('chunk')
    if not upload_id or chunk is None:
        return _err('нет данных части')
    if index is None or total is None or chunk_size is None or not (1 <= total <= MAX_CHUNKS):
        return _err('неверный номер части')
    if not (0 <= index < total) or not (1 <= chunk_size <= MAX_CHUNK_SIZE) or total * chunk_size > MAX_FILE_SIZE:
        return _err('неверный номер или размер части')
    data = chunk.read()
    if len(data) > chunk_size or (index < total - 1 and len(data) != chunk_size) or not data:
        return _err('часть неполная — повторите')

    album_id, section_id = to_id(request.POST.get('album')), to_id(request.POST.get('section'))
    params = {
        'total': total,
        'chunk_size': chunk_size,
        'name': (request.POST.get('name') or 'photo.jpg')[:200],
        'album': album_id,
        'section': section_id,
    }

    done = Photo.objects.filter(upload_key=upload_id).values_list('pk', flat=True).first()
    if done is not None:  # уже собрано — повтор после обрыва связи: то же фото
        return JsonResponse({'ok': True, 'done': True, 'duplicate': True, 'id': done})

    tmp_dir = os.path.join(settings.BASE_DIR, CHUNK_DIR_NAME)
    os.makedirs(tmp_dir, exist_ok=True)
    base = os.path.join(tmp_dir, upload_id)
    part_path, meta_path = base + '.part', base + '.json'

    if index == 0:
        _clean_old(tmp_dir)
    try:
        saved = _fix_params(meta_path, params)
    except ValueError:  # сюда не попадаем при обычной работе: запись атомарная
        _cleanup(base)
        return _err('служебные данные загрузки повреждены — загрузите файл заново', fatal=True)
    if saved != params:
        return _err('параметры загрузки изменились посреди файла — начните заново', fatal=True)

    fd = os.open(part_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        os.pwrite(fd, data, index * chunk_size)
    finally:
        os.close(fd)
    if index == total - 1:
        _write_atomic(base + '.last', str(len(data)))
    with open(base + '.idx', 'a') as f:
        f.write('%d\n' % index)

    with open(base + '.idx') as f:
        received = {int(line) for line in f if line.strip().isdigit()}
    if len(received) < total:
        return JsonResponse({'ok': True, 'received': index, 'missing': total - len(received)})

    with open(base + '.last') as f:  # размер последней части записан, когда она пришла
        expected = (total - 1) * chunk_size + int(f.read())
    if os.path.getsize(part_path) != expected:
        return _err('файл собрался не полностью — загрузите его заново', fatal=True)

    if not _take_lock(base + '.lock'):
        return _err('файл уже собирается — повторите через секунду', status=409)
    try:
        album = Album.objects.filter(pk=album_id).first() if album_id is not None else None
        section = album.section if album else Section.objects.filter(pk=section_id).first()
        if (album_id is not None and album is None) or section is None:
            raise ValueError('раздел или альбом не найден')
        if album and section_id is not None and section_id != album.section_id:
            raise ValueError('альбом не из выбранного раздела')
        with open(part_path, 'rb') as fp:
            photo = Photo.from_upload(fp, params['name'], section, album, upload_key=upload_id)
    except ValueError as e:
        _cleanup(base)
        return _err('Файл «%s» не загружен: %s' % (params['name'], e), fatal=True)
    except IntegrityError:  # тот же файл успели собрать параллельно — отдаём его
        _cleanup(base)
        done = Photo.objects.filter(upload_key=upload_id).values_list('pk', flat=True).first()
        return JsonResponse({'ok': True, 'done': True, 'duplicate': True, 'id': done})
    except Exception:
        _cleanup(base)
        logger.exception('загрузка %s не собралась', params['name'])
        return _err('ошибка на сервере при сборке файла — попробуйте ещё раз', status=500)
    _cleanup(base)
    return JsonResponse({'ok': True, 'done': True, 'id': photo.pk})


LOCK_STALE = 300


def _write_atomic(path, text):
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, path)


def _fix_params(meta_path, params):
    """Параметры загрузки фиксирует первая пришедшая часть (запись атомарная: целиком или никак)."""
    tmp = '%s.%d.tmp' % (meta_path, os.getpid())
    with open(tmp, 'w') as f:
        json.dump(params, f)
    try:
        os.link(tmp, meta_path)  # создать, только если ещё нет
    except FileExistsError:
        pass
    finally:
        os.remove(tmp)
    with open(meta_path) as f:
        return json.load(f)


def _take_lock(lock_path):
    for _ in range(2):
        try:
            os.close(os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) < LOCK_STALE:
                    return False
                os.remove(lock_path)  # брошенный замок (сборку прервали) — снять и взять заново
            except OSError:
                pass
    return False


def _cleanup(base):
    for ext in ('.part', '.json', '.idx', '.last', '.lock'):
        try:
            os.remove(base + ext)
        except OSError:
            pass
