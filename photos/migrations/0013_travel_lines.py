"""Путешествия — по просьбе Романа 02.10.2026 оперативно у всех альбомов: место, ОДИН месяц (не диапазон),
техника (из оригиналов) и строка «Коротко» — строки Романа (Алтай — по фотографиям). Записки напишем потом.
Бали не трогаем; у Узбекистана меняется только «Коротко» — без «как из кино» (Роман). Альбомы ищем по разделу и названию (номера на сайте и на Mac разные).
У «Питера 2024» были место и техника (миграция 0011) и «июль–август 2024» — откат вернёт их; у остальных было пусто.
"""
from django.db import migrations

TRAVEL = 3
FIELDS = ('place', 'period', 'intro', 'gear')
LINES = {
    'Китай': dict(place='Пекин', period='декабрь 2025',
                  intro='Летний дворец зимой, Великая Китайская стена, современное искусство и улицы Пекина.',
                  gear='Sony A7C II + GM 35 1.4 + GM 24-70 2.8; Ricoh GR IV'),
    'Тайланд': dict(place='Бангкок, Паттайя', period='декабрь 2023',
                    intro='Многогранность Тайланда. Глубина Паттайи.',
                    gear='Canon R6 Mark II + RF 70-200 4 + RF 50 1.8'),
    'Питер 2024': dict(place='Санкт-Петербург', period='июль 2024',
                       intro='Петергоф и Летний сад.',
                       gear='Canon R6 Mark II + RF 24-105 2.8'),
    'Питер 2025': dict(place='Санкт-Петербург', period='июль 2025',
                       intro='Всего понемногу: от Кронштадта и Выборга до современного искусства, сладкой ваты и битого стекла.',
                       gear='Sony A7C II + GM 50 1.4'),
    'Харабали': dict(place='Астраханская область', period='январь 2026',
                     intro='Отчий дом.',
                     gear='Ricoh GR IV'),
    'Узбекистан': dict(intro='Бухара, плов, который к 11 утра уже заканчивается, и лучший в жизни мильфей.'),
    'Алтай': dict(place='Республика Алтай', period='июль 2024',
                  intro='Горы, реки, красные скалы местного «Марса» и коровы, которые лежат прямо на дороге.',
                  gear='Canon R6 Mark II + RF 24-105 2.8'),
}
BEFORE = {'Питер 2024': dict(place='Санкт-Петербург', period='июль–август 2024', intro='',
                             gear='Canon R6 Mark II + RF 24-105 2.8'),
          'Узбекистан': dict(intro='Бухара как из кино, плов, который к 11 утра уже заканчивается, и лучший в жизни мильфей.')}


def forward(apps, schema_editor):
    SubCategory = apps.get_model('photos', 'SubCategory')
    for name, values in LINES.items():
        SubCategory.objects.filter(category_id=TRAVEL, name=name).update(**values)


def backward(apps, schema_editor):
    SubCategory = apps.get_model('photos', 'SubCategory')
    for name in LINES:
        old = BEFORE.get(name, {f: '' for f in FIELDS})
        SubCategory.objects.filter(category_id=TRAVEL, name=name).update(**old)


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0012_uzbekistan_text'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
