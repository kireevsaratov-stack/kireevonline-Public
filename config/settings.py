import os
import sys
import tempfile as _tempfile
from pathlib import Path

# --- Sprinthost: современный SQLite (системный слишком старый для Django 5) ---
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# Безопасно по умолчанию: на сервере ключ и DEBUG задаёт public_html/site.wsgi.
# Если настройка потеряется (переезд, восстановление из архива) — отладка остаётся
# выключенной, а ключ берётся случайный на время работы процесса: сайт открывается,
# подделать вход нельзя (вход в админку будет сбрасываться при перезапуске — сигнал
# задать ключ). Локально для разработки: DJANGO_DEBUG=True.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'photos',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.security.SecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'config.security.LoginThrottleMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'config.version.VersionHeaderMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'photos.context_processors.navigation',
                'photos.context_processors.site_version',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
MEDIA_URL = '/media/'
STATICFILES_DIRS = [BASE_DIR / 'static']

_public_html = BASE_DIR.parent / 'public_html'
if _public_html.is_dir():
    STATIC_ROOT = _public_html / 'static'
    MEDIA_ROOT = _public_html / 'media'
else:
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    MEDIA_ROOT = BASE_DIR / 'media'

# Локальный просмотр с настоящими фото из бэкапа: DJANGO_MEDIA_ROOT=../backups/media
if os.environ.get('DJANGO_MEDIA_ROOT'):
    MEDIA_ROOT = Path(os.environ['DJANGO_MEDIA_ROOT']).resolve()

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/admin/login/'  # наша страница входа — общая для нашей панели и панели Django
LOGIN_REDIRECT_URL = '/admin/'


# Доверенные источники для CSRF (прод) — только https
_base_host = 'kireevonline.ru'
CSRF_TRUSTED_ORIGINS = [
    'https://' + _base_host,
    'https://www.' + _base_host,
    'https://' + _base_host + '.xsph.ru',
]

# HTTPS на сервере (локально с DJANGO_DEBUG=True работаем по http).
# Хостинг правильно сообщает сайту, пришёл посетитель по http или https
# (проверено 01.10.2026 по robots.txt), поэтому перенаправление не зацикливается.
if not DEBUG:
    SECURE_SSL_REDIRECT = True  # http:// → https://
    SESSION_COOKIE_SECURE = True  # вход в админку только по защищённому соединению
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # браузер год сам открывает сайт только по https (было 30 дней)

# Временные файлы загрузок — на диск, а не в /tmp (оперативная память) на сервере
_server_tmp = '/home/user/tmp'
if os.path.isdir(_server_tmp):
    FILE_UPLOAD_TEMP_DIR = _server_tmp
    _tempfile.tempdir = _server_tmp
    os.environ['TMPDIR'] = _server_tmp

# Счётчики неудачных входов (config/security.py) — во временной папке (на сервере /home/user/tmp).
LOGIN_COUNTERS_DIR = os.path.join(_tempfile.gettempdir(), 'kireevonline-login')
