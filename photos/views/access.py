"""Только для администратора: без входа — сразу на нашу страницу входа /admin/login/
(стандартный декоратор Django вёл бы через вход панели Django /admindjango/login/)."""

from functools import partial

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required as _staff_member_required

staff_member_required = partial(_staff_member_required, login_url=settings.LOGIN_URL)
