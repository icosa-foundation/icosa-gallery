# Generated by Django 5.0.6 on 2025-03-31 12:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0114_rename_archive_url_format_zip_archive_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='preferred_viewer_format_override',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='preferred_format_override_for', to='icosa.format'),
        ),
    ]
