from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0005_photo_thumb'),
    ]

    operations = [
        migrations.AddField(
            model_name='photo',
            name='is_deleted',
            field=models.BooleanField(default=False, verbose_name='В корзине'),
        ),
        migrations.AddField(
            model_name='photo',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Удалено'),
        ),
    ]
