from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from photos.urls import legacy_urlpatterns
from photos.views.pages import about, home
from photos.views.seo import robots_txt, security_txt, sitemap_xml

urlpatterns = [
    # Главная — прямо на kireevonline.ru. /photos/ тоже отдаёт главную (не редирект):
    # раньше «/» навсегда (301) вёл на /photos/, и браузеры это запомнили —
    # обратный редирект дал бы им бесконечную петлю. Основной адрес задаёт canonical.
    path('', home, name='home'),
    path('about/', about, name='about'),
    path('robots.txt', robots_txt),
    path('sitemap.xml', sitemap_xml),
    path('.well-known/security.txt', security_txt),
    # /admin/ — наша панель; /admindjango/ — стандартная панель Django (вход — через нашу страницу)
    path('admin/', include('photos.panel_urls')),
    path('admindjango/login/', RedirectView.as_view(url='/admin/login/', query_string=True)),
    path('admindjango/', admin.site.urls),
    path('', include('photos.urls')),
    path('photos/', include(legacy_urlpatterns)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
