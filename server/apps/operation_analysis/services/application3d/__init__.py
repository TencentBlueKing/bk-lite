"""application3D domain package for ops-analysis Scene Widget."""

from __future__ import annotations

__all__ = ["Application3DQueryService"]


def __getattr__(name: str):
    if name == "Application3DQueryService":
        from apps.operation_analysis.services.application3d.query_service import Application3DQueryService

        return Application3DQueryService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
