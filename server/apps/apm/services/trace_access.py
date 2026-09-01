from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from apps.apm.models import ApmService, ApmServiceInstance
from apps.apm.services.contracts import SpanSummary, TraceDetail, TraceSummary
from apps.apm.services.identity import normalize_identity

T = TypeVar("T")
_MAX_VISIBILITY_FETCHES = 8


@dataclass(frozen=True)
class _TraceIdentity:
    service_namespace: str
    service_name: str
    instance_id: str | None


def collect_visible_page(
    *,
    fetch_page: Callable[[str | None], tuple[Sequence[T], str | None]],
    filter_items: Callable[[Sequence[T]], Sequence[T]],
    cursor: str | None,
    limit: int,
    encode_cursor: Callable[[T], str],
    max_fetches: int = _MAX_VISIBILITY_FETCHES,
) -> tuple[tuple[T, ...], str | None]:
    """先做组织可见性过滤，再计算 next_cursor，避免 VT 页游标越过隐藏行后漏掉可见行。"""

    collected: list[T] = []
    current = cursor
    next_store_cursor: str | None = None
    for _ in range(max_fetches):
        items, next_store_cursor = fetch_page(current)
        for item in filter_items(items):
            collected.append(item)
            if len(collected) > limit:
                return tuple(collected[:limit]), encode_cursor(collected[limit - 1])
        if next_store_cursor is None:
            return tuple(collected), None
        if len(collected) >= limit:
            return tuple(collected[:limit]), next_store_cursor
        current = next_store_cursor
    return tuple(collected[:limit]), next_store_cursor


class TraceAccessResolver:
    """把遥测身份解析为控制面组织权限，不把组织标签写入 Trace Store。"""

    def filter_summaries(
        self,
        summaries: Iterable[TraceSummary],
        organization_ids: Sequence[int],
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
            organization_ids,
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
        organization_ids: Sequence[int],
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
            organization_ids,
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

    def can_view_detail(self, detail: TraceDetail, organization_ids: Sequence[int]) -> bool:
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
        allowed_instances, allowed_services = self._allowed_identities(identities, organization_ids)
        return any(self._is_allowed(item, allowed_instances, allowed_services) for item in identities)

    @staticmethod
    def _allowed_identities(
        identities: Iterable[_TraceIdentity],
        organization_ids: Sequence[int],
    ) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
        items = tuple(identities)
        allowed_ids = {int(organization_id) for organization_id in organization_ids}
        if not allowed_ids:
            return set(), set()
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
                organization_links__organization__in=allowed_ids,
            )
        }
        service_names_without_instance = {normalize_identity(item.service_name) for item in items if item.instance_id is None}
        allowed_services = {
            (service.normalized_namespace, service.normalized_name)
            for service in ApmService.objects.filter(
                normalized_name__in=service_names_without_instance,
                organization_links__organization__in=allowed_ids,
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
