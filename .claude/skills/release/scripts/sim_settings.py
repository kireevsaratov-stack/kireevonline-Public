"""Настройки Django для проверки миграций на КОПИИ базы сайта (не на рабочей базе Mac).

KO_SIM_DIR=<папка с db.sqlite3> PYTHONPATH=.claude/skills/release/scripts DJANGO_SETTINGS_MODULE=sim_settings \
    ../.venv/bin/python manage.py migrate photos <шаг>
"""

import os

from config.settings import *  # noqa: F403

SIM = os.environ['KO_SIM_DIR']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.path.join(SIM, 'db.sqlite3')}}
MEDIA_ROOT = os.path.join(SIM, 'media')
