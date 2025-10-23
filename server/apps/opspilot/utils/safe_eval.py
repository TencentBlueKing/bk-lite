import ast
import operator
from typing import Any, Dict


class SafeExpressionEvaluator:
    """安全的表达式求值器，仅支持基本的比较和逻辑运算"""

    # 支持的操作符映射
    OPERATORS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda x, y: x in y,
        ast.NotIn: lambda x, y: x not in y,
        ast.And: operator.and_,
        ast.Or: operator.or_,
        ast.Not: operator.not_,
    }

    def __init__(self):
        self._variables = {}

    def evaluate(self, expression: str, variables: Dict[str, Any]) -> bool:
        """
        安全地计算表达式

        Args:
            expression: 表达式字符串，如 "status in ['active', 'pending']"
            variables: 变量字典，如 {"status": "active"}

        Returns:
            bool: 表达式计算结果

        Raises:
            ValueError: 表达式语法错误或包含不安全操作
        """
        try:
            # 解析表达式为 AST
            tree = ast.parse(expression, mode="eval")

            # 设置变量上下文
            self._variables = variables

            # 计算表达式
            result = self._eval_node(tree.body)

            # 确保返回布尔值
            return bool(result)

        except (SyntaxError, ValueError, TypeError) as e:
            raise ValueError(f"表达式求值错误: {e}")

    def _eval_node(self, node: ast.AST) -> Any:
        """递归计算 AST 节点"""

        # 常量值（Python 3.8+ 统一使用）
        if isinstance(node, ast.Constant):
            return node.value

        # 变量引用
        elif isinstance(node, ast.Name):
            if node.id in self._variables:
                return self._variables[node.id]
            raise ValueError(f"未定义的变量: {node.id}")

        # 列表字面量
        elif isinstance(node, ast.List):
            return [self._eval_node(item) for item in node.elts]

        # 元组字面量
        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(item) for item in node.elts)

        # 字典字面量
        elif isinstance(node, ast.Dict):
            return {self._eval_node(k): self._eval_node(v) for k, v in zip(node.keys, node.values)}

        # 集合字面量
        elif isinstance(node, ast.Set):
            return {self._eval_node(item) for item in node.elts}

        # 比较操作
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)

            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if type(op) not in self.OPERATORS:
                    raise ValueError(f"不支持的操作符: {type(op).__name__}")

                # 执行比较操作
                if not self.OPERATORS[type(op)](left, right):
                    return False
                left = right  # 链式比较：a < b < c

            return True

        # 布尔操作
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(value) for value in node.values)
            elif isinstance(node.op, ast.Or):
                return any(self._eval_node(value) for value in node.values)
            else:
                raise ValueError(f"不支持的布尔操作: {type(node.op).__name__}")

        # 一元操作
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not self._eval_node(node.operand)
            elif isinstance(node.op, ast.UAdd):
                return +self._eval_node(node.operand)
            elif isinstance(node.op, ast.USub):
                return -self._eval_node(node.operand)
            else:
                raise ValueError(f"不支持的一元操作: {type(node.op).__name__}")

        # 下标访问（用于支持 dict[key] 和 list[index]）
        elif isinstance(node, ast.Subscript):
            value = self._eval_node(node.value)
            slice_val = self._eval_node(node.slice)
            return value[slice_val]

        else:
            raise ValueError(f"不支持的节点类型: {type(node).__name__}")


def evaluate_condition(expression: str, **variables) -> bool:
    """
    便捷的条件表达式求值函数

    Args:
        expression: 条件表达式字符串
        **variables: 变量值

    Returns:
        bool: 条件判断结果

    Example:
        >>> evaluate_condition("status in ['active', 'pending']", status='active')
        True
        >>> evaluate_condition("count > 0 and count <= 100", count=50)
        True
        >>> evaluate_condition("data['key'] == 'value'", data={'key': 'value'})
        True
    """
    evaluator = SafeExpressionEvaluator()
    return evaluator.evaluate(expression, variables)
