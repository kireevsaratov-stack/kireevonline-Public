"""Правки после того, как Роман посмотрел сайт 02.10.2026:

- «Лапки»: подпись «Фестиваль домашних животных. Собаководы всех пород, объединяйтесь!»;
- Epiccon: 17 кадров с фестиваля Constanta (03–04.05.2025) → в корзину;
- «Прогулки 2023–2026»: одна подпись «Просто гуляю по Москве.», место, техника (год — в названии);
- 42 кадра из «Прогулок 2023» — Питер, 29.07–02.08.2024 (файлы 14433–14474) → новый альбом
  «Питер 2024» в «Путешествиях»; нынешний «Питер» (поездка 2025) → «Питер 2025».

Обратимо: откат возвращает подписи, кадры из корзины и в «Прогулки 2023», удаляет пустой
«Питер 2024» и возвращает название «Питер».
"""
from django.db import migrations
from django.utils import timezone

WALKS_CAT, TRAVEL_CAT, EPICCON, WALKS_2023 = 1, 3, 25, 38
LAPKI = (23, 'Собаководы всех пород, соединяйтесь!',
         'Фестиваль домашних животных. Собаководы всех пород, объединяйтесь!')
CONSTANTA = [3664, 3665, 3667, 3668, 3669, 3670, 3671, 3673, 3674, 3675, 3676, 3678, 3679, 3680, 3681, 3682, 3683]
FIELDS = ('place', 'period', 'intro', 'gear')
WALKS_INTRO = 'Просто гуляю по Москве.'  # одна подпись на все «Прогулки» (Роман 02.10)
WALKS = {
    38: dict(place='Москва', intro=WALKS_INTRO, gear='Canon 6D Mark II + EF 70-200 2.8'),
    12: dict(place='Москва', intro=WALKS_INTRO,
             gear='Canon R6 Mark II + RF 100 2.8 + RF 35 1.8 + RF 100-500 4.5-7.1 + RF 50 1.2'),
    10: dict(place='Москва', intro=WALKS_INTRO,
             gear='Sony A7R V + GM 70-200 2.8; Sony A7C II + GM 35 1.4 + Sigma 28-70 2.8 + G 40 2.5 '
                  '+ GM 50 1.4 + GM 24-70 2.8'),
    11: dict(place='Москва', intro=WALKS_INTRO, gear='Ricoh GR IV; Canon R5 Mark II + RF 70-200 2.8 + RF 35 1.4'),
}
PITER_PHOTOS = list(range(4258, 4300))
PITER_2024 = dict(name='Питер 2024', place='Санкт-Петербург', period='июль–август 2024',
                  gear='Canon R6 Mark II + RF 24-105 2.8')
PITER_COVER = 4299  # Самсон в Петергофе
RENAME = (16, 'Питер', 'Питер 2025')


def forward(apps, schema_editor):
    SubCategory = apps.get_model('photos', 'SubCategory')
    Photo = apps.get_model('photos', 'Photo')
    SubCategory.objects.filter(pk=LAPKI[0], intro=LAPKI[1]).update(intro=LAPKI[2])
    Photo.objects.filter(pk__in=CONSTANTA, subcategory_id=EPICCON, is_deleted=False).update(
        is_deleted=True, deleted_at=timezone.now())
    for pk, values in WALKS.items():
        SubCategory.objects.filter(pk=pk).update(**{f: values.get(f, '') for f in FIELDS})
    moving = Photo.objects.filter(pk__in=PITER_PHOTOS, subcategory_id=WALKS_2023)
    if moving.exists():
        cover = PITER_COVER if moving.filter(pk=PITER_COVER).exists() else None
        album = SubCategory.objects.create(category_id=TRAVEL_CAT, cover_id=cover, **PITER_2024)
        moving.update(subcategory_id=album.pk, category_id=TRAVEL_CAT)
    SubCategory.objects.filter(pk=RENAME[0], name=RENAME[1]).update(name=RENAME[2])


def backward(apps, schema_editor):
    SubCategory = apps.get_model('photos', 'SubCategory')
    Photo = apps.get_model('photos', 'Photo')
    SubCategory.objects.filter(pk=LAPKI[0], intro=LAPKI[2]).update(intro=LAPKI[1])
    Photo.objects.filter(pk__in=CONSTANTA, subcategory_id=EPICCON, is_deleted=True).update(
        is_deleted=False, deleted_at=None)
    SubCategory.objects.filter(pk__in=WALKS).update(**{f: '' for f in FIELDS})
    album = SubCategory.objects.filter(category_id=TRAVEL_CAT, name=PITER_2024['name']).first()
    if album:
        Photo.objects.filter(pk__in=PITER_PHOTOS, subcategory_id=album.pk).update(
            subcategory_id=WALKS_2023, category_id=WALKS_CAT)
        if not Photo.objects.filter(subcategory_id=album.pk).exists():
            album.delete()
    SubCategory.objects.filter(pk=RENAME[0], name=RENAME[2]).update(name=RENAME[1])


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0010_album_texts'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
