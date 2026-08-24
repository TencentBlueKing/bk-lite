from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import ApmDeploymentEvent, ApmService
from apps.apm.services.contracts import DeploymentReleaseQuery, InferredDeploymentRelease, MetricStore
from apps.apm.services.identity import normalize_identity

_VERSION_PART = re.compile(r"\d+")
ROLLING_WINDOW = timedelta(minutes=30)
INFERRED_RETENTION = timedelta(days=90)
BACKFILL_LOOKBACK = timedelta(days=7)
MAX_SILENT_CONVERGE = 500


def _version_rank(version: str) -> tuple[int, ...]:
    parts = [int(part) for part in _VERSION_PART.findall(version)]
    return tuple(parts) if parts else (0,)


def annotate_inferred_deployment_status(
    releases: list[InferredDeploymentRelease],
    *,
    observed_at: datetime,
    rolling_window: timedelta = ROLLING_WINDOW,
) -> list[tuple[InferredDeploymentRelease, str]]:
    """按 service.version 首次出现推断发布状态。"""
    grouped: dict[tuple[str, str, str], list[InferredDeploymentRelease]] = defaultdict(list)
    for release in releases:
        grouped[(release.service_namespace, release.service_name, release.environment)].append(release)

    annotated: list[tuple[InferredDeploymentRelease, str]] = []
    for group in grouped.values():
        group.sort(key=lambda item: item.first_seen_at)
        for index, current in enumerate(group):
            previous = group[index - 1] if index > 0 else None
            if previous and _version_rank(current.version) < _version_rank(previous.version):
                status = ApmDeploymentEvent.Status.ROLLBACK
            elif (
                index == len(group) - 1
                and previous is not None
                and current.first_seen_at >= observed_at - rolling_window
                and previous.last_seen_at >= current.first_seen_at - rolling_window
            ):
                status = ApmDeploymentEvent.Status.IN_PROGRESS
            else:
                status = ApmDeploymentEvent.Status.SUCCESS
            annotated.append((current, status))
    return annotated


@dataclass(frozen=True)
class ObservedVersion:
    service: ApmService
    environment: str
    version: str
    last_seen_at: datetime


@dataclass(frozen=True)
class DeploymentRecordResult:
    created: int = 0
    updated: int = 0
    pruned: int = 0


class DeploymentEventRecorder:
    """把近窗遥测 version 变化增量写入部署事件表。"""

    def __init__(self, *, rolling_window: timedelta = ROLLING_WINDOW, retention: timedelta = INFERRED_RETENTION):
        self.rolling_window = rolling_window
        self.retention = retention

    def record(self, observations: Sequence[ObservedVersion], *, observed_at: datetime) -> DeploymentRecordResult:
        created = 0
        updated = 0
        grouped: dict[tuple[UUID, str], list[ObservedVersion]] = defaultdict(list)
        for observation in observations:
            version = normalize_identity(observation.version)
            if not version:
                continue
            environment = normalize_identity(observation.environment)
            grouped[(observation.service.id, environment)].append(
                ObservedVersion(
                    service=observation.service,
                    environment=environment,
                    version=version,
                    last_seen_at=observation.last_seen_at,
                )
            )
        for items in grouped.values():
            created_count, updated_count = self._record_group(items, observed_at=observed_at)
            created += created_count
            updated += updated_count
        updated += self._converge_silent_in_progress(observed_keys=set(grouped), observed_at=observed_at)
        pruned = self._prune(observed_at)
        return DeploymentRecordResult(created=created, updated=updated, pruned=pruned)

    def _record_group(self, items: list[ObservedVersion], *, observed_at: datetime) -> tuple[int, int]:
        service = items[0].service
        environment = items[0].environment
        version_times = _version_windows(items)
        versions_present = set(version_times)
        with transaction.atomic():
            latest = (
                ApmDeploymentEvent.objects.select_for_update()
                .filter(service=service, environment=environment)
                .order_by("-deployed_at", "-id")
                .first()
            )
            if latest is None:
                return self._bootstrap(service, environment, version_times), 0
            if latest.version not in versions_present:
                incoming = self._incoming_version(latest, versions_present, version_times)
                if incoming is not None:
                    status, version = incoming
                    self._create_event(service, environment, version, version_times[version][0], status)
                    return 1, 0
                if latest.source != ApmDeploymentEvent.Source.INFERRED:
                    return 0, 0
                return 0, self._converge_latest(latest, versions_present, observed_at)
            newer = self._newer_or_peer_versions(latest.version, versions_present)
            if newer:
                version = max(newer, key=lambda item: (_version_rank(item), version_times[item][1], item))
                self._create_event(
                    service,
                    environment,
                    version,
                    version_times[version][0],
                    ApmDeploymentEvent.Status.IN_PROGRESS,
                )
                return 1, 0
            if latest.source != ApmDeploymentEvent.Source.INFERRED:
                return 0, 0
            return 0, self._converge_latest(latest, versions_present, observed_at)

    def _bootstrap(
        self,
        service: ApmService,
        environment: str,
        version_times: dict[str, tuple[datetime, datetime]],
    ) -> int:
        ordered = sorted(version_times, key=lambda version: (_version_rank(version), version_times[version][0], version))
        created = 0
        for index, version in enumerate(ordered):
            status = (
                ApmDeploymentEvent.Status.IN_PROGRESS
                if index == len(ordered) - 1 and len(ordered) > 1
                else ApmDeploymentEvent.Status.SUCCESS
            )
            self._create_event(service, environment, version, version_times[version][0], status)
            created += 1
        return created

    def _incoming_version(
        self,
        latest: ApmDeploymentEvent,
        versions_present: set[str],
        version_times: dict[str, tuple[datetime, datetime]],
    ) -> tuple[str, str] | None:
        others = [version for version in versions_present if version != latest.version]
        if not others:
            return None
        incoming = max(others, key=lambda version: (version_times[version][1], _version_rank(version), version))
        if _version_rank(incoming) < _version_rank(latest.version):
            return ApmDeploymentEvent.Status.ROLLBACK, incoming
        return ApmDeploymentEvent.Status.SUCCESS, incoming

    @staticmethod
    def _newer_or_peer_versions(latest_version: str, versions_present: set[str]) -> list[str]:
        latest_rank = _version_rank(latest_version)
        return [
            version
            for version in versions_present
            if version != latest_version and _version_rank(version) >= latest_rank
        ]

    def _converge_latest(self, latest: ApmDeploymentEvent, versions_present: set[str], observed_at: datetime) -> int:
        if latest.status != ApmDeploymentEvent.Status.IN_PROGRESS:
            return 0
        if latest.source != ApmDeploymentEvent.Source.INFERRED:
            return 0
        only_latest = versions_present == {latest.version}
        timed_out = latest.deployed_at <= observed_at - self.rolling_window
        if only_latest or (not versions_present and timed_out):
            latest.status = ApmDeploymentEvent.Status.SUCCESS
            latest.save(update_fields=("status", "updated_at"))
            return 1
        return 0

    def _converge_silent_in_progress(
        self,
        *,
        observed_keys: set[tuple[UUID, str]],
        observed_at: datetime,
    ) -> int:
        updated = 0
        cutoff = observed_at - self.rolling_window
        silent = list(
            ApmDeploymentEvent.objects.filter(
                source=ApmDeploymentEvent.Source.INFERRED,
                status=ApmDeploymentEvent.Status.IN_PROGRESS,
                deployed_at__lte=cutoff,
            ).order_by("service_id", "environment", "-deployed_at", "-id")[:MAX_SILENT_CONVERGE]
        )
        seen: set[tuple[UUID, str]] = set()
        for event in silent:
            key = (event.service_id, event.environment)
            if key in seen or key in observed_keys:
                continue
            seen.add(key)
            with transaction.atomic():
                latest = (
                    ApmDeploymentEvent.objects.select_for_update()
                    .filter(service_id=event.service_id, environment=event.environment)
                    .order_by("-deployed_at", "-id")
                    .first()
                )
                if (
                    latest is None
                    or latest.id != event.id
                    or latest.source != ApmDeploymentEvent.Source.INFERRED
                    or latest.status != ApmDeploymentEvent.Status.IN_PROGRESS
                ):
                    continue
                latest.status = ApmDeploymentEvent.Status.SUCCESS
                latest.save(update_fields=("status", "updated_at"))
                updated += 1
        return updated

    @staticmethod
    def _create_event(service: ApmService, environment: str, version: str, deployed_at: datetime, status: str) -> ApmDeploymentEvent:
        return ApmDeploymentEvent.objects.create(
            service=service,
            environment=environment,
            version=version,
            deployed_at=deployed_at,
            status=status,
            source=ApmDeploymentEvent.Source.INFERRED,
        )

    def _prune(self, observed_at: datetime) -> int:
        deleted, _ = ApmDeploymentEvent.objects.filter(
            source=ApmDeploymentEvent.Source.INFERRED,
            deployed_at__lt=observed_at - self.retention,
        ).delete()
        return deleted


def _version_windows(items: Iterable[ObservedVersion]) -> dict[str, tuple[datetime, datetime]]:
    windows: dict[str, tuple[datetime, datetime]] = {}
    for item in items:
        previous = windows.get(item.version)
        if previous is None:
            windows[item.version] = (item.last_seen_at, item.last_seen_at)
            continue
        first_seen, last_seen = previous
        windows[item.version] = (min(first_seen, item.last_seen_at), max(last_seen, item.last_seen_at))
    return windows


def backfill_inferred_deployment_events(
    metric_store: MetricStore,
    *,
    observed_at: datetime | None = None,
    lookback: timedelta = BACKFILL_LOOKBACK,
) -> DeploymentRecordResult:
    ended_at = observed_at or timezone.now()
    releases = metric_store.deployment_releases(DeploymentReleaseQuery(started_at=ended_at - lookback, ended_at=ended_at))
    annotated = annotate_inferred_deployment_status(releases, observed_at=ended_at)
    created = 0
    updated = 0
    for release, status in annotated:
        namespace = normalize_identity(release.service_namespace)
        name = normalize_identity(release.service_name)
        environment = normalize_identity(release.environment)
        version = normalize_identity(release.version)
        if not name or not version:
            continue
        service = ApmService.objects.filter(normalized_namespace=namespace, normalized_name=name).first()
        if service is None:
            continue
        with transaction.atomic():
            existing = (
                ApmDeploymentEvent.objects.select_for_update()
                .filter(
                    service=service,
                    environment=environment,
                    version=version,
                    source=ApmDeploymentEvent.Source.INFERRED,
                )
                .order_by("deployed_at", "id")
                .first()
            )
            if existing is None:
                ApmDeploymentEvent.objects.create(
                    service=service,
                    environment=environment,
                    version=version,
                    deployed_at=release.first_seen_at,
                    status=status,
                    source=ApmDeploymentEvent.Source.INFERRED,
                )
                created += 1
                continue
            if release.first_seen_at < existing.deployed_at:
                existing.deployed_at = release.first_seen_at
                existing.save(update_fields=("deployed_at", "updated_at"))
                updated += 1
    return DeploymentRecordResult(created=created, updated=updated)
