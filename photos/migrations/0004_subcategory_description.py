from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0003_subcategory_hidden'),
    ]

    operations = [
        migrations.AddField(
            model_name='subcategory',
            name='description',
            field=models.TextField(blank=True, default='', verbose_name='Описание (показывается под названием альбома)'),
        ),
    ]
