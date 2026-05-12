from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icosa', '0032_assetowner_moderation_exempt'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='license',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'No license chosen'),
                    ('CREATIVE_COMMONS_BY_3_0', 'CC BY Attribution 3.0 International'),
                    ('CREATIVE_COMMONS_BY_ND_3_0', 'CC BY-ND Attribution-NoDerivatives 3.0 International'),
                    ('CREATIVE_COMMONS_BY_4_0', 'CC BY Attribution 4.0 International'),
                    ('CREATIVE_COMMONS_0', 'CC0 1.0 Universal'),
                    ('CREATIVE_COMMONS_BY_SA_4_0', 'CC BY-SA Attribution-ShareAlike 4.0 International'),
                    ('CREATIVE_COMMONS_BY_ND_4_0', 'CC BY-ND Attribution-NoDerivatives 4.0 International'),
                    ('CREATIVE_COMMONS_NC_4_0', 'CC BY-NC Attribution-NonCommercial 4.0 International'),
                    ('CREATIVE_COMMONS_NC_SA_4_0', 'CC BY-NC-SA Attribution-NonCommercial-ShareAlike 4.0 International'),
                    ('CREATIVE_COMMONS_NC_ND_4_0', 'CC BY-NC-ND Attribution-NonCommercial-NoDerivatives 4.0 International'),
                    ('ALL_RIGHTS_RESERVED', 'All rights reserved'),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
