from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0053_user_profile_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("key", models.CharField(max_length=64)),
                ("value", models.CharField(max_length=64)),
            ],
            options={
                "ordering": ("id",),
            },
        ),
        migrations.AddConstraint(
            model_name="notificationtag",
            constraint=models.UniqueConstraint(fields=("key", "value"), name="uniq_notification_tag_key_value"),
        ),
        migrations.AddField(
            model_name="channel",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="channels", to="system_mgmt.notificationtag"),
        ),
        migrations.AddField(
            model_name="imnotificationchannel",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="im_notification_channels", to="system_mgmt.notificationtag"),
        ),
    ]
