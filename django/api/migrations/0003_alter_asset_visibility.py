# Generated by Django 5.0.6 on 2024-05-20 14:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_expandedasset'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='visibility',
            field=models.CharField(choices=[('PUBLIC', 'Public'), ('PRIVATE', 'Private')], db_default='PRIVATE', default='PRIVATE', max_length=255),
        ),
    ]