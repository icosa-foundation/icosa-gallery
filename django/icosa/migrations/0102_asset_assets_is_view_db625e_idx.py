# Generated by Django 5.0.6 on 2025-02-11 09:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0101_asset_assets_owner_i_b9eeda_idx'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['is_viewer_compatible', 'last_reported_time', 'visibility', 'license'], name='assets_is_view_db625e_idx'),
        ),
    ]
