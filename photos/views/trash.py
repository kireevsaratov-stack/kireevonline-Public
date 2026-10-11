"""Корзина: удалённые фото можно вернуть или стереть навсегда (только для администратора)."""

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .. import action_log
from ..models import Photo
from .access import staff_member_required
from .params import to_ids


@staff_member_required
@require_POST
def delete_photos(request):
    """Мягкое удаление — фото уезжает в «Корзину», файлы остаются на месте."""
    from django.utils import timezone

    ids = to_ids(request.POST.getlist('ids'))
    if ids is None:
        return JsonResponse({'ok': False, 'error': 'неверные номера фото'}, status=400)
    deleted = Photo.objects.filter(pk__in=ids, is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
    action_log.log(request, f'В корзину фото: {deleted}')
    return JsonResponse({'ok': True, 'deleted': deleted})


@staff_member_required
def trash_page(request):
    photos = Photo.objects.filter(is_deleted=True).select_related('section', 'album').order_by('-deleted_at', '-pk')
    return render(request, 'photos/panel/trash.html', {'photos': photos})


@staff_member_required
@require_POST
def trash_action(request):
    """Действия в корзине: restore (вернуть), delete (стереть выбранные), empty (очистить всё)."""
    action = request.POST.get('action')
    ids = to_ids(request.POST.getlist('ids'))
    if ids is None:
        return JsonResponse({'ok': False, 'error': 'неверные номера фото'}, status=400)
    if action == 'restore':
        restored = Photo.objects.filter(pk__in=ids, is_deleted=True).update(is_deleted=False, deleted_at=None)
        action_log.log(request, f'Из корзины возвращено фото: {restored}')
        return JsonResponse({'ok': True, 'restored': restored})
    if action == 'empty':
        qs = Photo.objects.filter(is_deleted=True)
    elif action == 'delete':
        qs = Photo.objects.filter(is_deleted=True, pk__in=ids)
    else:
        return JsonResponse({'ok': False, 'error': 'неизвестное действие'}, status=400)
    removed = 0
    for p in list(qs):
        p.delete()  # файл и превью сотрутся после успешной записи в базу (см. models._photo_delete_files)
        removed += 1
    action_log.log(request, f'Стёрто из корзины навсегда фото: {removed}', flag=action_log.DELETION)
    return JsonResponse({'ok': True, 'removed': removed})
