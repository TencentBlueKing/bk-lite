from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from apps.apm.models import ApmService, ApmServiceInstance
from apps.apm.services.contracts import SpanSummary, TraceDetail, TraceSummary
from apps.apm.services.identity import normalize_identity


@dataclass(frozen=True)
class _TraceIdentity:
    service_namespace: str
    service_name: str
    instance_id: str | None


class TraceAccessResolver:
    """把遥测身份解析为控制面组织权限，不把组织标签写入 Trace Store。"""

    def filter_summaries(
        self,
        summaries: Iterable[TraceSummary],
        organization_id: int,
    ) -> tuple[TraceSummary, ...]:
        items = tuple(summaries)
        allowed_instances, allowed_services = self._allowed_identities(
            (
                _TraceIdentity(
                    item.service_namespace,
                    item.service_name,
                    item.instance_id,
                )
                for item in items
            ),
            organization_id,
        )
        return tuple(
            item
            for item in items
            if self._is_allowed(
                _TraceIdentity(
                    item.service_namespace,
                    item.service_name,
                    item.instance_id,
                ),
                allowed_instances,
                allowed_services,
            )
        )

    def filter_span_summaries(
        self,
        summaries: Iterable[SpanSummary],
        organization_id: int,
    ) -> tuple[SpanSummary, ...]:
        items = tuple(summaries)
        allowed_instances, allowed_services = self._allowed_identities(
            (
                _TraceIdentity(
                    item.service_namespace,
                    item.service_name,
                    item.instance_id,
                )
                for item in items
            ),
            organization_id,
        )
        return tuple(
            item
            for item in items
            if self._is_allowed(
                _TraceIdentity(
                    item.service_namespace,
                    item.service_name,
                    item.instance_id,
                ),
                allowed_instances,
                allowed_services,
            )
        )

    def can_view_detail(self, detail: TraceDetail, organization_id: int) -> bool:
        identities = tuple(
            _TraceIdentity(
                span.service_namespace,
                span.service_name,
                span.instance_id,
            )
            for span in detail.spans
        ) or (
            _TraceIdentity(
                detail.service_namespace,
                detail.service_name,
                detail.instance_id,
            ),
        )
        allowed_instances, allowed_services = self._allowed_identities(identities, organization_id)
        return any(self._is_allowed(item, allowed_instances, allowed_services) for item in identities)

    @staticmethod
    def _allowed_identities(
        identities: Iterable[_TraceIdentity],
        organization_id: int,
    ) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
        items = tuple(identities)
        service_names = {normalize_identity(item.service_name) for item in items if item.instance_id}
        instance_ids = {normalize_identity(item.instance_id) for item in items if item.instance_id}
        allowed_instances = {
            (
                instance.service.normalized_namespace,
                instance.service.normalized_name,
                instance.normalized_instance_id,
            )
            for instance in ApmServiceInstance.objects.select_related("service").filter(
                service__normalized_name__in=service_names,
                normalized_instance_id__in=instance_ids,
                organization_links__organization=organization_id,
            )
        }
        service_names_without_instance = {
            normalize_identity(item.service_name) for item in items if item.instance_id is None
        }
        allowed_services = {
            (service.normalized_namespace, service.normalized_name)
            for service in ApmService.objects.filter(
                normalized_name__in=service_names_without_instance,
                organization_links__organization=organization_id,
            )
        }
        return allowed_instances, allowed_services

    @staticmethod
    def _is_allowed(
        identity: _TraceIdentity,
        allowed_instances: set[tuple[str, str, str]],
        allowed_services: set[tuple[str, str]],
    ) -> bool:
        if identity.instance_id:
            return (
                normalize_identity(identity.service_namespace),
                normalize_identity(identity.service_name),
                normalize_identity(identity.instance_id),
            ) in allowed_instances
        return (
            normalize_identity(identity.service_namespace),
            normalize_identity(identity.service_name),
        ) in allowed_services
