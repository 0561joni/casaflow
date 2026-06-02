from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0013_backfill_property_purchase_value_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="support_office_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="financial support office email"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="support_office_name",
            field=models.CharField(blank=True, max_length=160, verbose_name="financial support office name"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="support_office_phone",
            field=models.CharField(blank=True, max_length=80, verbose_name="financial support office phone"),
        ),
    ]
