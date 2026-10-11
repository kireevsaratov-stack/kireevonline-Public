from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from photos.models import Photo


class Command(BaseCommand):
    help = (
        'Находит фото без альбома (открепившиеся после удаления альбома). '
        'По умолчанию только показывает; с --trash отправляет их в корзину.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--section', help='адрес (slug) раздела — искать только в нём')
        parser.add_argument('--trash', action='store_true', help='отправить найденные фото в корзину')

    def handle(self, *args, **opts):
        qs = Photo.objects.filter(is_deleted=False, album__isnull=True).select_related('section')
        if opts.get('section'):
            qs = qs.filter(section__slug=opts['section'])

        counts = Counter()
        ids = []
        for p in qs:
            has_albums = p.section.albums.exists()
            counts[(p.section.name, has_albums)] += 1
            ids.append(p.pk)

        if not ids:
            self.stdout.write('Фото без альбома не найдено.')
            return

        self.stdout.write('Фото без альбома (альбом не задан):')
        for (section_name, has_albums), n in counts.items():
            note = (
                '' if has_albums else '  ← в этом разделе нет альбомов: возможно, это обычные фото раздела, не трогай!'
            )
            self.stdout.write(f'  {section_name}: {n}{note}')

        if opts.get('trash'):
            Photo.objects.filter(pk__in=ids).update(is_deleted=True, deleted_at=timezone.now())
            self.stdout.write(
                self.style.SUCCESS(
                    f'Отправлено в корзину: {len(ids)}. Проверь /admin/trash/ и при необходимости верни.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Это только просмотр. Чтобы отправить в корзину, добавь --trash '
                    '(лучше с --section <slug>, чтобы не задеть лишнее).'
                )
            )
