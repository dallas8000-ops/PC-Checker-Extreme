from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diagnostics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanreport",
            name="scan_progress",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="scanreport",
            name="scan_stage",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
