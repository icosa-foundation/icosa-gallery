# Generated by Django 5.0.6 on 2025-02-20 11:48

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0104_rename_assets_is_view_1962a9_idx_icosa_asset_is_view_0ae61f_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='resource',
            name='format',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='icosa.format'),
        ),
    ]
