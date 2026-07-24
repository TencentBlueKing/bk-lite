from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.models.share_models import DashboardShareLink


def _invalidate_dashboard_links(dashboard_id):
    DashboardShareLink.objects.filter(
        dashboard_instance_id=dashboard_id,
        status=DashboardShareLink.Status.ACTIVE,
    ).update(
        status=DashboardShareLink.Status.DASHBOARD_INVALID,
        invalidated_at=timezone.now(),
        invalidated_by="system",
        invalidation_reason=DashboardShareLink.Status.DASHBOARD_INVALID,
        updated_at=timezone.now(),
    )


@receiver(pre_delete, sender=Dashboard)
def invalidate_dashboard_shares_before_delete(sender, instance, **kwargs):
    _invalidate_dashboard_links(instance.pk)


@receiver(pre_save, sender=Dashboard)
def invalidate_dashboard_shares_before_move(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = Dashboard.objects.filter(pk=instance.pk).values("directory_id", "groups", "domain").first()
    if previous is None:
        return
    if (
        previous["directory_id"] != instance.directory_id
        or previous["groups"] != instance.groups
        or previous["domain"] != instance.domain
    ):
        _invalidate_dashboard_links(instance.pk)

