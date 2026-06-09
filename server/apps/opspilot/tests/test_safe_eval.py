"""opspilot.utils.safe_eval 生产规格 + 安全测试。

规格：SafeExpressionEvaluator 只允许比较/逻辑/成员/下标等安全表达式，
拒绝函数调用、属性访问、算术等不在白名单的 AST 节点（防表达式注入）。
这是条件流转的安全闸门，必须严格。
"""

import pytest

from apps.opspilot.utils.safe_eval import SafeExpressionEvaluator, evaluate_condition

pytestmark = pytest.mark.unit


class TestValidExpressions:
    @pytest.mark.parametrize("expr,vars,expected", [
        ("status == 'active'", {"status": "active"}, True),
        ("status != 'active'", {"status": "active"}, False),
        ("count > 0", {"count": 5}, True),
        ("count >= 5 and count <= 10", {"count": 5}, True),
        ("count > 0 or count < -10", {"count": -5}, False),
        ("status in ['active', 'pending']", {"status": "pending"}, True),
        ("status not in ['a', 'b']", {"status": "c"}, True),
        ("not done", {"done": False}, True),
        ("1 < count < 10", {"count": 5}, True),       # 链式比较
        ("1 < count < 10", {"count": 50}, False),
        ("data['key'] == 'v'", {"data": {"key": "v"}}, True),
        ("items[0] == 'first'", {"items": ["first", "second"]}, True),
    ])
    def test_合法表达式(self, expr, vars, expected):
        assert evaluate_condition(expr, **vars) is expected


class TestVariableErrors:
    def test_未定义变量抛错(self):
        with pytest.raises(ValueError, match="表达式求值错误"):
            evaluate_condition("x == 1")


class TestSecurityRejections:
    """不在白名单内的 AST 节点必须被拒绝。"""

    @pytest.mark.parametrize("expr", [
        "__import__('os').system('echo hi')",   # 函数调用 + dunder
        "obj.attr == 1",                          # 属性访问(Name obj 也未定义)
        "1 + 1 == 2",                             # 算术 BinOp 不支持
        "len(items) > 0",                         # 函数调用
        "(lambda: 1)() == 1",                     # lambda/调用
    ])
    def test_拒绝不安全表达式(self, expr):
        with pytest.raises(ValueError):
            evaluate_condition(expr, items=[1], obj=None)

    def test_语法错误抛_valueerror(self):
        with pytest.raises(ValueError):
            evaluate_condition("status ==")


class TestEvaluatorReuse:
    def test_同一实例可多次求值(self):
        ev = SafeExpressionEvaluator()
        assert ev.evaluate("a == 1", {"a": 1}) is True
        assert ev.evaluate("a == 1", {"a": 2}) is False
