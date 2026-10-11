from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0002_category_cover'),
    ]

    operations = [
        migrations.AddField(
            model_name='subcategory',
            name='hidden',
            field=models.BooleanField(default=False, verbose_name='Скрыть от посетителей (тестовая)'),
        ),
    ]
