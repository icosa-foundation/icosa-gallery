# Generated by Django 5.0.6 on 2024-06-12 13:03

from django.db import migrations


def forwards(apps, schema_editor):
    Asset = apps.get_model("icosa", "Asset")
    assets = Asset.objects.all()
    assets.update(orienting_rotation=[0, 0, 0, 0])


def backwards(apps, schema_editor):
    Asset = apps.get_model("icosa", "Asset")
    assets = Asset.objects.all()
    assets.update(orienting_rotation="[0,0,0,0]")


class Migration(migrations.Migration):
    dependencies = [
        ("icosa", "0003_asset_background_color_asset_color_space_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
