"""Служебные файлы для поисковиков и браузеров: robots.txt, sitemap.xml, security.txt."""

from django.http import HttpResponse
from django.urls import reverse

from ..models import Album, Section


def robots_txt(request):
    """robots.txt — разрешаем обход сайта и указываем карту сайта."""
    host = request.get_host()
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /admindjango/',
        f'Sitemap: {request.scheme}://{host}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')


def security_txt(request):
    """/.well-known/security.txt — куда сообщить о найденной уязвимости (стандарт RFC 9116).
    Срок действия считается от сегодняшнего дня, чтобы файл не «протухал»."""
    from datetime import timedelta

    from django.utils import timezone

    expires = (timezone.now() + timedelta(days=180)).strftime('%Y-%m-%dT00:00:00Z')
    lines = [
        'Contact: https://t.me/RomanFromKharabali',
        f'Expires: {expires}',
        'Preferred-Languages: ru, en',
        f'Canonical: https://{request.get_host()}/.well-known/security.txt',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


def sitemap_xml(request):
    """Карта сайта: главная, разделы и видимые альбомы. Домен — из запроса
    (без sites framework, без миграций)."""
    from xml.sax.saxutils import escape

    base = f'{request.scheme}://{request.get_host()}'
    urls = []

    def add(path, priority):
        urls.append((escape(base + path), priority))

    add(reverse('home'), '1.0')
    add(reverse('about'), '0.5')
    for cat in Section.objects.filter(hidden=False):
        add(reverse('section', args=[cat.slug]), '0.8')
    for sub in Album.objects.filter(hidden=False, section__hidden=False):
        add(reverse('album', args=[sub.pk]), '0.7')

    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, pr in urls:
        parts.append(f'<url><loc>{loc}</loc><priority>{pr}</priority></url>')
    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')
