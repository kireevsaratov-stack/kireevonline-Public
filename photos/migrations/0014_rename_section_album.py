"""Понятные имена (08.10.2026): «категория» → раздел (Section), «подкатегория» → альбом (Album).
Переименовываются таблицы и столбцы, данные не меняются. Обратимо: откат вернёт прежние имена."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0013_travel_lines'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RenameModel('Category', 'Section'),
        migrations.RenameModel('SubCategory', 'Album'),
        migrations.RenameField('album', 'category', 'section'),
        migrations.RenameField('photo', 'category', 'section'),
        migrations.RenameField('photo', 'subcategory', 'album'),
            # подписи в админке и имена обратных связей
        migrations.AlterModelOptions('album', options={'ordering': ['order', 'name'], 'verbose_name': 'Альбом',
                                                       'verbose_name_plural': 'Альбомы'}),
        migrations.AlterModelOptions('section', options={'ordering': ['order', 'name'], 'verbose_name': 'Раздел',
                                                         'verbose_name_plural': 'Разделы'}),
        migrations.AlterField('album', 'cover', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cover_for_album',
            to='photos.photo', verbose_name='Обложка')),
        migrations.AlterField('album', 'section', models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, related_name='albums', to='photos.section',
            verbose_name='Раздел')),
        migrations.AlterField('photo', 'album', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='photos',
            to='photos.album', verbose_name='Альбом')),
        migrations.AlterField('photo', 'section', models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='photos.section',
            verbose_name='Раздел')),
        migrations.AlterField('section', 'cover', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cover_for_section',
            to='photos.photo', verbose_name='Обложка')),
    ]
