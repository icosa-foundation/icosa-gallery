# Generated by Django 5.0.6 on 2024-12-11 09:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0082_asset_preview_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='triangle_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
