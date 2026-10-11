"""Защита: https, безопасные настройки, заголовки, пауза после неверных паролей, журнал действий."""

import os
import re
import subprocess
import sys
import tempfile
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import Album, Section


class SecurityTests(TestCase):
    """HTTPS и безопасные настройки по умолчанию (на сервере DEBUG выключен)."""

    def test_http_redirects_to_https(self):
        r = self.client.get('/about/')
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r['Location'], 'https://testserver/about/')

    def test_https_has_hsts_and_secure_cookies(self):
        r = self.client.get('/admin/login/', secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('max-age=31536000', r['Strict-Transport-Security'])
        self.assertTrue(r.cookies['csrftoken']['secure'])

    def test_settings_are_safe_without_server_environment(self):
        env = {k: v for k, v in os.environ.items() if k not in ('DJANGO_DEBUG', 'DJANGO_SECRET_KEY')}
        code = (
            'import django, os; os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"; '
            'from django.conf import settings as s; '
            'print(s.DEBUG, s.SECRET_KEY.startswith("django-insecure"), len(s.SECRET_KEY) >= 40)'
        )
        out = subprocess.run(
            [sys.executable, '-c', code], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, check=True
        ).stdout.split()
        self.assertEqual(out, ['False', 'False', 'True'])


@override_settings(SECURE_SSL_REDIRECT=False)
class HardeningTests(TestCase):
    """Защита 08.10.2026: заголовки, ограничение попыток входа, security.txt, журнал действий."""

    @classmethod
    def setUpTestData(cls):
        cls.cat = Section.objects.create(name='Репортаж', slug='reportazh')
        cls.album = Album.objects.create(section=cls.cat, name='Мотофест')
        cls.admin = get_user_model().objects.create_user('roman', password='верный-пароль-123', is_staff=True)

    def setUp(self):
        self.counters = tempfile.TemporaryDirectory()  # свои счётчики входов у каждого теста
        self.addCleanup(self.counters.cleanup)
        self.enterContext(override_settings(LOGIN_COUNTERS_DIR=self.counters.name))

    def test_csp_allows_only_own_scripts_with_page_nonce(self):
        r = self.client.get('/')
        csp = r['Content-Security-Policy']
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn('unsafe-inline', csp.split('script-src')[1].split(';')[0])
        scripts = re.findall(r'<script([^>]*)>', r.content.decode())
        self.assertTrue(scripts)
        for attrs in scripts:  # данные (application/json) не выполняются — nonce им не нужен
            self.assertTrue(f'nonce="{nonce}"' in attrs or 'src=' in attrs or 'application/json' in attrs, attrs)
        self.assertIn('camera=()', r['Permissions-Policy'])

    def test_no_inline_event_handlers_in_templates(self):
        """Обработчики вида onclick="…" CSP запретит — в шаблонах их быть не должно."""
        tpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        checked = 0
        for root, _, files in os.walk(tpl_dir):
            for name in files:
                with open(os.path.join(root, name), encoding='utf-8') as f:
                    self.assertIsNone(re.search(r'\son[a-z]+\s*=\s*["\']', f.read()), name)
                checked += 1
        self.assertGreater(checked, 10)  # тест не должен «проходить», ничего не найдя (было до 09.10.2026)

    def test_pages_load_nothing_from_other_servers(self):
        """Шрифт и всё остальное — только со своего сервера; чужие адреса — лишь обычные ссылки (VK, Telegram)."""
        for url in ('/', '/about/', reverse('album', args=[self.album.pk])):
            html = self.client.get(url).content.decode()
            self.assertNotIn('googleapis', html)
            self.assertNotIn('gstatic', html)
            for tag in re.findall(r'<(?:script|img|link|iframe|source)\b[^>]*>', html):
                for ref in re.findall(r'(?:src|href)="(https?://[^"]+)"', tag):
                    self.assertTrue(ref.startswith('https://kireevonline.ru'), (url, tag))
        csp = self.client.get('/')['Content-Security-Policy']
        self.assertNotIn('http', csp)

    def test_nonce_differs_between_requests(self):
        a = self.client.get('/')['Content-Security-Policy']
        b = self.client.get('/')['Content-Security-Policy']
        self.assertNotEqual(a, b)

    def test_security_txt(self):
        r = self.client.get('/.well-known/security.txt')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Contact: https://t.me/')
        self.assertContains(r, 'Expires: ')

    def _login(self, password, ip='10.0.0.1'):
        return self.client.post(
            '/admin/login/', {'username': 'roman', 'password': password, 'next': '/admin/'}, REMOTE_ADDR=ip
        )

    def test_login_paused_after_five_failures_even_with_right_password(self):
        for _ in range(5):
            self.assertEqual(self._login('не-тот').status_code, 200)
        r = self._login('верный-пароль-123')
        self.assertEqual(r.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_other_address_not_paused(self):
        for _ in range(5):
            self._login('не-тот', ip='10.0.0.1')
        self.assertEqual(self._login('верный-пароль-123', ip='10.0.0.2').status_code, 302)

    def test_successful_login_resets_counter(self):
        for _ in range(4):
            self._login('не-тот')
        self.assertEqual(self._login('верный-пароль-123').status_code, 302)
        self.client.logout()
        for _ in range(4):
            self._login('не-тот')
        self.assertEqual(self._login('верный-пароль-123').status_code, 302)

    def test_whole_site_limit_when_addresses_vary(self):
        for i in range(30):
            self._login('не-тот', ip=f'10.1.0.{i}')
        self.assertEqual(self._login('верный-пароль-123', ip='10.9.9.9').status_code, 429)

    def test_admin_actions_are_logged(self):
        from django.contrib.admin.models import LogEntry

        self.client.force_login(self.admin)
        self.client.post(reverse('panel:toggle'), {'kind': 'album', 'id': self.album.pk, 'hidden': '1'})
        self.client.post(reverse('panel:rename'), {'kind': 'album', 'id': self.album.pk, 'name': 'Мотофест 2025'})
        log = list(LogEntry.objects.order_by('pk').values_list('change_message', 'object_repr'))
        self.assertEqual(log[0][0], 'Скрыт от посетителей')
        self.assertIn('«Мотофест» → «Мотофест 2025»', log[1][0])
        get_user_model().objects.filter(pk=self.admin.pk).update(is_superuser=True)  # Роман — суперпользователь
        r = self.client.get('/admindjango/admin/logentry/')
        self.assertContains(r, 'Мотофест 2025')


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginCounterTests(TestCase):
    """Аудит 09.10.2026 (A08): счётчики неудачных входов на настоящем хранилище, а не на подмене."""

    def setUp(self):
        self.counters = tempfile.TemporaryDirectory()
        self.addCleanup(self.counters.cleanup)
        self.enterContext(override_settings(LOGIN_COUNTERS_DIR=self.counters.name))
        get_user_model().objects.create_user('roman', password='верный-пароль-123', is_staff=True)

    def test_new_failures_do_not_shorten_the_window(self):
        from config import security

        security._update('k', 900, 1)
        until1 = float(open(os.path.join(self.counters.name, 'k')).read().split()[1])
        security._update('k', 900, 1)
        until2 = float(open(os.path.join(self.counters.name, 'k')).read().split()[1])
        self.assertEqual(until1, until2)
        self.assertGreater(until2 - time.time(), 890)

    def test_simultaneous_failures_are_all_counted(self):
        from concurrent.futures import ThreadPoolExecutor

        from config import security

        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda _: security._update('t', 900, 1), range(400)))
        self.assertEqual(security._update('t', 900, None), 400)

    def test_mounted_address_does_not_bypass_pause(self):
        """Тот же вход через приставку (site.wsgi) — тоже на паузе."""
        for _ in range(5):
            self.client.post('/admin/login/', {'username': 'roman', 'password': 'нет'}, REMOTE_ADDR='10.0.0.7')
        r = self.client.post(
            '/admin/login/',
            {'username': 'roman', 'password': 'верный-пароль-123'},
            REMOTE_ADDR='10.0.0.7',
            SCRIPT_NAME='/site.wsgi',
        )
        self.assertEqual(r.status_code, 429)
