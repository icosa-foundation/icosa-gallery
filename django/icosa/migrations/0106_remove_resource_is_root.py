# Generated by Django 5.0.6 on 2025-02-20 11:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0105_alter_resource_format'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='resource',
            name='is_root',
        ),
    ]
