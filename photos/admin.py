from django.contrib import admin
from django.contrib.admin.models import LogEntry

from .models import Album, Photo, Section


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order', 'hidden']
    list_editable = ['hidden']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ['name', 'section', 'order', 'hidden']
    list_editable = ['hidden']
    list_filter = ['section', 'hidden']
    ordering = ['section', 'order', 'name']
    fields = ['section', 'name', 'order', 'hidden', 'place', 'period', 'intro', 'description', 'gear', 'cover']
    raw_id_fields = ['cover']


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    """Запасная панель: фото здесь только смотреть и править подписи/порядок. Загрузка и замена файлов —
    только через нашу панель (/admin/upload/), где файл проверяется до разбора (аудит 2, 09.10.2026)."""

    list_display = ['title', 'section', 'album', 'order', 'created_at']
    list_filter = ['section', 'album']
    ordering = ['section', 'order', '-created_at']
    raw_id_fields = ['album']
    fields = ['title', 'image', 'thumb', 'album', 'section', 'order', 'is_deleted', 'deleted_at']
    readonly_fields = ['image', 'thumb', 'section']

    def has_add_permission(self, request):
        return False


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    """«Журнал действий» — только просмотр: что, кто и когда менял.
    Записи ведут photos/action_log.py и сама админка."""

    list_display = ['action_time', 'user', 'object_repr', 'change_message']
    list_filter = ['action_flag', 'user']
    search_fields = ['object_repr', 'change_message']
    date_hierarchy = 'action_time'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
