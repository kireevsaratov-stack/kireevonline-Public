"""Защита сайта (08.10.2026): заголовки безопасности и ограничение попыток входа.

1. SecurityHeadersMiddleware — на каждый ответ:
   - Content-Security-Policy: страница выполняет только свои скрипты — файлы с сайта и встроенные
     <script nonce="{{ request.csp_nonce }}">. Скрипт, подброшенный в страницу чужим текстом, браузер не запустит.
   - Permissions-Policy: камера, микрофон, геолокация и т. п. сайту не нужны — запрещены; полный экран — только свой.
2. Ограничение попыток входа (LoginThrottleMiddleware + сигналы входа):
   - с одного адреса — не больше LOGIN_LIMIT_PER_IP неудачных попыток за LOGIN_WINDOW, потом пауза;
   - на весь сайт — не больше LOGIN_LIMIT_TOTAL неудачных попыток за час (на случай, если адрес подделан).
   Счётчики — маленькие файлы во временной папке с блокировкой (fcntl): прибавление атомарное для всех
   процессов сайта, срок окна не сбрасывается новыми попытками; адрес хранится только хэшем с ключом сайта.
   Общий лимит может на время закрыть вход и владельцу — для личной галереи это приемлемо (сессия входа
   живёт две недели), зато подбор пароля с подменой адресов упирается в него.
"""

import fcntl
import hashlib
import secrets
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from django.http import HttpResponse

LOGIN_LIMIT_PER_IP = 5
LOGIN_WINDOW = 15 * 60
LOGIN_LIMIT_TOTAL = 30
LOGIN_TOTAL_WINDOW = 60 * 60

CSP = '; '.join(
    [
        "default-src 'self'",
        "script-src 'self' 'nonce-{nonce}'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
PERMISSIONS_POLICY = (
    'camera=(), microphone=(), geolocation=(), payment=(), usb=(), '
    'serial=(), bluetooth=(), browsing-topics=(), fullscreen=(self)'
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        response.setdefault('Content-Security-Policy', CSP.format(nonce=request.csp_nonce))
        response.setdefault('Permissions-Policy', PERMISSIONS_POLICY)
        return response


def client_ip(request):
    # Хостинг ставит сайт за прокси: настоящий адрес посетителя — в X-Real-IP.
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')


def _ip_key(request):
    raw = (client_ip(request) + settings.SECRET_KEY).encode()
    return 'ip-' + hashlib.sha256(raw).hexdigest()[:32]


_TOTAL_KEY = 'total'


def _counter_path(key):
    folder = Path(getattr(settings, 'LOGIN_COUNTERS_DIR', None) or Path(tempfile.gettempdir()) / 'kireevonline-login')
    folder.mkdir(parents=True, exist_ok=True)
    return folder / key


def _update(key, window, delta):
    """Счётчик неудач в окне window секунд: (число, конец окна). delta=None — только прочитать,
    0 — сбросить. Под блокировкой файла — одновременные попытки не теряются."""
    with open(_counter_path(key), 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            count, until = (float(x) for x in f.read().split())
        except ValueError:
            count, until = 0, 0
        now = time.time()
        if until <= now:  # окно закончилось — счёт заново
            count, until = 0, now + window
        if delta is not None:
            count = 0 if delta == 0 else count + delta
            f.seek(0)
            f.truncate()
            f.write('%d %f' % (count, until))
        return int(count)


def login_blocked(request):
    return (
        _update(_ip_key(request), LOGIN_WINDOW, None) >= LOGIN_LIMIT_PER_IP
        or _update(_TOTAL_KEY, LOGIN_TOTAL_WINDOW, None) >= LOGIN_LIMIT_TOTAL
    )


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    _update(_ip_key(request), LOGIN_WINDOW, 1)
    _update(_TOTAL_KEY, LOGIN_TOTAL_WINDOW, 1)


@receiver(user_logged_in)
def _on_logged_in(sender, request, user, **kwargs):
    if request is not None:
        _update(_ip_key(request), LOGIN_WINDOW, 0)


BLOCKED_PAGE = (
    '<!doctype html><meta charset="utf-8"><title>Слишком много попыток</title>'
    '<body style="background:#000;color:#ddd;font:16px/1.5 sans-serif;padding:40px">'
    '<p>Слишком много неудачных попыток входа. Подождите 15 минут и попробуйте снова.</p>'
)


class LoginThrottleMiddleware:
    """Пока действует пауза, форма входа не проверяет пароль вовсе — подбирать нечего."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # path_info — путь внутри сайта: при запуске через site.wsgi с приставкой адрес входа тот же
        if request.method == 'POST' and request.path_info == settings.LOGIN_URL and login_blocked(request):
            return HttpResponse(BLOCKED_PAGE, status=429)
        return self.get_response(request)
