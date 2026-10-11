"""Адреса панели управления сайтом — /admin/ (Роман, 08.10.2026). Всё здесь — только для администратора.
Стандартная панель Django — /admindjango/ (запасной вход); вход у обеих общий — /admin/login/.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from .views import disk, panel, trash, uploads

app_name = 'panel'

urlpatterns = [
    path('', panel.albums, name='albums'),
    path('login/', auth_views.LoginView.as_view(template_name='photos/panel/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    # разделы и альбомы
    path('order/', panel.reorder, name='order'),
    path('toggle/', panel.toggle_hidden, name='toggle'),
    path('rename/', panel.rename, name='rename'),
    path('create/', panel.create, name='create'),
    path('delete/', panel.delete, name='delete'),
    path('album/<int:pk>/', panel.album_texts, name='album_texts'),
    # фото
    path('upload/', uploads.upload_page, name='upload'),
    path('upload/chunk/', uploads.upload_chunk, name='upload_chunk'),
    path('photos/move/', panel.move_photos, name='move_photos'),
    path('photos/cover/', panel.set_cover, name='set_cover'),
    path('photos/delete/', trash.delete_photos, name='delete_photos'),
    path('trash/', trash.trash_page, name='trash'),
    path('trash/action/', trash.trash_action, name='trash_action'),
    path('disk/', disk.disk, name='disk'),
    path('disk/clean/', disk.clean_orphans, name='clean_orphans'),
]
