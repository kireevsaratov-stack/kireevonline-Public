"""Публичные страницы: главная, «Обо мне», раздел, альбом, «Барабан»."""

import random
import re

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ..models import Album, Photo, Section


def _natural_key(photo):
    """Сортировка по названию с учётом чисел: IMG_2 раньше IMG_10. Числа — только цифры 0–9:
    «²» или «①» в названии — это текст, а не число (иначе страница альбома падала, аудит A10).
    Число и текст в одной позиции не сравниваются: каждая часть — (0, число) или (1, текст)."""
    parts = re.split(r'([0-9]+)', (photo.title or '').lower())
    return [(0, int(p), '') if p.isascii() and p.isdigit() else (1, 0, p) for p in parts]


def home(request):
    # админ видит главную как гость — скрытое только в «Админ → Альбомы» (Роман, 03.10.2026)
    sections = Section.objects.prefetch_related('albums', 'photos').filter(hidden=False)
    nav_items = []
    for cat in sections:
        nav_items.append({'name': cat.name, 'url': reverse('section', args=[cat.slug]), 'sub': False})
        for sub in cat.albums.all():
            if sub.hidden:
                continue
            nav_items.append({'name': sub.name, 'url': reverse('album', args=[sub.pk]), 'sub': True})
    # Превью ссылки на главную — обложка первого видимого альбома
    og_cover = next(
        (
            cover
            for cat in sections
            for sub in cat.albums.all()
            if not sub.hidden
            for cover in [sub.get_cover()]
            if cover
        ),
        None,
    )
    return render(
        request,
        'photos/home.html',
        {
            'sections': sections,
            'nav_items': nav_items,
            'og_cover': og_cover,
        },
    )


def about(request):
    return render(request, 'photos/about.html')


def section_detail(request, slug):
    section = get_object_or_404(Section, slug=slug)
    if section.hidden and not request.user.is_staff:  # админ открывает скрытый раздел из «Админ → Альбомы»
        raise Http404('Скрытый раздел')
    albums = section.albums.prefetch_related('photos').filter(hidden=False)
    # If no albums — show photos directly
    if section.albums.exists():
        photos = list(section.photos.filter(album__isnull=True, is_deleted=False))
    else:
        photos = list(section.photos.filter(is_deleted=False))
    photos.sort(key=_natural_key)
    siblings = []
    if not section.albums.exists():
        others = Section.objects.exclude(pk=section.pk).filter(hidden=False)
        for c in others:
            siblings.append({'name': c.name, 'url': reverse('section', args=[c.slug]), 'cover': c.get_cover()})
    return render(
        request,
        'photos/section.html',
        {
            'section': section,
            'albums': albums,
            'photos': photos,
            'cover_id': section.cover_id,
            'siblings': siblings,
        },
    )


def album_detail(request, album_id):
    album = get_object_or_404(Album, pk=album_id)
    if (album.hidden or album.section.hidden) and not request.user.is_staff:
        raise Http404('Скрытый альбом')  # админ открывает скрытый альбом из «Админ → Альбомы»
    photos = list(album.photos.filter(is_deleted=False))
    photos.sort(key=_natural_key)
    siblings = []
    sib_qs = album.section.albums.exclude(pk=album.pk).filter(hidden=False)
    if album.section.hidden:
        sib_qs = sib_qs.none()  # соседи в скрытом разделе посетителям не видны — и в «Другие альбомы» не идут
    for s in sib_qs:
        siblings.append(
            {
                'name': s.name,
                'url': reverse('album', args=[s.pk]),
                'cover': s.get_cover(),
                'hidden': s.hidden or album.section.hidden,
            }
        )
    # затем все остальные альбомы из других разделов
    rest_qs = (
        Album.objects.exclude(section=album.section)
        .select_related('section')
        .filter(hidden=False, section__hidden=False)
    )
    rest_qs = rest_qs.order_by('section__order', 'order', 'name')
    for s in rest_qs:
        siblings.append(
            {
                'name': s.name,
                'url': reverse('album', args=[s.pk]),
                'cover': s.get_cover(),
                'hidden': s.hidden or s.section.hidden,
            }
        )
    return render(
        request,
        'photos/album.html',
        {
            'album': album,
            'photos': photos,
            'cover_id': album.cover_id,
            'siblings': siblings,
            'is_hidden_album': album.hidden,
        },
    )


def shuffle(request):
    """«Барабан»: все фото, видимые гостю, вперемешку — при каждом заходе новый порядок.
    Выглядит как обычный альбом; в просмотре фото есть кнопка «Перейти к альбому»."""
    photos = list(Photo.objects.visible().select_related('album', 'section'))
    random.shuffle(photos)
    for p in photos:
        p.album_url = reverse('album', args=[p.album_id]) if p.album_id else reverse('section', args=[p.section.slug])
    return render(request, 'photos/shuffle.html', {'photos': photos})
