# Generated by Django 5.0.6 on 2025-01-20 14:57

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0088_rename_user_assetowner'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='UserAssetLike',
            new_name='OwnerAssetLike',
        ),
    ]
