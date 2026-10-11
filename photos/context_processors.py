from django.db.models import Prefetch

from .models import Album, Section


def navigation(request):
    # Меню у всех одинаковое — только то, что видят посетители (Роман, 03.10.2026: админ видит сайт как гость,
    # отличие — только панель «Админ»). Скрытое — в «Админ → Альбомы»; для служебных списков (перенос фото) —
    # полный список admin_sections, только администратору.
    context = {
        'all_sections': Section.objects.filter(hidden=False).prefetch_related(
            Prefetch('albums', queryset=Album.objects.filter(hidden=False))
        )
    }
    if request.user.is_staff:
        context['admin_sections'] = Section.objects.prefetch_related('albums')
    return context


def site_version(request):
    """Номер версии кода — к адресам стилей и скриптов (…/site.css?v=…), чтобы после выкладки браузер взял новые."""
    from config.version import VERSION

    return {'site_version': VERSION}
