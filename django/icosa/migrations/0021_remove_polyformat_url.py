# Generated by Django 5.0.6 on 2024-07-04 16:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0020_polyformat_polyresource'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='polyformat',
            name='url',
        ),
    ]
