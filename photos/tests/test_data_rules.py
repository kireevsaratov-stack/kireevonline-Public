"""Правила данных (внешний аудит 09.10.2026, A02, A05, A09, A10): что видит посетитель, обложки,
раздел фото = раздел альбома, файлы стираются только после записи в базу, кривые номера и названия."""

import io
import json
import os
import re
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings

from ..models import Album, Photo, Section


def _image(name='kadr.jpg'):
    from PIL import Image

    buf = io.BytesIO()
    Image.new('RGB', (40, 30), 'gray').save(buf, 'JPEG')
    return ContentFile(buf.getvalue(), name=name)


class MediaTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.tmp.name, SECURE_SSL_REDIRECT=False)
        self.override.enable()
        self.public = Section.objects.create(name='Путешествия', slug='puteshestviya')
        self.hidden = Section.objects.create(name='Портреты', slug='portrety', hidden=True)
        self.bali = Album.objects.create(section=self.public, name='Бали')
        self.secret = Album.objects.create(section=self.public, name='Алтай', hidden=True)
        self.staff = get_user_model().objects.create_user('roman', is_staff=True, is_superuser=True)

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def photo(self, album=None, section=None, title='kadr', deleted=False):
        p = Photo(title=title, section=section or (album.section if album else self.public), album=album,
                  is_deleted=deleted)  # fmt: skip
        p.image.save(title + '.jpg', _image(), save=False)
        p.save()
        return p


class VisibilityTests(MediaTestCase):
    def test_photo_section_always_follows_its_album(self):
        p = self.photo(album=self.bali, section=self.hidden)  # пытаемся записать «чужой» раздел
        self.assertEqual(p.section_id, self.public.pk)

    def test_album_moved_to_other_section_takes_photos_along(self):
        p = self.photo(album=self.bali)
        self.bali.section = self.hidden
        self.bali.save()
        p.refresh_from_db()
        self.assertEqual(p.section_id, self.hidden.pk)

    def test_stale_album_copy_does_not_move_photos_back(self):
        """Аудит 2: альбом перенесли в другой раздел, а параллельно его скрыли из устаревшей копии."""
        p = self.photo(album=self.bali)
        stale = Album.objects.get(pk=self.bali.pk)  # копия до переноса
        self.bali.section = self.hidden
        self.bali.save()
        stale.hidden = True
        stale.save(update_fields=['hidden'])  # как делает кнопка «скрыть» в панели
        p.refresh_from_db()
        self.assertEqual(p.section_id, self.hidden.pk)
        self.assertEqual(Album.objects.get(pk=self.bali.pk).section_id, self.hidden.pk)

    def test_visibility_also_checks_album_section(self):
        p = self.photo(album=self.bali)
        Photo.objects.filter(pk=p.pk).update(section=self.public)  # расхождение, записанное в обход модели
        Album.objects.filter(pk=self.bali.pk).update(section=self.hidden)
        self.assertFalse(Photo.objects.visible().filter(pk=p.pk).exists())

    def test_shuffle_and_covers_show_only_visible(self):
        shown = self.photo(album=self.bali, title='vidno')
        secret = self.photo(album=self.secret, title='skryto')
        page = self.client.get('/shuffle/').content.decode()
        self.assertIn(shown.image.url, page)
        self.assertNotIn(secret.image.url, page)
        self.public.cover = None
        self.assertNotEqual(self.public.get_cover(), secret)  # обложка раздела — не из скрытого альбома
        self.public.cover = secret
        self.assertNotEqual(self.public.get_cover(), secret)

    def test_cover_must_belong_to_its_album_or_section(self):
        other = self.photo(album=self.secret)
        self.bali.cover = other
        with self.assertRaises(ValidationError):
            self.bali.clean()
        self.public.cover = other  # своё, но из скрытого альбома
        with self.assertRaises(ValidationError):
            self.public.clean()

    def test_unicode_digits_in_title_do_not_break_album_page(self):
        for title in ('²', '①', 'IMG_2', 'IMG_10', 'кадр'):
            self.photo(album=self.bali, title=title)
        r = self.client.get('/album/%d/' % self.bali.pk)
        self.assertEqual(r.status_code, 200)
        names = re.findall(r'data-caption="([^"]*)"', r.content.decode())
        self.assertEqual(len(names), 5)
        self.assertLess(names.index('IMG_2'), names.index('IMG_10'))  # числа по величине, а не по буквам


class PanelInputTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_bad_ids_give_400_or_404_not_500(self):
        for url, data in (
            ('/admin/toggle/', {'kind': 'album', 'id': '²', 'hidden': '1'}),
            ('/admin/rename/', {'kind': 'album', 'id': '9' * 40, 'name': 'x'}),
            ('/admin/order/', {'kind': 'album', 'section': '①', 'ids': ['1']}),
            ('/admin/photos/move/', {'album': self.bali.pk, 'ids': ['²']}),
            ('/admin/photos/cover/', {'photo': '①'}),
            ('/admin/photos/delete/', {'ids': ['²']}),
            ('/admin/trash/action/', {'action': 'restore', 'ids': ['9' * 40]}),
        ):
            r = self.client.post(url, data)
            self.assertIn(r.status_code, (400, 404), (url, r.status_code))

    def test_any_album_name_keeps_uploader_script_valid(self):
        name = 'Конец\\ "кавычки" & <b>'
        Album.objects.create(section=self.public, name=name)
        html = self.client.get('/admin/upload/').content.decode()
        data = re.search(r'<script id="albums-by-section" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(data)
        names = [a['name'] for albums in json.loads(data.group(1)).values() for a in albums]
        self.assertIn(name, names)


class FileDeletionTests(TransactionTestCase):
    """Файлы стираются только после успешной записи в базу (A05)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.tmp.name)
        self.override.enable()
        s = Section.objects.create(name='Р', slug='r')
        self.p = Photo(title='kadr', section=s)
        self.p.image.save('kadr.jpg', _image(), save=False)
        self.p.save()

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def test_failed_delete_keeps_files(self):
        path, pk = self.p.image.path, self.p.pk
        try:
            with transaction.atomic():
                self.p.delete()
                raise RuntimeError('сбой посреди операции')
        except RuntimeError:
            pass
        self.assertTrue(Photo.objects.filter(pk=pk).exists())
        self.assertTrue(os.path.exists(path))

    def test_successful_delete_removes_files(self):
        path = self.p.image.path
        self.p.delete()
        self.assertFalse(os.path.exists(path))


class OrphanCleanupTests(MediaTestCase):
    def test_fresh_unreferenced_file_is_kept_old_one_removed(self):
        import time

        self.client.force_login(self.staff)
        fresh = os.path.join(self.tmp.name, 'photos', 'fresh.jpg')
        old = os.path.join(self.tmp.name, 'photos', 'old.jpg')
        os.makedirs(os.path.dirname(fresh), exist_ok=True)
        for path in (fresh, old):
            open(path, 'wb').write(b'x')
        day_ago = time.time() - 2 * 24 * 3600
        os.utime(old, (day_ago, day_ago))
        r = self.client.post('/admin/disk/clean/')
        self.assertEqual(r.json()['removed'], 1)
        self.assertTrue(os.path.exists(fresh))
        self.assertFalse(os.path.exists(old))
