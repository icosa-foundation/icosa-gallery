# Generated by Django 5.0.6 on 2024-09-05 14:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0054_asset_likes_asset_views'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='imported',
            field=models.BooleanField(default=False),
        ),
    ]
