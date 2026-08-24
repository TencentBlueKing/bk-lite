"""Execute transform(rows, params) under import whitelist constraints."""

from __future__ import annotations

import json
import os
from typing import Any

from app.script_guard import ALLOWED_IMPORT_MODULES, ScriptValidationError, validate_script_ast

MAX_ROWS = 10_000
# Soft serialization budget for a single payload direction (bytes of JSON text).
MAX_PAYLOAD_BYTES = max(1, int(os.getenv("TRANSFORM_MAX_PAYLOAD_BYTES", str(8 * 1024 * 1024))))


class TransformRuntimeError(Exception):
    def __init__(self, message: str, *, code: str = "transform_failed"):
        super().__init__(message)
        self.code = code


def _measure_payload_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _whitelisted_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
    root = str(name or "").split(".", 1)[0]
    if root not in ALLOWED_IMPORT_MODULES:
        raise ImportError(f"不允许导入模块: {name}")
    return __import__(name, globals, locals, fromlist, level)


def execute_transform(script: str, rows: list[Any], params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise TransformRuntimeError("rows 必须为数组", code="rows_invalid")
    if len(rows) > MAX_ROWS:
        raise TransformRuntimeError(f"输入超过 {MAX_ROWS} 行", code="rows_too_many")
    if _measure_payload_bytes(rows) > MAX_PAYLOAD_BYTES:
        raise TransformRuntimeError("输入序列化体积过大", code="rows_payload_too_large")

    params = params if isinstance(params, dict) else {}
    validate_script_ast(script)

    safe_builtins = {
        "__import__": _whitelisted_import,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }

    namespace: dict[str, Any] = {"__builtins__": safe_builtins}
    try:
        exec(compile(script, "<transform>", "exec"), namespace, namespace)  # noqa: S102
    except ScriptValidationError:
        raise
    except Exception as exc:
        raise TransformRuntimeError(f"脚本执行失败: {exc}", code="script_runtime_error") from exc

    transform_fn = namespace.get("transform")
    if not callable(transform_fn):
        raise TransformRuntimeError("脚本必须定义 transform(rows, params)", code="transform_missing")

    try:
        result = transform_fn(rows, params)
    except Exception as exc:
        raise TransformRuntimeError(f"transform 调用失败: {exc}", code="transform_call_failed") from exc

    if not isinstance(result, list):
        raise TransformRuntimeError("transform 必须返回 list", code="transform_return_invalid")
    if len(result) > MAX_ROWS:
        raise TransformRuntimeError(f"输出超过 {MAX_ROWS} 行", code="output_too_many")
    if _measure_payload_bytes(result) > MAX_PAYLOAD_BYTES:
        raise TransformRuntimeError("输出序列化体积过大", code="output_payload_too_large")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(result):
        if not isinstance(item, dict):
            raise TransformRuntimeError(
                f"transform 返回第 {index} 项不是对象",
                code="transform_return_invalid",
            )
        normalized.append(item)
    return normalized
