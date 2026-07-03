"""
tests for issue #3653: AlertViewSet bare int() 转换分页/step 参数触发 500

直接测试 _to_positive_int 工具函数的行为契约（Django-free）。
revert 修复代码（将 _to_positive_int 替换回 int()）后这些断言必然失败。
"""
import ast
import pathlib


# ---------------------------------------------------------------------------
# 从 policy.py 源码中提取 _to_positive_int 函数定义，隔离执行（无 Django 依赖）
# ---------------------------------------------------------------------------

_policy_src = (
    pathlib.Path(__file__).parent.parent / "views" / "policy.py"
).read_text(encoding="utf-8")

# 找到 _to_positive_int 函数的 AST 节点并反编译为可执行源码
_tree = ast.parse(_policy_src)
_func_node = next(
    node for node in ast.walk(_tree)
    if isinstance(node, ast.FunctionDef) and node.name == "_to_positive_int"
)
_func_src = ast.get_source_segment(_policy_src, _func_node)

_ns: dict = {}
exec(_func_src, _ns)  # noqa: S102  — controlled exec of our own source
_to_positive_int = _ns["_to_positive_int"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToPositiveInt:
    """直接对 _to_positive_int 工具函数的单元测试"""

    def test_valid_integer_string(self):
        assert _to_positive_int("5", 1) == 5

    def test_valid_integer_zero_clipped_to_min(self):
        # min_val 默认 1，传 0 应返回 1
        assert _to_positive_int("0", 1) == 1

    def test_negative_clipped_to_min(self):
        assert _to_positive_int("-10", 1) == 1

    def test_non_integer_returns_default(self):
        # 这是修复的核心：非整数必须返回默认值而非抛 ValueError
        assert _to_positive_int("abc", 1) == 1

    def test_none_returns_default(self):
        assert _to_positive_int(None, 10) == 10

    def test_float_string_returns_default(self):
        # "1.5" 不能被 int() 直接转换，应返回默认值
        assert _to_positive_int("1.5", 10) == 10

    def test_exceeds_max_val_clipped(self):
        assert _to_positive_int("99999", 1, max_val=500) == 500

    def test_step_non_integer_returns_default(self):
        # step=1h 场景
        assert _to_positive_int("1h", 60) == 60

    def test_step_zero_clipped_to_min_val_1(self):
        # step=0 时 min_val=1 防止除零
        assert _to_positive_int("0", 60, min_val=1, max_val=1440) == 1

    def test_step_valid(self):
        assert _to_positive_int("30", 60, min_val=1, max_val=1440) == 30

    def test_step_exceeds_max(self):
        assert _to_positive_int("9999", 60, min_val=1, max_val=1440) == 1440

    def test_page_size_default_max(self):
        # page_size 上限 500
        assert _to_positive_int("1000", 10, max_val=500) == 500

    def test_empty_string_returns_default(self):
        assert _to_positive_int("", 1) == 1
