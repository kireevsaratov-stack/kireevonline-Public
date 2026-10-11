"""Демо-данные для пустой копии сайта: разделы, альбомы и нарисованные картинки вместо фото.

Нужны тому, кто склонировал код: без базы и фото галерея пустая. Запускается только на пустой базе
и только при DJANGO_DEBUG=True — на настоящем сайте ничего не сделает.
"""

import io
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from photos.models import Album, Photo, Section

SECTIONS = [
    ('Репортаж', 'reportazh', [('Фестиваль', 'Москва', 'июнь 2026'), ('Мотофест', 'Москва', 'май 2026')]),
    ('Путешествия', 'puteshestviya', [('Горы', 'Алтай', 'август 2026'), ('Море', 'Бали', 'март 2026')]),
    ('Прогулки', 'progulki', [('Город', 'Москва', 'осень 2026')]),
]


def picture(seed):
    """Картинка-заглушка: градиент и пара кругов, у каждой свои цвета и пропорции."""
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    w, h = rnd.choice([(1600, 1067), (1067, 1600), (1600, 1200), (1600, 900)])
    a, b = [tuple(rnd.randrange(30, 220) for _ in range(3)) for _ in range(2)]
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    for _ in range(2):
        r = rnd.randrange(h // 8, h // 3)
        x, y = rnd.randrange(w), rnd.randrange(h)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=tuple(rnd.randrange(0, 256) for _ in range(3)))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
    buf.seek(0)
    return buf


class Command(BaseCommand):
    help = 'Заполняет пустую копию сайта демо-разделами, альбомами и картинками-заглушками.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--photos', type=int, default=12, help='Сколько картинок в каждом альбоме (по умолчанию 12)'
        )

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError('Только для копии сайта: запустите с DJANGO_DEBUG=True.')
        if Section.objects.exists() or Photo.objects.exists():
            raise CommandError('В базе уже есть разделы или фото — демо-данные кладутся только в пустую базу.')
        seed = 0
        for order, (name, slug, albums) in enumerate(SECTIONS):
            section = Section.objects.create(name=name, slug=slug, order=order)
            for a_order, (a_name, place, period) in enumerate(albums):
                album = Album.objects.create(
                    section=section,
                    name=a_name,
                    order=a_order,
                    place=place,
                    period=period,
                    intro='Демо-альбом: картинки нарисованы командой demo_data.',
                )
                for _ in range(opts['photos']):
                    seed += 1
                    Photo.from_upload(picture(seed), 'demo_%03d.jpg' % seed, section, album)
                self.stdout.write('  %s / %s — %d фото' % (name, a_name, opts['photos']))
        self.stdout.write(self.style.SUCCESS('Готово: %d фото.' % Photo.objects.count()))
