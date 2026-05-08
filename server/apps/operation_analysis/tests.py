# -- coding: utf-8 --
# @File: tests.py
# @Time: 2025/7/14 16:35
# @Author: windyzhao
import ast
from pathlib import Path


VIEW_FILE = Path(__file__).with_name("views") / "import_export_view.py"


def _get_function_decorators(function_name):
    module = ast.parse(VIEW_FILE.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "ImportExportViewSet":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == function_name:
                    return item.decorator_list
    raise AssertionError(f"未找到函数 {function_name}")


def _assert_has_permission(function_name, expected_permission):
    decorators = _get_function_decorators(function_name)
    for decorator in decorators:
        if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "HasPermission":
            literal_args = [arg.value for arg in decorator.args if isinstance(arg, ast.Constant)]
            assert expected_permission in literal_args
            return
    raise AssertionError(f"{function_name} 缺少 HasPermission({expected_permission})")


def test_import_export_export_requires_module_view_permission():
    _assert_has_permission("export_objects", "operation_analysis-View")


def test_import_export_precheck_requires_module_add_permission():
    _assert_has_permission("import_precheck", "operation_analysis-Add")


def test_import_export_submit_requires_module_add_permission():
    _assert_has_permission("import_submit", "operation_analysis-Add")
