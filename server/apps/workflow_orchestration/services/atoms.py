"""编排原子的稳定入口。

所有可执行实现与契约均来自 ``atom_packages``；本模块只为编排、目录和 Worker
提供一个窄接口，不再维护第二套原子声明或 handler 实现。
"""

from __future__ import annotations

from typing import Any

from apps.workflow_orchestration.atom_packages.bklite_document_render.runtime.handler import render_document_atom
from apps.workflow_orchestration.atom_packages.bklite_http_request.runtime.handler import execute as http_atom
from apps.workflow_orchestration.atom_packages.bklite_job_execute.runtime.handler import execute as job_execute_atom
from apps.workflow_orchestration.atom_packages.bklite_notification.runtime.handler import execute as notification_atom
from apps.workflow_orchestration.services.atom_packages import (
    execute_package_atom,
    load_package_handlers,
    package_catalog_payload,
    package_task_definitions,
)
from apps.workflow_orchestration.services.system_nodes import system_node_catalog_payload

# 兼容旧导入路径：测试与视图仍从本模块取这些符号。
__all__ = [
    "ATOM_CATALOG",
    "ATOM_HANDLERS",
    "TASK_DEFINITIONS",
    "atom_catalog_payload",
    "execute_atom",
    "http_atom",
    "job_execute_atom",
    "notification_atom",
    "package_atom_task_definitions",
    "report_atom",
    "system_node_catalog_payload",
]


def atom_catalog_payload() -> list[dict[str, Any]]:
    return package_catalog_payload()


ATOM_CATALOG = {item["key"]: item for item in atom_catalog_payload()}
TASK_DEFINITIONS = package_task_definitions()
_PACKAGE_HANDLERS = load_package_handlers()
ATOM_HANDLERS = dict(_PACKAGE_HANDLERS)


def report_atom(inputs: dict[str, Any], *, store=None) -> dict[str, Any]:
    """测试与模板调用使用的文档生成薄适配器。"""
    payload = {
        **inputs,
        "data": inputs.get("data"),
    }
    return render_document_atom(payload, store=store)


def package_atom_task_definitions() -> list[dict[str, Any]]:
    """返回数据库中存在、但不属于随代码交付目录的额外研发包。"""
    from apps.workflow_orchestration.models import AtomDefinition
    from apps.workflow_orchestration.services.atom_registry import task_definition_from_catalog_item

    local_keys = set(ATOM_CATALOG)
    atoms = AtomDefinition.objects.filter(source_type=AtomDefinition.SourceType.PACKAGE).exclude(key__in=local_keys)
    return [
        task_definition_from_catalog_item(
            {
                "key": atom.key,
                "description": atom.description,
                "retry_count": atom.retry_count,
                "retry_delay_seconds": atom.retry_delay_seconds,
                "default_timeout_seconds": atom.default_timeout_seconds,
                "built_in": False,
            }
        )
        for atom in atoms
    ]


def execute_atom(task_type: str, inputs: dict[str, Any], *, retry_count: int = 0) -> dict[str, Any]:
    del retry_count
    return execute_package_atom(task_type, inputs)
