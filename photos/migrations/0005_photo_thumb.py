from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0004_subcategory_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='photo',
            name='thumb',
            field=models.ImageField(blank=True, null=True, upload_to='thumbs/%Y/%m/', verbose_name='Превью'),
        ),
    ]
