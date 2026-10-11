"""Адреса публичных страниц галереи. Подключаются в config/urls.py от корня сайта."""

from django.urls import path, register_converter
from django.views.generic import RedirectView

from .views import pages


class UnicodeSlugConverter:
    """Позволяет использовать русские буквы в адресах разделов."""

    regex = r'[-\w]+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(UnicodeSlugConverter, 'uslug')

urlpatterns = [
    path('section/<uslug:slug>/', pages.section_detail, name='section'),
    path('album/<int:album_id>/', pages.album_detail, name='album'),
    path('shuffle/', pages.shuffle, name='shuffle'),
]

# Старые адреса (до 08.10.2026). /photos/ по-прежнему отдаёт главную без перенаправления — см. config/urls.py.
legacy_urlpatterns = [
    path('', pages.home),
    path('category/<uslug:slug>/', RedirectView.as_view(url='/section/%(slug)s/', permanent=True)),
    path('subcategory/<int:album_id>/', RedirectView.as_view(url='/album/%(album_id)s/', permanent=True)),
    path('shuffle/', RedirectView.as_view(url='/shuffle/', permanent=True)),
    # служебное переехало в /admin/ — старые закладки ведут туда же
    path('manage/', RedirectView.as_view(url='/admin/')),
    path('manage/album/<int:pk>/', RedirectView.as_view(url='/admin/album/%(pk)s/')),
    path('upload/', RedirectView.as_view(url='/admin/upload/')),
    path('trash/', RedirectView.as_view(url='/admin/trash/')),
    path('stats/', RedirectView.as_view(url='/admin/disk/')),
]
