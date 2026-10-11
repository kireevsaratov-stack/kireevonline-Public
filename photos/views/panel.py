"""Панель управления сайтом (/admin/) — свои страницы вместо админки Django для ежедневной работы (Роман, 03.10.2026):
порядок и скрытие разделов и альбомов, создание, переименование и удаление пустых, тексты альбома,
перенос фото между альбомами. Всё только для администратора; изменения — POST с защитой CSRF.
Админка Django остаётся запасным входом («Админ» → «Панель Django»).
"""

import re

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import action_log
from ..models import Album, Photo, Section
from .access import staff_member_required
from .params import to_id, to_ids

NAME_MAX = 200
# русские буквы → латиница для адреса нового раздела («-» — буква пропадает: ъ, ь)
_RU = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
_LAT = 'a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch - y - e yu ya'.split()
TRANSLIT = {ru: '' if lat == '-' else lat for ru, lat in zip(_RU, _LAT, strict=True)}
MODELS = {'section': Section, 'album': Album}


def _err(text, status=400):
    return JsonResponse({'ok': False, 'error': text}, status=status)


def _get(model, raw_id):
    pk = to_id(raw_id)
    return model.objects.filter(pk=pk).first() if pk is not None else None


def _clean_name(raw):
    name = ' '.join((raw or '').split())
    if not name:
        return None, 'Название не может быть пустым.'
    if len(name) > NAME_MAX:
        return None, f'Название длиннее {NAME_MAX} знаков.'
    return name, None


def _slug_for(name):
    """Адрес нового раздела латиницей: «Путешествия» → puteshestviya (как у существующих)."""
    base = ''.join(TRANSLIT.get(ch, ch) for ch in name.lower())
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-') or 'razdel'
    slug, n = base, 2
    while Section.objects.filter(slug=slug).exists():
        slug, n = f'{base}-{n}', n + 1
    return slug


@staff_member_required
def albums(request):
    """Все разделы и альбомы одним списком."""
    albums = (
        Album.objects.select_related('cover')
        .annotate(n_photos=Count('photos', filter=Q(photos__is_deleted=False)), n_all=Count('photos'))
        .order_by('order', 'name')
    )
    by_cat = {}
    for album in albums:
        by_cat.setdefault(album.section_id, []).append(album)
    loose = dict(
        Photo.objects.filter(album__isnull=True, is_deleted=False)
        .values_list('section')
        .annotate(n=Count('id'))
        .values_list('section', 'n')
    )
    with_photos = set(Photo.objects.values_list('section', flat=True).distinct())
    sections = list(Section.objects.all())
    for cat in sections:
        cat.album_list = by_cat.get(cat.pk, [])
        cat.n_loose = loose.get(cat.pk, 0)
        cat.can_delete = not cat.album_list and cat.pk not in with_photos
    return render(request, 'photos/panel/albums.html', {'sections': sections})


@staff_member_required
@require_POST
def reorder(request):
    """Новый порядок разделов (kind=section) или альбомов одного раздела (kind=album, section=…)."""
    kind = request.POST.get('kind')
    ids = to_ids(request.POST.getlist('ids'))
    if kind not in MODELS or not ids or len(set(ids)) != len(ids):
        return _err('Неверный порядок.')
    if kind == 'section':
        current = set(Section.objects.values_list('pk', flat=True))
    else:
        cat = _get(Section, request.POST.get('section'))
        if not cat:
            return _err('Раздел не найден.', 404)
        current = set(cat.albums.values_list('pk', flat=True))
    if current != set(ids):  # должен прийти весь список целиком — иначе порядок собьётся
        return _err('Список устарел — обновите страницу.', 409)
    model = MODELS[kind]
    with transaction.atomic():
        for position, pk in enumerate(ids):
            model.objects.filter(pk=pk).update(order=position)
    action_log.log(request, f'Новый порядок: {"разделы" if kind == "section" else "альбомы"}')
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def toggle_hidden(request):
    """Скрыть от посетителей / показать."""
    model = MODELS.get(request.POST.get('kind'))
    obj = model and _get(model, request.POST.get('id'))
    if not obj:
        return _err('Не найдено.', 404)
    obj.hidden = request.POST.get('hidden') == '1'
    obj.save(update_fields=['hidden'])
    action_log.log(request, 'Скрыт от посетителей' if obj.hidden else 'Показан посетителям', obj)
    return JsonResponse({'ok': True, 'hidden': obj.hidden})


@staff_member_required
@require_POST
def rename(request):
    model = MODELS.get(request.POST.get('kind'))
    obj = model and _get(model, request.POST.get('id'))
    if not obj:
        return _err('Не найдено.', 404)
    name, error = _clean_name(request.POST.get('name'))
    if error:
        return _err(error)
    old = obj.name
    obj.name = name
    obj.save(update_fields=['name'])
    action_log.log(
        request, f'Переименован: «{old}» → «{name}»', obj
    )  # адрес раздела (slug) не меняется — старые ссылки работают
    return JsonResponse({'ok': True, 'name': obj.name})


@staff_member_required
@require_POST
def create(request):
    """Новый раздел или альбом — в конец списка и сразу скрытый, чтобы посетители не увидели пустой."""
    kind = request.POST.get('kind')
    name, error = _clean_name(request.POST.get('name'))
    if error:
        return _err(error)
    if kind == 'section':
        top = Section.objects.aggregate(m=Max('order'))['m']
        obj = Section.objects.create(name=name, slug=_slug_for(name), hidden=True, order=0 if top is None else top + 1)
    elif kind == 'album':
        cat = _get(Section, request.POST.get('section'))
        if not cat:
            return _err('Раздел не найден.', 404)
        top = cat.albums.aggregate(m=Max('order'))['m']
        obj = Album.objects.create(section=cat, name=name, hidden=True, order=0 if top is None else top + 1)
    else:
        return _err('Неизвестный тип.')
    action_log.log(request, 'Создан (скрытым)', obj, action_log.ADDITION)
    return JsonResponse({'ok': True, 'id': obj.pk})


@staff_member_required
@require_POST
def delete(request):
    """Удалить можно только пустой альбом или раздел — фото так не потеряются."""
    kind = request.POST.get('kind')
    model = MODELS.get(kind)
    obj = model and _get(model, request.POST.get('id'))
    if not obj:
        return _err('Не найдено.', 404)
    if kind == 'album' and obj.photos.exists():
        return _err('В альбоме есть фото (может быть, в корзине) — сначала перенесите их.')
    if kind == 'section' and (obj.albums.exists() or obj.photos.exists()):
        return _err('В разделе есть альбомы или фото.')
    action_log.log(request, 'Удалён (пустой)', obj, action_log.DELETION)
    obj.delete()
    return JsonResponse({'ok': True})


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ['name', 'section', 'place', 'period', 'intro', 'description', 'gear', 'hidden']
        labels = {'section': 'Раздел', 'hidden': 'Скрыть от посетителей'}
        widgets = {
            'intro': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 14}),
        }

    def clean(self):
        data = super().clean()
        for field in ('name', 'place', 'period', 'intro', 'gear'):
            if isinstance(data.get(field), str):
                data[field] = ' '.join(data[field].split())
        if isinstance(data.get('description'), str):
            data['description'] = data['description'].replace('\r\n', '\n').strip()
        if not data.get('name'):
            self.add_error('name', 'Название не может быть пустым.')
        return data


@staff_member_required
def album_texts(request, pk):
    """Тексты альбома на одной странице, справа — как это будет выглядеть."""
    album = get_object_or_404(Album, pk=pk)
    old_section = album.section_id
    form = AlbumForm(request.POST or None, instance=album)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            album = form.save()
            if album.section_id != old_section:  # альбом переехал в другой раздел — его фото тоже
                moved = list(album.photos.values_list('pk', flat=True))
                album.photos.update(section=album.section)
                Section.objects.filter(pk=old_section, cover_id__in=moved).update(cover=None)
        action_log.log(
            request,
            'Тексты: ' + (', '.join(str(form.fields[f].label) for f in form.changed_data) or 'без изменений'),
            album,
        )
        messages.success(request, 'Сохранено.')
        return redirect('panel:album_texts', pk=album.pk)
    n_photos = album.photos.filter(is_deleted=False).count()
    return render(request, 'photos/panel/album_texts.html', {'form': form, 'album': album, 'n_photos': n_photos})


@staff_member_required
@require_POST
def move_photos(request):
    """Перенести выбранные фото в другой альбом (и в его раздел). Обложки, которые уехали, сбрасываются."""
    target = _get(Album, request.POST.get('album'))
    if not target:
        return _err('Альбом не найден.', 404)
    ids = to_ids(request.POST.getlist('ids')) or []
    if not ids:
        return _err('Не выбраны фото.')
    with transaction.atomic():
        photos = Photo.objects.filter(pk__in=ids)
        moved = list(photos.values_list('pk', flat=True))
        Album.objects.filter(cover_id__in=moved).exclude(pk=target.pk).update(cover=None)
        Section.objects.filter(cover_id__in=moved).exclude(pk=target.section_id).update(cover=None)
        count = photos.update(album=target, section=target.section)
    action_log.log(request, f'Перенесено фото: {count}', target)
    return JsonResponse({'ok': True, 'moved': count, 'album': target.name, 'url': reverse('album', args=[target.pk])})


@staff_member_required
@require_POST
def set_cover(request):
    photo_id = to_id(request.POST.get('photo'))
    try:
        photo = Photo.objects.get(pk=photo_id)
    except Photo.DoesNotExist:
        return JsonResponse({'ok': False}, status=404)
    if photo.album_id:
        sub = photo.album
        sub.cover = photo
        sub.save(update_fields=['cover'])
        action_log.log(request, f'Обложка: фото №{photo.pk}', sub)
        return JsonResponse({'ok': True, 'target': 'album'})
    cat = photo.section
    cat.cover = photo
    cat.save(update_fields=['cover'])
    action_log.log(request, f'Обложка: фото №{photo.pk}', cat)
    return JsonResponse({'ok': True, 'target': 'section'})
