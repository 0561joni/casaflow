from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0026_landlord_profiles_structured_addresses"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="language_code",
            field=models.CharField(
                choices=[("en", "English"), ("de", "Deutsch")],
                default="en",
                max_length=8,
            ),
        ),
    ]
