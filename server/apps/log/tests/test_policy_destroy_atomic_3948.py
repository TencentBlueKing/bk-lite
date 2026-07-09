"""
Issue #3948: PolicyViewSet.destroy 先删 PeriodicTask 再删 Policy，分步写在 DB 异常时产生孤儿策略

验证 PolicyViewSet.destroy 的两步写在同一个 transaction.atomic() 中：
- PeriodicTask.objects.filter(name=f"log_policy_task_{policy_id}").delete() 与 super().destroy()
  必须被同一个 `with transaction.atomic():` 块包裹。
- 缺失该 atomic 包裹时（即现状），本测试失败；加上后，本测试通过。

采用 AST 静态分析的方式，不依赖 Django/DB 启动，可在任意环境跑通：
    uv run pytest server/apps/log/tests/test_policy_destroy_atomic_3948.py -v
"""
import ast
from pathlib import Path

import pytest


POLICY_PY = Path(__file__).resolve().parents[1] / "views" / "policy.py"


def _get_destroy_function_node(module: ast.Module) -> ast.FunctionDef:
    """从模块 AST 中定位 PolicyViewSet.destroy 方法。"""
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == "PolicyViewSet":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "destroy":
                    return item
    raise AssertionError("未找到 PolicyViewSet.destroy 方法")


def _has_transaction_atomic_import(module: ast.Module) -> bool:
    """检查模块顶部的 from-import 中是否存在 `from django.db import transaction`。"""
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == "django.db":
            for alias in node.names:
                if alias.name == "transaction":
                    return True
    return False


def _atomic_wraps_both_calls(destroy_node: ast.FunctionDef) -> tuple[bool, str]:
    """
    检查 destroy 方法体内是否存在一个 with transaction.atomic() 块，且该块包含：
    1) PeriodicTask.objects.filter(...).delete()
    2) super().destroy(...)
    两个调用都必须出现在该 with 块的 body 中（按出现顺序：delete 在前、destroy 在后）。
    """
    for stmt in destroy_node.body:
        if not isinstance(stmt, ast.With):
            continue
        # 检查 with-item 是 transaction.atomic()
        if not _is_transaction_atomic_withitem(stmt.items[0]):
            continue
        body = stmt.body
        has_periodic_delete, periodic_idx = _find_periodic_task_delete(body)
        has_super_destroy, super_idx = _find_super_destroy(body)
        if has_periodic_delete and has_super_destroy:
            if periodic_idx is not None and super_idx is not None and periodic_idx < super_idx:
                return True, ""
            return False, "transaction.atomic 块存在，但 PeriodicTask.delete 未在 super().destroy 之前"
        missing = []
        if not has_periodic_delete:
            missing.append("PeriodicTask.objects.filter(...).delete()")
        if not has_super_destroy:
            missing.append("super().destroy(...)")
        return False, f"transaction.atomic 块存在，但缺少 {' / '.join(missing)}"
    return False, "destroy 体内未发现 `with transaction.atomic():` 块"


def _is_transaction_atomic_withitem(item: ast.withitem) -> bool:
    """检查 with-item 是否为 transaction.atomic() 形式的调用。"""
    expr = item.context_expr
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Attribute) and func.attr == "atomic":
            value = func.value
            if isinstance(value, ast.Name) and value.id == "transaction":
                return True
    return False


def _find_periodic_task_delete(body: list[ast.stmt]) -> tuple[bool, int | None]:
    """在 body 中查找 PeriodicTask.objects.filter(...).delete() 调用，返回 (found, idx)。"""
    for idx, stmt in enumerate(body):
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            # 形如 PeriodicTask.objects.filter(...).delete()
            func = call.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "delete"
                and isinstance(func.value, ast.Call)
            ):
                inner = func.value
                if (
                    isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "filter"
                    and isinstance(inner.func.value, ast.Attribute)
                    and inner.func.value.attr == "objects"
                    and isinstance(inner.func.value.value, ast.Name)
                    and inner.func.value.value.id == "PeriodicTask"
                ):
                    return True, idx
    return False, None


def _find_super_destroy(body: list[ast.stmt]) -> tuple[bool, int | None]:
    """在 body 中查找 super().destroy(...) 调用，返回 (found, idx)。"""
    for idx, stmt in enumerate(body):
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            func = call.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "destroy"
                and isinstance(func.value, ast.Call)
                and isinstance(func.value.func, ast.Name)
                and func.value.func.id == "super"
            ):
                return True, idx
    return False, None


# ---------------------------------------------------------------------------
# 测试 1：destroy 方法必须 import transaction 并被 atomic 包裹
# ---------------------------------------------------------------------------

def test_destroy_imports_transaction_atomic():
    """
    #3948 红测：PolicyViewSet.destroy 必须 `from django.db import transaction` 且
    主体用 `with transaction.atomic():` 包裹 PeriodicTask.delete 与 super().destroy。
    当前 master（160a17568）缺这一包裹——测试必须失败。
    """
    source = POLICY_PY.read_text(encoding="utf-8")
    module = ast.parse(source)

    assert _has_transaction_atomic_import(module), (
        "destroy 路径需要事务，但 policy.py 顶部缺少 `from django.db import transaction`"
    )

    destroy_node = _get_destroy_function_node(module)
    ok, reason = _atomic_wraps_both_calls(destroy_node)
    assert ok, f"PolicyViewSet.destroy 缺少原子性包裹（issue #3948 根因）：{reason}"


# ---------------------------------------------------------------------------
# 测试 2：destroy 内 PeriodicTask.delete 必须在 super().destroy 之前（同事务块内顺序敏感）
# ---------------------------------------------------------------------------

def test_destroy_periodic_task_delete_precedes_super_destroy():
    """
    #3948 顺序断言：PeriodicTask.delete 必须在 super().destroy 之前执行。
    倒序执行会让 Policy 先于 PeriodicTask 删除，仍然有"Policy 删失败但 PeriodicTask 已删"的孤儿。
    """
    source = POLICY_PY.read_text(encoding="utf-8")
    module = ast.parse(source)
    destroy_node = _get_destroy_function_node(module)

    # 在 destroy 的所有顶层 with/expr 中查找两者的最早出现位置
    flat_calls = []

    def _walk_for_calls(node):
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and isinstance(child.value, ast.Call):
                call = child.value
                func = call.func
                if isinstance(func, ast.Attribute) and func.attr == "destroy":
                    if (
                        isinstance(func.value, ast.Call)
                        and isinstance(func.value.func, ast.Name)
                        and func.value.func.id == "super"
                    ):
                        flat_calls.append(("super_destroy", child.lineno))
            elif isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                call = child.value
                func = call.func
                # PeriodicTask.objects.filter(...).delete()
                if isinstance(func, ast.Attribute) and func.attr == "delete":
                    flat_calls.append(("periodic_delete", child.lineno))

    _walk_for_calls(destroy_node)

    pd = [ln for kind, ln in flat_calls if kind == "periodic_delete"]
    sd = [ln for kind, ln in flat_calls if kind == "super_destroy"]

    assert pd, "destroy 体内未发现 PeriodicTask.delete 调用"
    assert sd, "destroy 体内未发现 super().destroy 调用"
    assert min(pd) < min(sd), (
        f"PeriodicTask.delete (line {min(pd)}) 必须在 super().destroy (line {min(sd)}) 之前——"
        "否则 super().destroy 抛异常时 PeriodicTask.delete 已先 commit，留下永不扫描的孤儿策略"
    )