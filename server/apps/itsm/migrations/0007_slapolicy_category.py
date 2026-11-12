from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("itsm", "0006_datatable_tickettag_ticketrelation_ticketcomment_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="slapolicy",
            name="category",
            field=models.CharField(default="sla", max_length=16),
        ),
    ]
