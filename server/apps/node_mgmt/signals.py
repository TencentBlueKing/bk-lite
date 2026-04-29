from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.node_mgmt.models.sidecar import Action, ChildConfig, CollectorConfiguration
from apps.node_mgmt.services.sidecar_cache import (
    invalidate_action_node_etag,
    invalidate_assignment_node_etags,
    invalidate_child_config_etag,
    invalidate_collector_configuration_related_etags,
    invalidate_collector_configuration_node_etags,
)


@receiver(m2m_changed, sender=CollectorConfiguration.nodes.through)
def invalidate_node_assignment_etags(sender, instance, action, reverse, pk_set, **kwargs):
    invalidate_assignment_node_etags(action, reverse, instance, pk_set)


@receiver([post_save, post_delete], sender=Action)
def invalidate_action_etag(sender, instance, **kwargs):
    invalidate_action_node_etag(instance)


@receiver([post_save, post_delete], sender=ChildConfig)
def invalidate_child_config_render_etag(sender, instance, **kwargs):
    invalidate_child_config_etag(instance)


@receiver([post_save, post_delete], sender=CollectorConfiguration)
def invalidate_configuration_render_etag(sender, instance, **kwargs):
    invalidate_collector_configuration_related_etags(instance)


@receiver(pre_delete, sender=CollectorConfiguration)
def invalidate_deleted_configuration_node_etags(sender, instance, **kwargs):
    invalidate_collector_configuration_node_etags(instance)
