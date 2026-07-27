from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY

_CANVAS_MODELS = (Dashboard, Topology, Architecture, Screen, Report, NetworkTopology)
_MODEL_TO_RESOURCE_TYPE = {
    meta.model: object_type for object_type, meta in CANVAS_TYPE_REGISTRY.items()
}


def _invalidate_resource_links(resource_type, resource_id):
    DashboardShareLink.objects.filter(
        resource_type=resource_type,
        dashboard_instance_id=resource_id,
        status=DashboardShareLink.Status.ACTIVE,
    ).update(
        status=DashboardShareLink.Status.DASHBOARD_INVALID,
        invalidated_at=timezone.now(),
        invalidated_by="system",
        invalidation_reason=DashboardShareLink.Status.DASHBOARD_INVALID,
        updated_at=timezone.now(),
    )


def _register_canvas_share_signals():
    for model in _CANVAS_MODELS:
        resource_type = _MODEL_TO_RESOURCE_TYPE[model]

        def make_delete_handler(rt):
            def handler(sender, instance, **kwargs):
                _invalidate_resource_links(rt, instance.pk)

            return handler

        def make_move_handler(rt, model_cls):
            def handler(sender, instance, **kwargs):
                if not instance.pk:
                    return
                previous = model_cls.objects.filter(pk=instance.pk).values("groups", "domain").first()
                if previous is None:
                    return
                if previous["groups"] != instance.groups or previous["domain"] != instance.domain:
                    _invalidate_resource_links(rt, instance.pk)

            return handler

        pre_delete.connect(
            make_delete_handler(resource_type),
            sender=model,
            weak=False,
            dispatch_uid=f"canvas_share_invalidate_delete_{resource_type}",
        )
        pre_save.connect(
            make_move_handler(resource_type, model),
            sender=model,
            weak=False,
            dispatch_uid=f"canvas_share_invalidate_move_{resource_type}",
        )


_register_canvas_share_signals()
