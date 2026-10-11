import logging
import os

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.text import slugify
from PIL import Image

logger = logging.getLogger(__name__)


class Section(models.Model):
    name = models.CharField('Название', max_length=200)
    slug = models.SlugField('Slug', unique=True, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    hidden = models.BooleanField(
        'Скрыть раздел от посетителей',
        default=False,
        help_text='Скрывает раздел целиком: пункт меню, кнопку на главной, '
        'страницу раздела, все его альбомы и фото. Администратор видит всё.',
    )
    cover = models.ForeignKey(
        'Photo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cover_for_section',
        verbose_name='Обложка',
    )

    class Meta:
        verbose_name = 'Раздел'
        verbose_name_plural = 'Разделы'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def clean(self):
        if self.cover_id and (self.cover.section_id != self.pk or (self.cover.album and self.cover.album.hidden)):
            raise ValidationError({'cover': 'Обложка — фото этого раздела не из скрытого альбома.'})

    def get_cover(self):
        """Обложка для посетителей: выбранная, если она своя и видимая, иначе первое видимое фото раздела."""
        visible = Photo.objects.visible().filter(section=self)
        if self.cover_id and visible.filter(pk=self.cover_id).exists():
            return self.cover
        return visible.filter(album__isnull=True).first() or visible.first()


class Album(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='albums', verbose_name='Раздел')
    name = models.CharField('Название', max_length=200)
    order = models.PositiveIntegerField('Порядок', default=0)
    hidden = models.BooleanField('Скрыть от посетителей', default=False)
    place = models.CharField(
        'Место', max_length=120, blank=True, default='', help_text='Например «Бали, Индонезия» или «Москва, ВДНХ».'
    )
    period = models.CharField(
        'Когда', max_length=60, blank=True, default='', help_text='Например «декабрь 2024» или «лето 2023».'
    )
    intro = models.CharField(
        'Коротко',
        max_length=300,
        blank=True,
        default='',
        help_text='Одна строка под названием альбома: о чём он. Видно сразу.',
    )
    description = models.TextField(
        'Записки',
        blank=True,
        default='',
        help_text='Впечатления, пара абзацев (абзацы — через пустую строку). Раскрываются по «+».',
    )
    gear = models.CharField(
        'Техника',
        max_length=200,
        blank=True,
        default='',
        help_text='На что снято, например «Leica Q3». Видно всегда, отдельной строкой: «Снято на …».',
    )
    cover = models.ForeignKey(
        'Photo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cover_for_album',
        verbose_name='Обложка',
    )

    class Meta:
        verbose_name = 'Альбом'
        verbose_name_plural = 'Альбомы'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.section.name} / {self.name}'

    def save(self, *args, **kwargs):
        # альбом переехал в другой раздел — его фото переезжают вместе с ним (раздел фото = раздел альбома).
        # Только если раздел действительно сохраняется: при скрытии или переименовании (update_fields без
        # section) устаревшая копия альбома не должна «возвращать» фото в старый раздел (аудит 2).
        update_fields = kwargs.get('update_fields')
        moves = update_fields is None or 'section' in update_fields
        with transaction.atomic():
            moved = moves and self.pk and Album.objects.filter(pk=self.pk).exclude(section_id=self.section_id).exists()
            super().save(*args, **kwargs)
            if moved:
                self.photos.update(section_id=self.section_id)

    def clean(self):
        if self.cover_id and self.cover.album_id != self.pk:
            raise ValidationError({'cover': 'Обложка — фото из этого альбома.'})

    def get_cover(self):
        if self.cover and not self.cover.is_deleted and self.cover.album_id == self.pk:
            return self.cover
        return self.photos.filter(is_deleted=False).first()


class PhotoQuerySet(models.QuerySet):
    def visible(self):
        """Единое правило «что видит посетитель»: не в корзине, раздел не скрыт, альбом (если есть) не скрыт."""
        return (
            self.filter(is_deleted=False, section__hidden=False)
            .exclude(album__hidden=True)
            .exclude(album__section__hidden=True)  # и раздел самого альбома — на случай расхождения
        )


class Photo(models.Model):
    title = models.CharField('Название', max_length=300, blank=True)
    image = models.ImageField('Фото', upload_to='photos/%Y/%m/')
    thumb = models.ImageField('Превью', upload_to='thumbs/%Y/%m/', blank=True, null=True)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='photos', verbose_name='Раздел')
    album = models.ForeignKey(
        Album, on_delete=models.SET_NULL, null=True, blank=True, related_name='photos', verbose_name='Альбом'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    created_at = models.DateTimeField('Дата', auto_now_add=True)
    is_deleted = models.BooleanField('В корзине', default=False)
    deleted_at = models.DateTimeField('Удалено', null=True, blank=True)
    upload_key = models.CharField(
        'Номер загрузки',
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        editable=False,
        help_text='Из какой загрузки по частям пришло фото: повтор после обрыва находит его, а не создаёт второе.',
    )

    objects = PhotoQuerySet.as_manager()

    class Meta:
        verbose_name = 'Фото'
        verbose_name_plural = 'Фото'
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title or f'Photo #{self.pk}'

    def save(self, *args, **kwargs):
        if self.album_id:  # раздел фото всегда = раздел его альбома (иначе фото «просочится» мимо скрытия)
            self.section_id = Album.objects.values_list('section_id', flat=True).get(pk=self.album_id)
        super().save(*args, **kwargs)

    @classmethod
    def from_upload(cls, fp, name, section, album=None, upload_key=None):
        """Новое фото из загруженного файла: сначала проверка и сжатие (photos/media.py), потом запись.
        Не фото / битый файл — ValueError, в базе и на диске ничего не появляется. Сорвалась запись превью
        или фото в базу — файлы, созданные этой попыткой, стираются (аудит 2, 09.10.2026)."""
        from django.core.files.base import ContentFile

        from .media import jpeg_name, prepare

        image, thumb = prepare(fp)
        file_name = jpeg_name(name)
        photo = cls(
            title=os.path.splitext(os.path.basename(name or ''))[0], section=section, album=album, upload_key=upload_key
        )
        created = []
        try:
            photo.image.save(file_name, ContentFile(image), save=False)
            created.append(photo.image.name)
            photo.thumb.save(file_name[:-4] + '_t.jpg', ContentFile(thumb), save=False)
            created.append(photo.thumb.name)
            photo.save()
        except BaseException:
            for name_ in created:
                photo.image.storage.delete(name_)
            raise
        return photo

    def make_thumb(self):
        """Пересоздать превью из сохранённого фото (команда make_thumbs). Ошибка — исключение."""
        from django.core.files.base import ContentFile

        from .media import THUMB_EDGE, THUMB_QUALITY, _to_jpeg

        with self.image.open('rb') as f, Image.open(f) as img:
            img.load()
            thumb = _to_jpeg(img.convert('RGB'), THUMB_EDGE, THUMB_QUALITY)
        base = os.path.splitext(os.path.basename(self.image.name))[0]
        self.thumb.save(base + '_t.jpg', ContentFile(thumb), save=False)
        type(self).objects.filter(pk=self.pk).update(thumb=self.thumb.name)

    def get_thumb(self):
        try:
            if self.thumb and self.thumb.name:
                return self.thumb.url
        except Exception:
            pass
        return self.image.url


@receiver(pre_delete, sender=Album)
def _album_photos_to_trash(sender, instance, **kwargs):
    """При удалении альбома его фото уезжают в корзину (можно вернуть),
    файлы удалятся, когда очистишь корзину."""
    from django.utils import timezone

    try:
        instance.photos.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
    except Exception:
        pass


@receiver(post_delete, sender=Photo)
def _photo_delete_files(sender, instance, **kwargs):
    """Когда фото удаляется окончательно (очистка корзины, админка, удаление раздела) — стираем файл
    и превью, но только ПОСЛЕ успешной записи в базу: если удаление откатится, файлы останутся на месте."""
    files = [(f.storage, f.name) for f in (instance.image, instance.thumb) if f and f.name]

    def remove():
        for storage, name in files:
            try:
                storage.delete(name)
            except OSError:
                logger.warning('не удалось стереть файл %s', name)

    transaction.on_commit(remove)
