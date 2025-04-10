# Generated by Django 5.0.6 on 2025-04-07 11:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0115_asset_preferred_viewer_format_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetowner',
            name='disable_profile',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='asset',
            name='visibility',
            field=models.CharField(choices=[('PUBLIC', 'Public'), ('PRIVATE', 'Private'), ('UNLISTED', 'Unlisted'), ('ARCHIVED', 'ARCHIVED')], db_default='PRIVATE', default='PRIVATE', max_length=255),
        ),
    ]
