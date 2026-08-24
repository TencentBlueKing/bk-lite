from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta

from apps.apm.services.contracts import InferredDeploymentRelease

_VERSION_PART = re.compile(r"\d+")


def _version_rank(version: str) -> tuple[int, ...]:
    parts = [int(part) for part in _VERSION_PART.findall(version)]
    return tuple(parts) if parts else (0,)


def annotate_inferred_deployment_status(
    releases: list[InferredDeploymentRelease],
    *,
    observed_at: datetime,
    rolling_window: timedelta = timedelta(minutes=30),
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
                status = "rollback"
            elif (
                index == len(group) - 1
                and previous is not None
                and current.first_seen_at >= observed_at - rolling_window
                and previous.last_seen_at >= current.first_seen_at - rolling_window
            ):
                status = "in_progress"
            else:
                status = "success"
            annotated.append((current, status))
    return annotated
