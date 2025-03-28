# Generated by Django 5.0.6 on 2025-03-04 14:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0107_format_is_preferred_for_download_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitlistEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('create_time', models.DateTimeField(auto_now_add=True)),
                ('update_time', models.DateTimeField(auto_now=True)),
                ('email', models.EmailField(blank=True, max_length=255, null=True)),
            ],
        ),
    ]
