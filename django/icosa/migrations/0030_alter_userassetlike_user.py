# Generated by Django 5.0.6 on 2024-07-15 11:16

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0029_alter_user_displayname'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userassetlike',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liker', to='icosa.user'),
        ),
    ]