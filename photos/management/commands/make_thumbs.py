from django.core.management.base import BaseCommand

from photos.models import Photo


class Command(BaseCommand):
    help = 'Создаёт превью (thumb) для всех фото, у которых его ещё нет.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Пересоздать превью даже у тех, где оно уже есть')

    def handle(self, *args, **opts):
        force = opts.get('force')
        qs = Photo.objects.all().order_by('pk')
        total = qs.count()
        made = skipped = failed = 0
        self.stdout.write(f'Всего фото: {total}')
        for p in qs.iterator():
            if not force and p.thumb and p.thumb.name:
                skipped += 1
                continue
            try:
                p.make_thumb()
                if p.thumb and p.thumb.name:
                    made += 1
                    self.stdout.write(f'  + {p.pk}: {p.thumb.name}')
                else:
                    failed += 1
                    self.stderr.write(f'  ! {p.pk}: превью не создано')
            except Exception as e:
                failed += 1
                self.stderr.write(f'  ! {p.pk}: {e}')
        self.stdout.write(
            self.style.SUCCESS(f'Готово. Создано: {made}, пропущено (уже было): {skipped}, ошибок: {failed}')
        )
