from django.db import migrations, models
from django.db.models import Count


def ensure_active_links_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    DashboardShareLink = apps.get_model("operation_analysis", "DashboardShareLink")
    links = DashboardShareLink.objects.using(alias)
    duplicate = (
        links.filter(status="active")
        .values("resource_type", "dashboard_instance_id", "sharer_username", "sharer_domain")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("resource_type", "dashboard_instance_id", "sharer_username", "sharer_domain")
        .first()
    )
    if duplicate is not None:
        raise RuntimeError("存在重复的有效画布分享链接，请先完成业务核对再迁移")


def populate_active_guard(apps, schema_editor):
    alias = schema_editor.connection.alias
    DashboardShareLink = apps.get_model("operation_analysis", "DashboardShareLink")
    links = DashboardShareLink.objects.using(alias)
    links.filter(status="active").update(active_guard=True)


def clear_active_guard(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model("operation_analysis", "DashboardShareLink").objects.using(alias).update(active_guard=None)


class Migration(migrations.Migration):
    dependencies = [("operation_analysis", "0022_prometheus_source_type")]

    operations = [
        migrations.RunPython(ensure_active_links_unique, migrations.RunPython.noop),
        migrations.AddField(
            model_name="dashboardsharelink",
            name="active_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.RunPython(populate_active_guard, clear_active_guard),
        migrations.AddConstraint(
            model_name="dashboardsharelink",
            constraint=models.UniqueConstraint(
                fields=(
                    "resource_type",
                    "dashboard_instance_id",
                    "sharer_username",
                    "sharer_domain",
                    "active_guard",
                ),
                name="uniq_active_canvas_share_guard",
            ),
        ),
    ]
