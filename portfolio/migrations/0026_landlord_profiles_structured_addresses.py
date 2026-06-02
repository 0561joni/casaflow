from django.db import migrations, models
import django.db.models.deletion


def split_address(value):
    import re

    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if not lines:
        return "", "", ""
    one_line = " ".join(lines)
    match = re.match(r"^(?P<street>.*?),\s*(?P<zip>\d{4,5})\s+(?P<city>.+)$", one_line)
    if match:
        return match.group("street").strip(), match.group("zip"), match.group("city").strip()
    if len(lines) >= 2:
        match = re.match(r"^(?P<zip>\d{4,5})\s+(?P<city>.+)$", lines[1])
        if match:
            return lines[0], match.group("zip"), match.group("city").strip()
    return lines[0], "", ""


def backfill_structured_addresses_and_landlord(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    AppSettings = apps.get_model("portfolio", "AppSettings")
    LandlordProfile = apps.get_model("portfolio", "LandlordProfile")

    for property_obj in Property.objects.all():
        if property_obj.street_address or property_obj.postal_code or property_obj.city:
            continue
        street, postal_code, city = split_address(property_obj.address)
        property_obj.street_address = street
        property_obj.postal_code = postal_code
        property_obj.city = city
        property_obj.save(update_fields=["street_address", "postal_code", "city"])

    app_settings = AppSettings.objects.filter(pk=1).first()
    if app_settings and app_settings.landlord_name and not LandlordProfile.objects.exists():
        LandlordProfile.objects.create(
            name=app_settings.landlord_name,
            street_address=app_settings.landlord_street,
            postal_code=app_settings.landlord_zip,
            city=app_settings.landlord_city,
            phone=app_settings.landlord_phone,
            fax=app_settings.landlord_fax,
            email=app_settings.landlord_email,
            is_default=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0025_mietbescheinigung_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="LandlordProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("street_address", models.CharField(max_length=200)),
                ("postal_code", models.CharField(blank=True, max_length=20)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=80)),
                ("fax", models.CharField(blank=True, max_length=80)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("signature_image", models.FileField(blank=True, upload_to="landlord_signatures/")),
                ("is_default", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["-is_default", "name"],
            },
        ),
        migrations.AddField(
            model_name="property",
            name="city",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="property",
            name="postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="property",
            name="street_address",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddConstraint(
            model_name="landlordprofile",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("is_default",), name="unique_default_landlord_profile"),
        ),
        migrations.RunPython(backfill_structured_addresses_and_landlord, migrations.RunPython.noop),
    ]
