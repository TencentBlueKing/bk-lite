from __future__ import annotations

from typing import Any

from apps.workflow_orchestration.atom_packages.http_runtime import execute_http


def execute(inputs: dict[str, Any]) -> dict[str, Any]:
    return execute_http(inputs)
