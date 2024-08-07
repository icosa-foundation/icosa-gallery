# Generated by Django 5.0.6 on 2024-07-08 15:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0023_delete_icosaformat'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrientingRotation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('x', models.FloatField(blank=True, null=True)),
                ('y', models.FloatField(blank=True, null=True)),
                ('z', models.FloatField(blank=True, null=True)),
                ('w', models.FloatField(blank=True, null=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='asset',
            name='background_color',
        ),
        migrations.RemoveField(
            model_name='asset',
            name='color_space',
        ),
        migrations.RemoveField(
            model_name='asset',
            name='orienting_rotation',
        ),
        migrations.CreateModel(
            name='PresentationParams',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('color_space', models.CharField(choices=[('LINEAR', 'LINEAR'), ('GAMMA', 'GAMMA')], default='GAMMA', max_length=50)),
                ('background_color', models.CharField(blank=True, max_length=7, null=True)),
                ('orienting_rotation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='icosa.orientingrotation')),
            ],
        ),
        migrations.AddField(
            model_name='asset',
            name='presentation_params',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='icosa.presentationparams'),
        ),
    ]
