"""Демо-данные для пустой копии сайта (python manage.py demo_data)."""

import tempfile

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from ..models import Album, Photo, Section


class DemoDataTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_fills_empty_site_and_pages_open(self):
        with override_settings(DEBUG=True, MEDIA_ROOT=self.tmp.name, SECURE_SSL_REDIRECT=False):
            call_command('demo_data', photos=1, stdout=open('/dev/null', 'w'))
            self.assertEqual((Section.objects.count(), Album.objects.count(), Photo.objects.count()), (3, 5, 5))
            self.assertTrue(all(p.thumb for p in Photo.objects.all()))  # прошли обычный путь загрузки
            album = Album.objects.first()
            self.assertEqual(self.client.get('/').status_code, 200)
            self.assertContains(self.client.get('/album/%d/' % album.pk), 'Демо-альбом')
            with self.assertRaises(CommandError):  # второй раз — нет: база уже не пустая
                call_command('demo_data', photos=1)

    def test_refuses_on_real_site(self):
        with override_settings(DEBUG=False, MEDIA_ROOT=self.tmp.name):
            with self.assertRaises(CommandError):
                call_command('demo_data', photos=1)
        self.assertFalse(Section.objects.exists())
