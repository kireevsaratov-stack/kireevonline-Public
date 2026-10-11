"""Загрузка фото: только настоящие фото, сжатие, превью."""

import hashlib
import io
import os
import tempfile
import time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ..models import Photo, Section


def _png_bytes(size=(64, 48), color=(200, 30, 30)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


class UploadTestCase(TestCase):
    """Основа: администратор, временная папка фото, отправка файла одной частью."""

    @classmethod
    def setUpTestData(cls):
        cls.cat = Section.objects.create(name='Репортаж', slug='reportazh')
        cls.staff = get_user_model().objects.create_user('staff', is_staff=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.media = os.path.join(self.tmp.name, 'media')
        self.override = override_settings(MEDIA_ROOT=self.media, BASE_DIR=self.tmp.name, SECURE_SSL_REDIRECT=False)
        self.override.enable()
        self.client.force_login(self.staff)

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def upload(self, name, content):
        return self.client.post(
            '/admin/upload/chunk/',
            {
                'upload_id': 'test' + str(abs(hash(name)) % 10000),
                'index': 0,
                'total': 1,
                'chunk_size': len(content),
                'name': name,
                'section': self.cat.pk,
                'album': '',
                'chunk': SimpleUploadedFile('chunk', content),
            },
        )

    def media_files(self):
        found = []
        for root, _, names in os.walk(self.media):
            found += [os.path.join(root, n) for n in names]
        return found


class UploadTests(UploadTestCase):
    """Загрузка принимает только фото и хранит их как .jpg; сохранение не пережимает снимок."""

    def test_real_photo_is_saved_as_jpg_with_thumbnail(self):
        r = self.upload('Закат.png', _png_bytes())
        self.assertEqual(r.json().get('ok'), True, r.content)
        photo = Photo.objects.get()
        self.assertTrue(photo.image.name.endswith('.jpg'))
        self.assertEqual(photo.title, 'Закат')
        self.assertTrue(os.path.exists(photo.image.path))
        self.assertTrue(photo.thumb and os.path.exists(photo.thumb.path))

    def test_program_disguised_as_upload_is_rejected(self):
        for name, content in [('evil.php', b'<?php echo 1; ?>'), ('fake.jpg', b'not a picture')]:
            r = self.upload(name, content)
            self.assertEqual(r.status_code, 400)
            self.assertTrue(r.json().get('fatal'))
        self.assertEqual(Photo.objects.count(), 0)
        self.assertEqual(self.media_files(), [])

    def test_saving_again_does_not_recompress_photo(self):
        self.upload('Портрет.png', _png_bytes())
        photo = Photo.objects.get()
        digest = hashlib.sha256(open(photo.image.path, 'rb').read()).hexdigest()
        files_before = sorted(self.media_files())
        photo = Photo.objects.get()  # как при правке в админке: загрузили из базы
        photo.title = 'Новое название'
        photo.save()
        self.assertEqual(hashlib.sha256(open(photo.image.path, 'rb').read()).hexdigest(), digest)
        self.assertEqual(sorted(self.media_files()), files_before)  # без лишних превью


def _jpeg_bytes(size=(900, 600), exif=True):
    from PIL import Image

    img = Image.new('RGB', size, (40, 120, 200))
    buf = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = 'Canon'  # производитель камеры
        ex[0x0110] = 'EOS R6'  # модель
        img.save(buf, 'JPEG', quality=95, exif=ex)
    else:
        img.save(buf, 'JPEG', quality=95)
    return buf.getvalue()


class UploadProtocolTests(UploadTestCase):
    """Внешний аудит 09.10.2026 (A01, A06, A07): загрузка по частям и проверка файла."""

    def send(self, uid, index, total, chunk_size, content, name='Кадр.jpg', section=None, album=''):
        return self.client.post(
            '/admin/upload/chunk/',
            {
                'upload_id': uid,
                'index': index,
                'total': total,
                'chunk_size': chunk_size,
                'name': name,
                'section': self.cat.pk if section is None else section,
                'album': album,
                'chunk': SimpleUploadedFile('chunk', content),
            },
        )

    def send_all(self, uid, content, size=4096, **kw):
        parts = [content[i : i + size] for i in range(0, len(content), size)]
        r = None
        for i, part in enumerate(parts):
            r = self.send(uid, i, len(parts), size, part, **kw)
        return r, parts

    def test_good_photo_is_shrunk_without_camera_data_and_with_thumbnail(self):
        from PIL import Image

        r, _ = self.send_all('good1', _jpeg_bytes((3000, 2000)))
        self.assertEqual(r.json()['ok'], True, r.content)
        photo = Photo.objects.get()
        with Image.open(photo.image.path) as img:
            self.assertEqual(max(img.size), 1920)
            self.assertEqual(len(img.getexif()), 0)
        self.assertTrue(os.path.exists(photo.thumb.path))

    def test_truncated_jpeg_is_rejected(self):
        data = _jpeg_bytes()
        r = self.upload('Обрезанный.jpg', data[: len(data) // 2])
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['fatal'])
        self.assertFalse(Photo.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_other_formats_are_not_even_parsed(self):
        """EPS/GIF и прочее под видом .jpg Pillow не разбирает (CVE в разборщике EPS)."""
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (20, 20)).save(buf, 'GIF')
        eps = b'%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n'
        for content in (buf.getvalue(), eps):
            r = self.upload('Картинка.jpg', content)
            self.assertEqual(r.status_code, 400)
        self.assertFalse(Photo.objects.exists())

    def test_eps_parser_is_never_called(self):
        """Уязвимость разборщика EPS в Pillow < 12.3.0: на сервере стоит 12.2.0 — разборщик не должен запускаться."""
        from unittest import mock

        from PIL import EpsImagePlugin

        eps = b'%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n'
        with mock.patch.object(
            EpsImagePlugin.EpsImageFile, '_open', side_effect=AssertionError('EPS разбирается')
        ) as m:
            r = self.upload('Обложка.jpg', eps)
        self.assertEqual(r.status_code, 400)
        m.assert_not_called()

    def test_extreme_sides_are_rejected_before_decoding(self):
        """Сторона больше 30 000 px — отказ до разбора, даже если площадь небольшая."""
        import struct
        import zlib

        def png(w, h):
            head = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
            chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))  # noqa: E731
            return (
                b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', head) + chunk(b'IDAT', zlib.compress(b'')) + chunk(b'IEND', b'')
            )

        r = self.upload('Полоска.png', png(40_000, 1))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Photo.objects.exists())

    def test_missing_middle_chunk_does_not_create_photo(self):
        data = _jpeg_bytes()
        parts = [data[i : i + 4096] for i in range(0, len(data), 4096)]
        self.assertGreaterEqual(len(parts), 3)
        for i in (0, len(parts) - 1):
            r = self.send('gap1', i, len(parts), 4096, parts[i])
        self.assertNotIn('done', r.json())
        self.assertFalse(Photo.objects.exists())
        r = self.send('gap1', 1, len(parts), 4096, parts[1])  # дослать середину (если частей больше — все)
        for i in range(2, len(parts) - 1):
            r = self.send('gap1', i, len(parts), 4096, parts[i])
        self.assertTrue(r.json().get('done'), r.content)
        self.assertEqual(Photo.objects.count(), 1)

    def test_retry_of_last_chunk_returns_the_same_photo(self):
        r, parts = self.send_all('retry1', _jpeg_bytes())
        first = r.json()['id']
        again = self.send('retry1', len(parts) - 1, len(parts), 4096, parts[-1]).json()
        self.assertEqual((again['done'], again['id']), (True, first))
        self.assertEqual(Photo.objects.count(), 1)

    def test_parameters_cannot_change_mid_file(self):
        other = Section.objects.create(name='Прогулки', slug='progulki')
        data = _jpeg_bytes()
        parts = [data[i : i + 4096] for i in range(0, len(data), 4096)]
        self.send('swap1', 0, len(parts), 4096, parts[0])
        r = self.send('swap1', 1, len(parts), 4096, parts[1], section=other.pk)
        self.assertEqual(r.status_code, 400)

    def test_bad_numbers_are_400_not_500(self):
        for index, total in (('-1', '3'), ('²', '3'), ('0', '0'), ('0', '99999999999999')):
            r = self.client.post(
                '/admin/upload/chunk/',
                {'upload_id': 'bad', 'index': index, 'total': total, 'chunk_size': '10', 'name': 'a.jpg',
                 'section': self.cat.pk, 'chunk': SimpleUploadedFile('chunk', b'0123456789')},
            )  # fmt: skip
            self.assertEqual(r.status_code, 400, (index, total))

    def test_album_from_hidden_section_cannot_be_paired_with_public_section(self):
        from ..models import Album

        hidden = Section.objects.create(name='Портреты', slug='portrety', hidden=True)
        album = Album.objects.create(section=hidden, name='Секрет')
        r, _ = self.send_all('mix1', _jpeg_bytes(), album=album.pk)  # раздел из формы — публичный «Репортаж»
        self.assertEqual(r.status_code, 400)
        r, _ = self.send_all('mix2', _jpeg_bytes(), album=album.pk, section=hidden.pk)
        self.assertEqual(Photo.objects.get().section_id, hidden.pk)


class UploadCrashTests(UploadTestCase):
    """Аудит 2 (09.10.2026): обрывы и сбои посреди сборки фото."""

    send = UploadProtocolTests.send

    def parts(self, size=4096):
        data = _jpeg_bytes()
        return [data[i : i + size] for i in range(0, len(data), size)]

    def chunk_dir(self):
        return os.path.join(self.tmp.name, 'chunk_tmp')

    def send_all_but_last(self, uid, parts):
        for i in range(len(parts) - 1):
            self.send(uid, i, len(parts), 4096, parts[i])

    def test_fresh_lock_gives_409_stale_lock_is_taken_over(self):
        parts = self.parts()
        self.send_all_but_last('lock1', parts)
        lock = os.path.join(self.chunk_dir(), 'lock1.lock')
        open(lock, 'w').close()  # «кто-то собирает прямо сейчас»
        r = self.send('lock1', len(parts) - 1, len(parts), 4096, parts[-1])
        self.assertEqual(r.status_code, 409)
        old = time.time() - 3600
        os.utime(lock, (old, old))  # сборку прервали час назад — замок брошен
        r = self.send('lock1', len(parts) - 1, len(parts), 4096, parts[-1])
        self.assertTrue(r.json().get('done'), r.content)
        self.assertEqual(Photo.objects.count(), 1)

    def test_retry_after_photo_saved_but_answer_lost(self):
        """Фото записалось, а ответ не дошёл и служебные файлы остались — повтор отдаёт то же фото."""
        parts = self.parts()
        self.send_all_but_last('lost1', parts)
        r = self.send('lost1', len(parts) - 1, len(parts), 4096, parts[-1])
        first = r.json()['id']
        open(os.path.join(self.chunk_dir(), 'lost1.lock'), 'w').close()  # остатки прерванной обработки
        for i in (0, len(parts) - 1):
            again = self.send('lost1', i, len(parts), 4096, parts[i]).json()
            self.assertEqual((again.get('done'), again.get('id')), (True, first))
        self.assertEqual(Photo.objects.count(), 1)

    def test_database_failure_leaves_no_files(self):
        from unittest import mock

        with mock.patch.object(Photo, 'save', side_effect=RuntimeError('база недоступна')):
            r = self.upload('Кадр.jpg', _jpeg_bytes())
        self.assertEqual(r.status_code, 500)
        self.assertFalse(Photo.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_thumbnail_failure_leaves_no_files(self):
        from unittest import mock

        from django.db.models.fields.files import FieldFile

        real_save = FieldFile.save

        def save(self_, name, content, save=True):
            if name.endswith('_t.jpg'):
                raise OSError('диск переполнен')
            return real_save(self_, name, content, save)

        with mock.patch.object(FieldFile, 'save', save):
            r = self.upload('Кадр.jpg', _jpeg_bytes())
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.media_files(), [])

    def test_damaged_service_data_is_a_clear_refusal(self):
        parts = self.parts()
        self.send('meta1', 0, len(parts), 4096, parts[0])
        with open(os.path.join(self.chunk_dir(), 'meta1.json'), 'w') as f:
            f.write('{не json')
        r = self.send('meta1', 1, len(parts), 4096, parts[1])
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['fatal'])
