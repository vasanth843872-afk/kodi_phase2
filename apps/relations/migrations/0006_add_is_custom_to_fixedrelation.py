# Generated migration for is_custom field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('relations', '0005_fixedrelation_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='fixedrelation',
            name='is_custom',
            field=models.BooleanField(default=False, help_text='Whether this is a user-defined custom relation'),
        ),
    ]
