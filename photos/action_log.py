"""Журнал действий администратора (08.10.2026): кто, когда и что сделал в «Управлении», корзине,
с обложками и загрузкой. Пишется в стандартный журнал Django — смотреть: «Панель Django» → «Журнал действий».
"""

import logging

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

__all__ = ['log', 'ADDITION', 'CHANGE', 'DELETION']


def log(request, message, obj=None, flag=CHANGE):
    try:
        LogEntry.objects.create(
            user_id=request.user.pk,
            content_type=ContentType.objects.get_for_model(obj) if obj is not None else None,
            object_id=str(obj.pk) if obj is not None else None,
            object_repr=(str(obj) if obj is not None else '—')[:200],
            action_flag=flag,
            change_message=message,
        )
    except Exception:  # журнал не должен ломать само действие, но сбой видно в журнале сервера
        logger.exception('журнал действий: запись не удалась (%s)', message)
