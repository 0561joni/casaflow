from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0014_tenant_support_office_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="photo",
            field=models.FileField(blank=True, upload_to="property_photos/"),
        ),
    ]
