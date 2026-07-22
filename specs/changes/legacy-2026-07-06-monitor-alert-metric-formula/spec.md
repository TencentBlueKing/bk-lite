# Historical Superpowers change: 2026-07-06-monitor-alert-metric-formula

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-06-monitor-alert-metric-formula.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将监控告警策略“定义指标”从单指标扩展为支持结构化多指标公式、AND/OR 条件、维度匹配、预览、扫描、阈值和无数据告警的完整能力。

**Architecture:** 单指标继续走现有 `query_condition.type = metric` 路径，多指标新增 `query_condition.type = formula`。后端新增表达式引擎模块，负责解析、校验和编译 MetricsQL；现有预览和扫描服务只接入最终查询结果，继续复用阈值、恢复、无数据和通知链路。前端将现有 `MetricDefinitionForm` 拆成指标编辑器，单指标保存旧结构，多指标保存 `formula` 结构。

**Tech Stack:** Python 3.12、Django 4.2、pytest、VictoriaMetrics/MetricsQL、Next.js 16、React 19、TypeScript、Ant Design、pnpm。

---

## File Structure

后端新增文件：

- `server/apps/monitor/expression/__init__.py`：表达式模块导出入口。
- `server/apps/monitor/expression/errors.py`：表达式错误类型，统一转换成 `BaseAppException` 可读消息。
- `server/apps/monitor/expression/ast.py`：AST 节点 dataclass。
- `server/apps/monitor/expression/parser.py`：受限表达式 tokenizer 和 Pratt/递归下降 parser。
- `server/apps/monitor/expression/conditions.py`：AND/OR 条件编译器，复用现有 label 校验和转义规则。
- `server/apps/monitor/expression/validators.py`：formula 结构、变量引用、维度匹配校验。
- `server/apps/monitor/expression/compiler.py`：将 formula 输入和 AST 编译为 MetricsQL。
- `server/apps/monitor/expression/query.py`：统一 `metric` / `pmq` / `formula` 查询构建门面，供预览和扫描调用。
- `server/apps/monitor/tests/test_formula_expression_parser.py`：表达式解析测试。
- `server/apps/monitor/tests/test_formula_condition_compiler.py`：AND/OR 条件编译测试。
- `server/apps/monitor/tests/test_formula_validator.py`：变量和维度匹配校验测试。
- `server/apps/monitor/tests/test_formula_compiler.py`：MetricsQL 编译测试。
- `server/apps/monitor/tests/test_formula_policy_preview.py`：预览服务集成测试。
- `server/apps/monitor/tests/test_formula_policy_scan.py`：扫描、模板变量和无数据语义测试。

后端修改文件：

- `server/apps/monitor/serializers/monitor_policy.py`：扩展 `validate_query_condition`，支持 `formula` 和 AND/OR 条件。
- `server/apps/monitor/services/policy_preview.py`：调用统一查询构建门面；支持 formula 预览、warning 和最终结果单位。
- `server/apps/monitor/tasks/services/policy_scan/metric_query.py`：调用统一查询构建门面；`metric` 路径保持旧行为，`formula` 路径返回最终公式查询。
- `server/apps/monitor/tasks/services/policy_scan/alert_detector.py`：多指标 `${metric_name}` 取 `result_name`；维度名映射支持公式锚点。
- `server/apps/monitor/services/policy_baseline.py`：无数据基准刷新基于公式最终结果序列。

前端新增文件：

- `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionTypes.ts`：多指标编辑器类型。
- `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`：变量分配、表达式引用提取、payload 转换。
- `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`：指标表达式编辑器。
- `web/scripts/monitor-policy-formula-payload-test.ts`：前端纯逻辑测试脚本。

前端修改文件：

- `web/src/app/monitor/types/event.ts`：扩展 `StrategyFields.query_condition` union。
- `web/src/app/monitor/types/index.ts`：扩展 `FilterItem` 增加 `logic?: 'and' | 'or'`。
- `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`：接入表达式编辑器，单指标保存旧结构，多指标保存 formula。
- `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`：改为包装新编辑器或迁移后删除重复逻辑。
- `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`：预览 payload 支持 formula。
- `web/src/app/monitor/locales/zh.json`、`web/src/app/monitor/locales/en.json`：新增错误、warning 和控件文案。

## Task 1: 后端表达式 Parser

**Files:**
- Create: `server/apps/monitor/expression/__init__.py`
- Create: `server/apps/monitor/expression/errors.py`
- Create: `server/apps/monitor/expression/ast.py`
- Create: `server/apps/monitor/expression/parser.py`
- Test: `server/apps/monitor/tests/test_formula_expression_parser.py`

- [ ] **Step 1: Write parser tests**

Create `server/apps/monitor/tests/test_formula_expression_parser.py`:

```python
import pytest

from apps.monitor.expression.ast import BinaryOpNode, NumberNode, VariableNode
from apps.monitor.expression.errors import FormulaSyntaxError
from apps.monitor.expression.parser import parse_expression


def test_parse_operator_precedence():
    node = parse_expression("a / b * 100")

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "*"
    assert isinstance(node.right, NumberNode)
    assert node.right.value == 100
    assert isinstance(node.left, BinaryOpNode)
    assert node.left.operator == "/"
    assert isinstance(node.left.left, VariableNode)
    assert node.left.left.name == "a"
    assert isinstance(node.left.right, VariableNode)
    assert node.left.right.name == "b"


def test_parse_parentheses():
    node = parse_expression("(a + b) / c")

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "/"
    assert isinstance(node.left, BinaryOpNode)
    assert node.left.operator == "+"
    assert isinstance(node.right, VariableNode)
    assert node.right.name == "c"


def test_reject_unknown_character():
    with pytest.raises(FormulaSyntaxError) as exc:
        parse_expression("a / b; drop")

    assert "非法字符" in str(exc.value)


def test_reject_unclosed_parentheses():
    with pytest.raises(FormulaSyntaxError) as exc:
        parse_expression("(a / b")

    assert "括号" in str(exc.value)
```

- [ ] **Step 2: Run parser tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_expression_parser.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.monitor.expression'`.

- [ ] **Step 3: Add expression errors**

Create `server/apps/monitor/expression/errors.py`:

```python
class FormulaError(ValueError):
    """公式配置错误基类。"""


class FormulaSyntaxError(FormulaError):
    """公式语法错误。"""


class FormulaValidationError(FormulaError):
    """公式结构或语义校验错误。"""


class FormulaCompileError(FormulaError):
    """公式编译错误。"""
```

Create `server/apps/monitor/expression/__init__.py`:

```python
"""监控告警指标表达式引擎。"""
```

- [ ] **Step 4: Add AST nodes**

Create `server/apps/monitor/expression/ast.py`:

```python
from dataclasses import dataclass


class ExpressionNode:
    pass


@dataclass(frozen=True)
class NumberNode(ExpressionNode):
    value: float | int


@dataclass(frozen=True)
class VariableNode(ExpressionNode):
    name: str


@dataclass(frozen=True)
class BinaryOpNode(ExpressionNode):
    operator: str
    left: ExpressionNode
    right: ExpressionNode
```

- [ ] **Step 5: Implement parser**

Create `server/apps/monitor/expression/parser.py`:

```python
import re
from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, NumberNode, VariableNode
from apps.monitor.expression.errors import FormulaSyntaxError


TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
    |(?P<NUMBER>\d+(?:\.\d+)?)
    |(?P<IDENT>[a-zA-Z][a-zA-Z0-9_]*)
    |(?P<OP>[+\-*/()])
    |(?P<MISMATCH>.)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    type: str
    value: str


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    for match in TOKEN_RE.finditer(expression or ""):
        kind = match.lastgroup or "MISMATCH"
        value = match.group()
        if kind == "SPACE":
            continue
        if kind == "MISMATCH":
            raise FormulaSyntaxError(f"表达式包含非法字符：{value}")
        tokens.append(Token(kind, value))
    if not tokens:
        raise FormulaSyntaxError("表达式不能为空")
    return tokens


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def parse(self) -> ExpressionNode:
        node = self.parse_add_sub()
        if self.current() is not None:
            raise FormulaSyntaxError(f"表达式存在多余内容：{self.current().value}")
        return node

    def parse_add_sub(self) -> ExpressionNode:
        node = self.parse_mul_div()
        while self.match("+") or self.match("-"):
            operator = self.previous().value
            right = self.parse_mul_div()
            node = BinaryOpNode(operator, node, right)
        return node

    def parse_mul_div(self) -> ExpressionNode:
        node = self.parse_primary()
        while self.match("*") or self.match("/"):
            operator = self.previous().value
            right = self.parse_primary()
            node = BinaryOpNode(operator, node, right)
        return node

    def parse_primary(self) -> ExpressionNode:
        token = self.current()
        if token is None:
            raise FormulaSyntaxError("表达式不完整")
        if token.type == "NUMBER":
            self.index += 1
            if "." in token.value:
                return NumberNode(float(token.value))
            return NumberNode(int(token.value))
        if token.type == "IDENT":
            self.index += 1
            return VariableNode(token.value)
        if token.value == "(":
            self.index += 1
            node = self.parse_add_sub()
            if not self.match(")"):
                raise FormulaSyntaxError("表达式括号不匹配")
            return node
        raise FormulaSyntaxError(f"表达式语法错误：{token.value}")

    def current(self) -> Token | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def previous(self) -> Token:
        return self.tokens[self.index - 1]

    def match(self, value: str) -> bool:
        token = self.current()
        if token and token.value == value:
            self.index += 1
            return True
        return False


def parse_expression(expression: str) -> ExpressionNode:
    return Parser(tokenize(expression)).parse()
```

- [ ] **Step 6: Run parser tests and commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_expression_parser.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/expression server/apps/monitor/tests/test_formula_expression_parser.py
git commit -m "feat(monitor): 添加告警公式解析器"
```

## Task 2: 条件维度 AND/OR 编译器

**Files:**
- Create: `server/apps/monitor/expression/conditions.py`
- Modify: `server/apps/monitor/tasks/utils/metric_query.py`
- Test: `server/apps/monitor/tests/test_formula_condition_compiler.py`

- [ ] **Step 1: Write condition compiler tests**

Create `server/apps/monitor/tests/test_formula_condition_compiler.py`:

```python
import pytest

from apps.monitor.expression.conditions import compile_filter_to_selectors


def test_compile_all_and_conditions_to_one_selector():
    selectors = compile_filter_to_selectors(
        "http_requests_total",
        [
            {"name": "service", "method": "=", "value": "checkout"},
            {"logic": "and", "name": "status", "method": "=~", "value": "5.."},
        ],
    )

    assert selectors == ['http_requests_total{service="checkout",status=~"5.."}']


def test_compile_or_conditions_to_selector_union():
    selectors = compile_filter_to_selectors(
        "http_requests_total",
        [
            {"name": "service", "method": "=", "value": "checkout"},
            {"logic": "and", "name": "status", "method": "=~", "value": "5.."},
            {"logic": "or", "name": "status", "method": "=", "value": "499"},
        ],
    )

    assert selectors == [
        'http_requests_total{service="checkout",status=~"5.."}',
        'http_requests_total{status="499"}',
    ]


def test_compile_empty_filter_keeps_placeholder_empty_selector():
    assert compile_filter_to_selectors("up", []) == ["up"]


def test_reject_invalid_logic():
    with pytest.raises(ValueError) as exc:
        compile_filter_to_selectors("up", [{"logic": "xor", "name": "a", "method": "=", "value": "b"}])

    assert "logic" in str(exc.value)
```

- [ ] **Step 2: Run condition tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_condition_compiler.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing `compile_filter_to_selectors`.

- [ ] **Step 3: Implement condition compiler**

Create `server/apps/monitor/expression/conditions.py`:

```python
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter


def split_filter_groups(filters: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for index, item in enumerate(filters or []):
        logic = str(item.get("logic") or "and").lower()
        if index == 0:
            logic = "and"
        if logic not in {"and", "or"}:
            raise ValueError(f"filter[{index}].logic 非法，只允许 and/or")
        if logic == "or" and current:
            groups.append(current)
            current = []
        condition = {key: item.get(key) for key in ("name", "method", "value")}
        current.append(condition)
    if current:
        groups.append(current)
    return groups


def compile_filter_to_selectors(metric_query: str, filters: list[dict]) -> list[str]:
    groups = split_filter_groups(filters)
    if not groups:
        return [metric_query.replace("__$labels__", "")]

    selectors: list[str] = []
    for group in groups:
        vm_filter = format_to_vm_filter(group)
        selectors.append(metric_query.replace("__$labels__", vm_filter))
    return selectors


def compile_filter_to_query(metric_query: str, filters: list[dict]) -> str:
    selectors = compile_filter_to_selectors(metric_query, filters)
    if len(selectors) == 1:
        return selectors[0]
    return " or ".join(f"({selector})" for selector in selectors)
```

- [ ] **Step 4: Reuse condition compiler in existing metric filter path**

Modify `server/apps/monitor/tasks/utils/metric_query.py` only if needed for shared validation. Keep `format_to_vm_filter` unchanged so old callers remain stable.

No code change is required in this file for this task if `conditions.py` imports `format_to_vm_filter`.

- [ ] **Step 5: Run condition tests and commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_condition_compiler.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/expression/conditions.py server/apps/monitor/tests/test_formula_condition_compiler.py
git commit -m "feat(monitor): 支持指标条件 AND OR 编译"
```

## Task 3: Formula 结构与维度校验

**Files:**
- Create: `server/apps/monitor/expression/validators.py`
- Modify: `server/apps/monitor/serializers/monitor_policy.py`
- Test: `server/apps/monitor/tests/test_formula_validator.py`
- Test: `server/apps/monitor/tests/test_monitor_policy_serializer_validation.py`

- [ ] **Step 1: Write formula validator tests**

Create `server/apps/monitor/tests/test_formula_validator.py`:

```python
import pytest

from apps.monitor.expression.errors import FormulaValidationError
from apps.monitor.expression.validators import validate_formula_condition


def formula(**overrides):
    data = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "status"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
        ],
    }
    data.update(overrides)
    return data


def test_validate_formula_allows_subset_dimensions():
    result = validate_formula_condition(formula())

    assert result.anchor_ref == "a"
    assert result.warnings == []


def test_validate_formula_warns_cross_dimension_reuse():
    payload = formula(
        expression="a / b - c",
        queries=[
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "status"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
            {"ref": "c", "metric_id": 3, "filter": [], "group_algorithm": "avg", "group_by": ["status"]},
        ],
    )

    result = validate_formula_condition(payload)

    assert result.anchor_ref == "a"
    assert result.warnings
    assert "跨缺失维度复用" in result.warnings[0]["message"]


def test_validate_formula_rejects_extra_non_anchor_dimension():
    payload = formula(
        queries=[
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "path"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "method"]},
        ],
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "锚点外额外维度" in str(exc.value)


def test_validate_formula_rejects_missing_variable_reference():
    payload = formula(expression="a / c")

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "不存在" in str(exc.value)
```

- [ ] **Step 2: Run validator tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_validator.py -q
```

Expected: FAIL with missing `validators.py`.

- [ ] **Step 3: Implement formula validator**

Create `server/apps/monitor/expression/validators.py`:

```python
from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, VariableNode
from apps.monitor.expression.errors import FormulaValidationError
from apps.monitor.expression.parser import parse_expression


@dataclass(frozen=True)
class FormulaValidationResult:
    ast: ExpressionNode
    anchor_ref: str
    warnings: list[dict]


def collect_variables(node: ExpressionNode) -> list[str]:
    if isinstance(node, VariableNode):
        return [node.name]
    if isinstance(node, BinaryOpNode):
        return collect_variables(node.left) + collect_variables(node.right)
    return []


def validate_formula_condition(query_condition: dict) -> FormulaValidationResult:
    if query_condition.get("type") != "formula":
        raise FormulaValidationError("query_condition.type 必须为 formula")
    if not query_condition.get("result_name"):
        raise FormulaValidationError("多指标策略必须填写结果名称")
    expression = query_condition.get("expression") or ""
    ast = parse_expression(expression)
    queries = query_condition.get("queries")
    if not isinstance(queries, list) or len(queries) < 2:
        raise FormulaValidationError("多指标策略至少需要两个指标")

    by_ref: dict[str, dict] = {}
    for index, item in enumerate(queries):
        ref = str(item.get("ref") or "")
        if not ref:
            raise FormulaValidationError(f"queries[{index}].ref 不能为空")
        if ref in by_ref:
            raise FormulaValidationError(f"指标变量 {ref} 重复")
        if not item.get("metric_id"):
            raise FormulaValidationError(f"指标 {ref} 缺少 metric_id")
        if not item.get("group_algorithm"):
            raise FormulaValidationError(f"指标 {ref} 缺少 group_algorithm")
        group_by = item.get("group_by")
        if not isinstance(group_by, list) or not group_by:
            raise FormulaValidationError(f"指标 {ref} 缺少 group_by")
        by_ref[ref] = item

    variables = collect_variables(ast)
    if not variables:
        raise FormulaValidationError("表达式必须引用指标变量")
    for ref in variables:
        if ref not in by_ref:
            raise FormulaValidationError(f"表达式引用了不存在的指标变量 {ref}")

    anchor_ref = variables[0]
    anchor_group_by = set(by_ref[anchor_ref].get("group_by") or [])
    warnings: list[dict] = []
    for ref in dict.fromkeys(variables[1:]):
        group_by = set(by_ref[ref].get("group_by") or [])
        extra = sorted(group_by - anchor_group_by)
        if extra:
            raise FormulaValidationError(f"指标 {ref} 包含锚点外额外维度：{', '.join(extra)}")
        if group_by and not group_by.issuperset({"instance_id"}) and group_by != anchor_group_by:
            warnings.append(
                {
                    "code": "FORMULA_DIMENSION_REUSE",
                    "message": f"指标 {ref} 将按 {', '.join(sorted(group_by))} 对齐，并跨缺失维度复用数据",
                }
            )

    return FormulaValidationResult(ast=ast, anchor_ref=anchor_ref, warnings=warnings)
```

- [ ] **Step 4: Extend serializer validation**

Modify `server/apps/monitor/serializers/monitor_policy.py` in `validate_query_condition`:

```python
        if query_type == "formula":
            from apps.monitor.expression.errors import FormulaError
            from apps.monitor.expression.validators import validate_formula_condition

            try:
                validate_formula_condition(value)
            except FormulaError as err:
                raise serializers.ValidationError(str(err)) from err
            return value
```

Place this block after the existing `pmq` block and before the metric `metric_id` requirement.

- [ ] **Step 5: Add serializer test for formula validation**

Append to `server/apps/monitor/tests/test_monitor_policy_serializer_validation.py`:

```python
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer


def test_serializer_accepts_valid_formula_query_condition():
    serializer = MonitorPolicySerializer()
    value = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "status"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
        ],
    }

    assert serializer.validate_query_condition(value) == value
```

- [ ] **Step 6: Run validator and serializer tests, then commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_validator.py apps/monitor/tests/test_monitor_policy_serializer_validation.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/expression/validators.py server/apps/monitor/serializers/monitor_policy.py server/apps/monitor/tests/test_formula_validator.py server/apps/monitor/tests/test_monitor_policy_serializer_validation.py
git commit -m "feat(monitor): 校验多指标公式结构"
```

## Task 4: Formula MetricsQL 编译

**Files:**
- Create: `server/apps/monitor/expression/compiler.py`
- Create: `server/apps/monitor/expression/query.py`
- Modify: `server/apps/monitor/services/policy_preview.py`
- Modify: `server/apps/monitor/tasks/services/policy_scan/metric_query.py`
- Test: `server/apps/monitor/tests/test_formula_compiler.py`

- [ ] **Step 1: Write compiler tests**

Create `server/apps/monitor/tests/test_formula_compiler.py`:

```python
import pytest

from apps.monitor.expression.compiler import FormulaCompiler


class MetricObj:
    def __init__(self, metric_id, query, unit="", display_name=""):
        self.id = metric_id
        self.query = query
        self.unit = unit
        self.display_name = display_name
        self.dimensions = []


def test_compile_formula_with_group_left():
    metrics = {
        1: MetricObj(1, "disk_read_latency_gauge{__$labels__}"),
        2: MetricObj(2, "disk_total_gauge{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "读延迟占比",
        "expression": "a / b",
        "queries": [
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id", "config_type"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert "avg(disk_read_latency_gauge{}) by (instance_id,config_type)" in compiled.query
    assert "/ on(instance_id) group_left" in compiled.query
    assert "avg(disk_total_gauge{}) by (instance_id)" in compiled.query
    assert compiled.result_name == "读延迟占比"
    assert compiled.group_by == ["instance_id", "config_type"]


def test_compile_formula_same_dimensions_without_group_left():
    metrics = {
        1: MetricObj(1, "a_metric{__$labels__}"),
        2: MetricObj(2, "b_metric{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "比率",
        "expression": "a / b * 100",
        "queries": [
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert "group_left" not in compiled.query
    assert "* 100" in compiled.query
```

- [ ] **Step 2: Run compiler tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_compiler.py -q
```

Expected: FAIL with missing `compiler.py`.

- [ ] **Step 3: Implement formula compiler**

Create `server/apps/monitor/expression/compiler.py`:

```python
from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, NumberNode, VariableNode
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.validators import validate_formula_condition


@dataclass(frozen=True)
class CompiledFormula:
    query: str
    result_name: str
    group_by: list[str]
    warnings: list[dict]
    anchor_ref: str


class FormulaCompiler:
    def __init__(self, query_condition: dict, metrics_by_id: dict[int, object]):
        self.query_condition = query_condition
        self.metrics_by_id = metrics_by_id
        self.validation = validate_formula_condition(query_condition)
        self.inputs = {item["ref"]: item for item in query_condition["queries"]}
        self.anchor_group_by = self.inputs[self.validation.anchor_ref]["group_by"]

    def compile(self) -> CompiledFormula:
        query = self._compile_node(self.validation.ast)
        return CompiledFormula(
            query=query,
            result_name=self.query_condition["result_name"],
            group_by=list(self.anchor_group_by),
            warnings=self.validation.warnings,
            anchor_ref=self.validation.anchor_ref,
        )

    def _compile_node(self, node: ExpressionNode) -> str:
        if isinstance(node, NumberNode):
            return str(node.value)
        if isinstance(node, VariableNode):
            return self._compile_variable(node.name)
        if isinstance(node, BinaryOpNode):
            left = self._compile_node(node.left)
            right = self._compile_node(node.right)
            modifier = self._match_modifier(node.left, node.right)
            return f"({left} {node.operator}{modifier} {right})"
        raise TypeError(f"Unsupported expression node: {type(node)!r}")

    def _compile_variable(self, ref: str) -> str:
        item = self.inputs[ref]
        metric = self.metrics_by_id[item["metric_id"]]
        base_query = compile_filter_to_query(metric.query, item.get("filter") or [])
        group_by = ",".join(item.get("group_by") or [])
        return f"{item['group_algorithm']}({base_query}) by ({group_by})"

    def _match_modifier(self, left: ExpressionNode, right: ExpressionNode) -> str:
        left_ref = self._first_variable(left)
        right_ref = self._first_variable(right)
        if not left_ref or not right_ref:
            return ""
        left_group = set(self.inputs[left_ref]["group_by"])
        right_group = set(self.inputs[right_ref]["group_by"])
        if left_group == right_group:
            return ""
        common = [key for key in self.inputs[left_ref]["group_by"] if key in right_group]
        if not common:
            return ""
        if right_group.issubset(left_group):
            return f" on({','.join(common)}) group_left"
        return ""

    def _first_variable(self, node: ExpressionNode) -> str | None:
        if isinstance(node, VariableNode):
            return node.name
        if isinstance(node, BinaryOpNode):
            return self._first_variable(node.left) or self._first_variable(node.right)
        return None
```

- [ ] **Step 4: Implement query builder门面**

Create `server/apps/monitor/expression/query.py`:

```python
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.expression.compiler import CompiledFormula, FormulaCompiler
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter


def build_metric_query(metric, filters: list[dict]) -> str:
    vm_filter = format_to_vm_filter(filters or [])
    return (metric.query or "").replace("__$labels__", vm_filter)


def build_formula_query(query_condition: dict) -> CompiledFormula:
    metric_ids = [item["metric_id"] for item in query_condition.get("queries") or []]
    metrics = Metric.objects.filter(id__in=metric_ids)
    by_id = {metric.id: metric for metric in metrics}
    missing = [metric_id for metric_id in metric_ids if metric_id not in by_id]
    if missing:
        raise BaseAppException(f"metric does not exist [{missing[0]}]")
    return FormulaCompiler(query_condition, by_id).compile()
```

- [ ] **Step 5: Run compiler tests and commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_compiler.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/expression/compiler.py server/apps/monitor/expression/query.py server/apps/monitor/tests/test_formula_compiler.py
git commit -m "feat(monitor): 编译多指标公式查询"
```

## Task 5: 预览服务接入 formula

**Files:**
- Modify: `server/apps/monitor/services/policy_preview.py`
- Test: `server/apps/monitor/tests/test_formula_policy_preview.py`
- Test: `server/apps/monitor/tests/test_policy_preview_service.py`

- [ ] **Step 1: Write preview tests**

Create `server/apps/monitor/tests/test_formula_policy_preview.py`:

```python
import pytest

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_preview import PolicyPreviewService


@pytest.mark.django_db
def test_preview_formula_uses_compiled_query(mocker):
    obj = MonitorObject.objects.create(name="FormulaObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    a = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="a_metric",
        query="a_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    b = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="b_metric",
        query="b_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["query"] = query
        captured["group_by"] = group_by
        return {"status": "success", "data": {"result": []}}

    mocker.patch.dict(
        "apps.monitor.services.policy_preview.METHOD",
        {"avg_over_time": fake_method},
        clear=False,
    )

    svc = PolicyPreviewService(
        {
            "query_condition": {
                "type": "formula",
                "result_name": "错误率",
                "expression": "a / b * 100",
                "queries": [
                    {"ref": "a", "metric_id": a.id, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id", "status"]},
                    {"ref": "b", "metric_id": b.id, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
                ],
            },
            "period": {"type": "min", "value": 5},
            "algorithm": "avg_over_time",
            "group_algorithm": "avg",
            "group_by": ["instance_id"],
            "preview": {"duration_points": 1},
        }
    )

    out = svc.preview()

    assert "on(instance_id) group_left" in captured["query"]
    assert captured["group_by"] == "instance_id,status"
    assert out["warnings"] == []
```

- [ ] **Step 2: Run preview tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_policy_preview.py -q
```

Expected: FAIL because `PolicyPreviewService` does not handle `formula`.

- [ ] **Step 3: Modify PolicyPreviewService**

Modify `server/apps/monitor/services/policy_preview.py`:

```python
from apps.monitor.expression.query import build_formula_query
```

In `preview`, after `query_condition = self._require_dict("query_condition")`, branch formula:

```python
        compiled_formula = None
        if query_condition.get("type") == "formula":
            compiled_formula = build_formula_query(query_condition)
            metric_query = compiled_formula.query
            group_by = compiled_formula.group_by
            group_by_clause = ",".join(group_by)
            self.warnings.extend(compiled_formula.warnings)
        else:
            group_by = self._require_string_list("group_by")
            group_by_clause = ",".join(group_by)
            metric_query = self._build_metric_query(query_condition)
```

Remove the original unconditional `group_by = ...` and `metric_query = ...` lines so they are not duplicated.

- [ ] **Step 4: Run preview regression tests and commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_policy_preview.py apps/monitor/tests/test_policy_preview_service.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/services/policy_preview.py server/apps/monitor/tests/test_formula_policy_preview.py
git commit -m "feat(monitor): 预览多指标公式"
```

## Task 6: 扫描链路、模板变量和无数据基准接入 formula

**Files:**
- Modify: `server/apps/monitor/tasks/services/policy_scan/metric_query.py`
- Modify: `server/apps/monitor/tasks/services/policy_scan/alert_detector.py`
- Modify: `server/apps/monitor/services/policy_baseline.py`
- Test: `server/apps/monitor/tests/test_formula_policy_scan.py`

- [ ] **Step 1: Write scan service tests**

Create `server/apps/monitor/tests/test_formula_policy_scan.py`:

```python
from datetime import datetime, timezone
from types import SimpleNamespace

from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService


def test_formula_query_aggregation_uses_formula_group_by(mocker):
    policy = SimpleNamespace(
        id=1,
        last_run_time=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
        query_condition={"type": "formula", "result_name": "错误率"},
        period={"type": "min", "value": 5},
        algorithm="avg_over_time",
        group_algorithm="avg",
        group_by=["instance_id"],
        metric_unit="",
        calculation_unit="",
    )
    compiled = SimpleNamespace(
        query="sum(a{}) by (instance_id,status) / on(instance_id) group_left sum(b{}) by (instance_id)",
        group_by=["instance_id", "status"],
        result_name="错误率",
        warnings=[],
    )
    captured = {}

    mocker.patch("apps.monitor.tasks.services.policy_scan.metric_query.build_formula_query", return_value=compiled)

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["query"] = query
        captured["group_by"] = group_by
        return {"status": "success", "data": {"result": []}}

    mocker.patch.dict(
        "apps.monitor.tasks.services.policy_scan.metric_query.METHOD",
        {"avg_over_time": fake_method},
        clear=False,
    )

    service = MetricQueryService(policy, {})
    service.set_monitor_obj_instance_key()
    service.query_aggregation_metrics(policy.period)

    assert service.instance_id_keys == ["instance_id", "status"]
    assert captured["query"].startswith("sum(a{})")
    assert captured["group_by"] == "instance_id,status"
```

- [ ] **Step 2: Run scan tests and verify failure**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_policy_scan.py -q
```

Expected: FAIL because `MetricQueryService` does not import or use `build_formula_query`.

- [ ] **Step 3: Modify MetricQueryService for formula**

Modify `server/apps/monitor/tasks/services/policy_scan/metric_query.py`:

```python
from apps.monitor.expression.query import build_formula_query
```

In `__init__` add:

```python
        self.compiled_formula = None
```

In `set_monitor_obj_instance_key`, before metric type handling:

```python
        if query_type == "formula":
            self.compiled_formula = build_formula_query(self.policy.query_condition)
            self.instance_id_keys = self.compiled_formula.group_by
            return
```

In `format_pmq`, before metric type handling:

```python
        if query_type == "formula":
            if self.compiled_formula is None:
                self.compiled_formula = build_formula_query(query_condition)
            return self.compiled_formula.query
```

In `query_aggregation_metrics`, replace:

```python
        group_by = ",".join(self.policy.group_by or [])
```

with:

```python
        group_by_keys = self.compiled_formula.group_by if self.compiled_formula else (self.policy.group_by or [])
        group_by = ",".join(group_by_keys)
```

In `format_aggregation_metrics`, replace:

```python
        group_by_keys = self.policy.group_by or []
```

with:

```python
        group_by_keys = self.compiled_formula.group_by if self.compiled_formula else (self.policy.group_by or [])
```

- [ ] **Step 4: Modify metric display name**

Modify `server/apps/monitor/tasks/services/policy_scan/alert_detector.py` in `_get_metric_display_name`:

```python
        if self.policy.query_condition.get("type") == "formula":
            return self.policy.query_condition.get("result_name", "")
```

Place this before reading `self.metric_query_service.metric`.

- [ ] **Step 5: Modify baseline group_by for formula**

Modify `server/apps/monitor/services/policy_baseline.py` in `_query_metric_instances` after `metric_query_service.query_aggregation_metrics(...)`:

```python
            group_by_keys = metric_query_service.instance_id_keys or self.policy.group_by or []
```

Replace the existing:

```python
            group_by_keys = self.policy.group_by or []
```

- [ ] **Step 6: Run scan tests and commit**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_formula_policy_scan.py apps/monitor/tests/test_metric_query_trigger_count.py -q
```

Expected: PASS.

Commit:

```bash
git add server/apps/monitor/tasks/services/policy_scan/metric_query.py server/apps/monitor/tasks/services/policy_scan/alert_detector.py server/apps/monitor/services/policy_baseline.py server/apps/monitor/tests/test_formula_policy_scan.py
git commit -m "feat(monitor): 扫描多指标公式结果"
```

## Task 7: 前端类型与 payload 转换

**Files:**
- Create: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionTypes.ts`
- Create: `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`
- Modify: `web/src/app/monitor/types/event.ts`
- Modify: `web/src/app/monitor/types/index.ts`
- Test: `web/scripts/monitor-policy-formula-payload-test.ts`

- [ ] **Step 1: Write frontend payload test**

Create `web/scripts/monitor-policy-formula-payload-test.ts`:

```ts
import assert from 'node:assert/strict';
import {
  buildFormulaQueryCondition,
  extractFormulaRefs,
  toMetricRowsFromMetricCondition
} from '../src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils';

const refs = extractFormulaRefs('a / b * 100');
assert.deepEqual(refs, ['a', 'b']);

const rows = toMetricRowsFromMetricCondition({
  type: 'metric',
  metric_id: 10,
  filter: [{ name: 'service', method: '=', value: 'checkout' }]
});
assert.equal(rows.length, 1);
assert.equal(rows[0].ref, 'a');
assert.equal(rows[0].metricId, 10);

const formula = buildFormulaQueryCondition({
  resultName: 'HTTP 5xx 错误率',
  expression: 'a / b * 100',
  rows: [
    {
      ref: 'a',
      metricId: 1,
      filters: [{ name: 'status', method: '=~', value: '5..' }],
      groupAlgorithm: 'sum',
      groupBy: ['instance_id', 'status']
    },
    {
      ref: 'b',
      metricId: 2,
      filters: [],
      groupAlgorithm: 'sum',
      groupBy: ['instance_id']
    }
  ]
});

assert.equal(formula.type, 'formula');
assert.equal(formula.result_name, 'HTTP 5xx 错误率');
assert.equal(formula.queries[0].ref, 'a');
assert.equal(formula.queries[1].group_by[0], 'instance_id');

console.log('monitor-policy-formula-payload-test passed');
```

- [ ] **Step 2: Add npm script**

Modify `web/package.json` scripts:

```json
"test:monitor-policy-formula-payload": "pnpm exec tsx scripts/monitor-policy-formula-payload-test.ts",
```

Place it near other `test:monitor-*` scripts.

- [ ] **Step 3: Run frontend test and verify failure**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload
```

Expected: FAIL because `formulaExpressionUtils` does not exist.

- [ ] **Step 4: Add expression types**

Create `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionTypes.ts`:

```ts
import { FilterItem } from '@/app/monitor/types';

export interface MetricExpressionRow {
  ref: string;
  metricId: number | null;
  metricName?: string;
  filters: FilterItem[];
  groupAlgorithm: string;
  groupBy: string[];
}

export interface FormulaQueryCondition {
  type: 'formula';
  result_name: string;
  expression: string;
  queries: Array<{
    ref: string;
    metric_id: number;
    filter: FilterItem[];
    group_algorithm: string;
    group_by: string[];
  }>;
}

export interface MetricQueryCondition {
  type: 'metric';
  metric_id?: number;
  filter?: FilterItem[];
}
```

- [ ] **Step 5: Add payload utilities**

Create `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`:

```ts
import {
  FormulaQueryCondition,
  MetricExpressionRow,
  MetricQueryCondition
} from './metricExpressionTypes';

export const VARIABLE_SEQUENCE = 'abcdefghijklmnopqrstuvwxyz'.split('');

export const createMetricRow = (index: number): MetricExpressionRow => ({
  ref: VARIABLE_SEQUENCE[index] || `m${index + 1}`,
  metricId: null,
  filters: [],
  groupAlgorithm: 'avg',
  groupBy: ['instance_id']
});

export const extractFormulaRefs = (expression: string): string[] => {
  const refs = new Set<string>();
  const matcher = /\b[a-zA-Z][a-zA-Z0-9_]*\b/g;
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(expression || ''))) {
    refs.add(match[0]);
  }
  return Array.from(refs);
};

export const toMetricRowsFromMetricCondition = (
  condition?: MetricQueryCondition
): MetricExpressionRow[] => [
  {
    ref: 'a',
    metricId: condition?.metric_id || null,
    filters: condition?.filter || [],
    groupAlgorithm: 'avg',
    groupBy: ['instance_id']
  }
];

export const buildFormulaQueryCondition = ({
  resultName,
  expression,
  rows
}: {
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): FormulaQueryCondition => ({
  type: 'formula',
  result_name: resultName,
  expression,
  queries: rows.map((row) => ({
    ref: row.ref,
    metric_id: row.metricId as number,
    filter: row.filters,
    group_algorithm: row.groupAlgorithm,
    group_by: row.groupBy
  }))
});
```

- [ ] **Step 6: Extend shared types**

Modify `web/src/app/monitor/types/index.ts` `FilterItem` definition to include:

```ts
logic?: 'and' | 'or' | null;
```

Modify `web/src/app/monitor/types/event.ts` `StrategyFields.query_condition` to:

```ts
  query_condition?:
    | {
        type: 'metric';
        query?: string;
        metric_id?: number;
        filter?: FilterItem[];
      }
    | {
        type: 'pmq';
        query?: string;
      }
    | {
        type: 'formula';
        result_name: string;
        expression: string;
        queries: Array<{
          ref: string;
          metric_id: number;
          filter?: FilterItem[];
          group_algorithm: string;
          group_by: string[];
        }>;
      };
```

- [ ] **Step 7: Run frontend payload test and commit**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload
```

Expected: `monitor-policy-formula-payload-test passed`.

Commit:

```bash
git add web/package.json web/scripts/monitor-policy-formula-payload-test.ts web/src/app/monitor/types web/src/app/monitor/\\(pages\\)/event/strategy/detail/metricExpressionTypes.ts web/src/app/monitor/\\(pages\\)/event/strategy/detail/formulaExpressionUtils.ts
git commit -m "feat(monitor): 添加公式策略前端数据模型"
```

## Task 8: 前端指标表达式编辑器

**Files:**
- Create: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`

- [ ] **Step 1: Create editor component**

Create `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`:

```tsx
'use client';

import React from 'react';
import { Button, Input, Select } from 'antd';
import { CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { FilterItem, IndexViewItem, ListItem, MetricItem } from '@/app/monitor/types';
import { MetricExpressionRow } from './metricExpressionTypes';

const { Option } = Select;

interface Props {
  rows: MetricExpressionRow[];
  resultName: string;
  expression: string;
  labelsByRef: Record<string, string[]>;
  originMetricData: IndexViewItem[];
  groupByOptions: string[];
  groupMethods: ListItem[];
  conditionMethods: ListItem[];
  onRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
}

const MetricExpressionEditor: React.FC<Props> = ({
  rows,
  resultName,
  expression,
  labelsByRef,
  originMetricData,
  groupByOptions,
  groupMethods,
  conditionMethods,
  onRowsChange,
  onResultNameChange,
  onExpressionChange
}) => {
  const updateRow = (index: number, patch: Partial<MetricExpressionRow>) => {
    const next = rows.map((row, rowIndex) =>
      rowIndex === index ? { ...row, ...patch } : row
    );
    onRowsChange(next);
  };

  const addCondition = (rowIndex: number) => {
    const row = rows[rowIndex];
    updateRow(rowIndex, {
      filters: [
        ...row.filters,
        { logic: row.filters.length ? 'and' : undefined, name: null, method: null, value: '' }
      ] as FilterItem[]
    });
  };

  const updateCondition = (
    rowIndex: number,
    conditionIndex: number,
    patch: Partial<FilterItem>
  ) => {
    const row = rows[rowIndex];
    const filters = row.filters.map((item, index) =>
      index === conditionIndex ? { ...item, ...patch } : item
    );
    updateRow(rowIndex, { filters });
  };

  const removeCondition = (rowIndex: number, conditionIndex: number) => {
    const row = rows[rowIndex];
    const filters = row.filters.filter((_, index) => index !== conditionIndex);
    onRowsChange(
      rows.map((item, index) => (index === rowIndex ? { ...item, filters } : item))
    );
  };

  return (
    <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3">
      <div className="flex flex-col gap-3">
        {rows.map((row, rowIndex) => (
          <div
            key={row.ref}
            className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3"
          >
            <div className="flex items-center gap-2">
              <span className="w-6 rounded border border-[var(--color-border-2)] text-center text-xs text-[var(--color-primary)]">
                {row.ref}
              </span>
              <Select
                className="flex-1"
                showSearch
                value={row.metricName}
                placeholder="指标"
                options={originMetricData.map((group) => ({
                  label: group.display_name,
                  title: group.name,
                  options: (group.child || []).map((metric: MetricItem) => ({
                    label: metric.display_name,
                    value: metric.name
                  }))
                }))}
                onChange={(value) => updateRow(rowIndex, { metricName: value })}
              />
              <Select
                className="w-[130px]"
                value={row.groupAlgorithm}
                onChange={(value) => updateRow(rowIndex, { groupAlgorithm: value })}
              >
                {groupMethods.map((item) => (
                  <Option key={item.value} value={item.value}>
                    {item.label}
                  </Option>
                ))}
              </Select>
              <Select
                className="flex-1"
                mode="multiple"
                value={row.groupBy}
                options={groupByOptions.map((item) => ({ label: item, value: item }))}
                onChange={(value) => updateRow(rowIndex, { groupBy: value })}
              />
              {rows.length > 1 && (
                <Button
                  icon={<CloseOutlined />}
                  onClick={() => onRowsChange(rows.filter((_, index) => index !== rowIndex))}
                />
              )}
            </div>
            <div className="ml-8 mt-2 flex flex-col gap-2">
              {row.filters.map((filter, filterIndex) => (
                <div className="flex items-center gap-2" key={`${row.ref}-${filterIndex}`}>
                  {filterIndex > 0 && (
                    <Select
                      className="w-[76px]"
                      value={filter.logic || 'and'}
                      onChange={(value) => updateCondition(rowIndex, filterIndex, { logic: value })}
                      options={[
                        { label: 'AND', value: 'and' },
                        { label: 'OR', value: 'or' }
                      ]}
                    />
                  )}
                  <Select
                    className="w-[180px]"
                    value={filter.name}
                    placeholder="维度"
                    options={(labelsByRef[row.ref] || []).map((item) => ({ label: item, value: item }))}
                    onChange={(value) => updateCondition(rowIndex, filterIndex, { name: value })}
                  />
                  <Select
                    className="w-[90px]"
                    value={filter.method}
                    options={conditionMethods.map((item) => ({ label: item.name, value: item.id }))}
                    onChange={(value) => updateCondition(rowIndex, filterIndex, { method: value })}
                  />
                  <Input
                    className="w-[180px]"
                    value={filter.value}
                    placeholder="值"
                    onChange={(event) => updateCondition(rowIndex, filterIndex, { value: event.target.value })}
                  />
                  <Button icon={<CloseOutlined />} onClick={() => removeCondition(rowIndex, filterIndex)} />
                </div>
              ))}
              <Button className="w-fit" icon={<PlusOutlined />} onClick={() => addCondition(rowIndex)}>
                添加条件
              </Button>
            </div>
          </div>
        ))}
        <Button className="w-fit" icon={<PlusOutlined />} onClick={() => onRowsChange([...rows, { ref: String.fromCharCode(97 + rows.length), metricId: null, filters: [], groupAlgorithm: 'avg', groupBy: ['instance_id'] }])}>
          添加指标
        </Button>
        {rows.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="w-6 text-center text-[var(--color-primary)]">fx</span>
            <Input className="w-[220px]" value={resultName} placeholder="结果名称" onChange={(event) => onResultNameChange(event.target.value)} />
            <span>=</span>
            <Input value={expression} placeholder="a / b * 100" onChange={(event) => onExpressionChange(event.target.value)} />
          </div>
        )}
      </div>
    </div>
  );
};

export default MetricExpressionEditor;
```

- [ ] **Step 2: Wire editor into MetricDefinitionForm**

Modify `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx` by importing the editor and adding props:

```ts
import MetricExpressionEditor from './metricExpressionEditor';
import { MetricExpressionRow } from './metricExpressionTypes';
```

Extend `MetricDefinitionFormProps`:

```ts
  metricRows: MetricExpressionRow[];
  resultName: string;
  expression: string;
  labelsByRef: Record<string, string[]>;
  onMetricRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
```

Replace the existing non-Trap metric/group/condition JSX block with:

```tsx
              <Form.Item
                name="metric"
                label={<span className="w-[100px]">{t('monitor.metric')}</span>}
                rules={[{ validator: validateMetric, required: true }]}
                className="mb-[16px]"
              >
                <MetricExpressionEditor
                  rows={metricRows}
                  resultName={resultName}
                  expression={expression}
                  labelsByRef={labelsByRef}
                  originMetricData={originMetricData}
                  groupByOptions={groupByOptions}
                  groupMethods={GROUP_METHOD_LIST}
                  conditionMethods={CONDITION_LIST}
                  onRowsChange={onMetricRowsChange}
                  onResultNameChange={onResultNameChange}
                  onExpressionChange={onExpressionChange}
                />
              </Form.Item>
```

- [ ] **Step 3: Wire state in page**

Modify `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`:

Add state:

```ts
  const [metricRows, setMetricRows] = useState<MetricExpressionRow[]>([createMetricRow(0)]);
  const [formulaResultName, setFormulaResultName] = useState<string>('');
  const [formulaExpression, setFormulaExpression] = useState<string>('a / b * 100');
  const [labelsByRef, setLabelsByRef] = useState<Record<string, string[]>>({});
```

Import:

```ts
import { buildFormulaQueryCondition, createMetricRow, extractFormulaRefs } from './formulaExpressionUtils';
import { MetricExpressionRow } from './metricExpressionTypes';
```

Pass props to `MetricDefinitionForm`.

- [ ] **Step 4: Update createStrategy payload**

In `createStrategy`, replace non-Trap `params.query_condition` assignment with:

```ts
        if (metricRows.length > 1) {
          const refs = extractFormulaRefs(formulaExpression);
          const rowRefs = new Set(metricRows.map((row) => row.ref));
          const missingRef = refs.find((ref) => !rowRefs.has(ref));
          if (!formulaResultName.trim()) {
            message.error('多指标策略必须填写结果名称');
            return;
          }
          if (missingRef) {
            message.error(`表达式引用了不存在的指标变量 ${missingRef}`);
            return;
          }
          params.query_condition = buildFormulaQueryCondition({
            resultName: formulaResultName.trim(),
            expression: formulaExpression.trim(),
            rows: metricRows
          });
          params.source = source;
          params.metric_unit = '';
        } else {
          const mertricTarget = metrics.find((item) => item.name === metricRows[0]?.metricName);
          params.query_condition = {
            type: 'metric',
            metric_id: mertricTarget?.id,
            filter: metricRows[0]?.filters || []
          };
          params.source = source;
          params.metric_unit = isStringArray(mertricTarget?.unit) ? '' : mertricTarget?.unit;
        }
```

Ensure `return` inside validation exits before `operateStrategy(params)`.

- [ ] **Step 5: Run frontend type check and commit**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: PASS.

Commit:

```bash
git add web/src/app/monitor/\\(pages\\)/event/strategy/detail web/src/app/monitor/locales web/src/app/monitor/types
git commit -m "feat(monitor): 构建多指标公式编辑器"
```

## Task 9: 前端预览接入 formula

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`

- [ ] **Step 1: Extend MetricPreview props**

Modify `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`:

```ts
import { FormulaQueryCondition, MetricExpressionRow } from './metricExpressionTypes';
import { buildFormulaQueryCondition } from './formulaExpressionUtils';
```

Extend props:

```ts
  metricRows?: MetricExpressionRow[];
  formulaResultName?: string;
  formulaExpression?: string;
```

- [ ] **Step 2: Update canQuery**

Replace `canQuery` calculation with:

```ts
  const isFormula = (metricRows?.length || 0) > 1;
  const canQuery = useMemo(() => {
    const sanitizedGroupBy = sanitizeGroupBy(groupBy);
    if (isFormula) {
      return !!(
        monitorObjId &&
        algorithm &&
        formulaResultName &&
        formulaExpression &&
        selectedInstance &&
        instances.length > 0 &&
        metricRows?.every((row) => row.metricId && row.groupBy.length)
      );
    }
    return !!(
      monitorObjId &&
      metric &&
      algorithm &&
      sanitizedGroupBy.length > 0 &&
      selectedInstance &&
      instances.length > 0
    );
  }, [monitorObjId, metric, algorithm, groupBy.length, selectedInstance, instances.length, isFormula, formulaResultName, formulaExpression, metricRows]);
```

- [ ] **Step 3: Build formula preview payload**

In `getPreviewPayload`, before current metric branch:

```ts
    if (isFormula && metricRows?.length) {
      return {
        monitor_object: monitorObjId,
        query_condition: buildFormulaQueryCondition({
          resultName: formulaResultName || '',
          expression: formulaExpression || '',
          rows: metricRows
        }) as FormulaQueryCondition,
        source,
        period: {
          type: periodUnit,
          value: period || 5
        },
        algorithm,
        group_algorithm: groupAlgorithm || 'avg',
        group_by: metricRows[0]?.groupBy || ['instance_id'],
        metric_unit: '',
        calculation_unit: calculationUnit || '',
        preview: {
          instance_id: selectedInst.instance_id,
          instance_id_values: selectedInst.instance_id_values,
          duration_points: 30
        }
      };
    }
```

- [ ] **Step 4: Pass preview props from page**

Modify `MetricPreview` usage in `page.tsx`:

```tsx
                metricRows={metricRows}
                formulaResultName={formulaResultName}
                formulaExpression={formulaExpression}
```

- [ ] **Step 5: Run frontend gates and commit**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: PASS.

Commit:

```bash
git add web/src/app/monitor/\\(pages\\)/event/strategy/detail/metricPreview.tsx web/src/app/monitor/\\(pages\\)/event/strategy/detail/page.tsx
git commit -m "feat(monitor): 预览多指标公式结果"
```

## Task 10: End-to-end verification and cleanup

**Files:**
- Verify only; modify files only to fix failures found by the commands below.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd server && uv run pytest \
  apps/monitor/tests/test_formula_expression_parser.py \
  apps/monitor/tests/test_formula_condition_compiler.py \
  apps/monitor/tests/test_formula_validator.py \
  apps/monitor/tests/test_formula_compiler.py \
  apps/monitor/tests/test_formula_policy_preview.py \
  apps/monitor/tests/test_formula_policy_scan.py \
  apps/monitor/tests/test_policy_preview_service.py \
  apps/monitor/tests/test_monitor_policy_serializer_validation.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run backend monitor app tests**

Run:

```bash
cd server && make test-app APP=monitor
```

Expected: PASS. If the app suite is too slow for local iteration, capture the first failing focused test and fix it before rerunning the focused command from Step 1.

- [ ] **Step 3: Run frontend tests and gates**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload && pnpm lint && pnpm type-check
```

Expected: PASS.

- [ ] **Step 4: Manual preview check**

Start services if needed:

```bash
cd server && make dev
cd web && pnpm dev
```

Open the strategy detail page and verify:

- Single metric save payload uses `query_condition.type = metric`.
- Adding a second metric shows `结果名称 = 表达式`.
- `HTTP 5xx 错误率 = a / b * 100` preview sends `query_condition.type = formula`.
- Removing a referenced metric blocks save with a missing-variable message.
- AND/OR condition rows serialize `logic` from the second condition onward.

- [ ] **Step 5: Final commit if verification fixes were needed**

If Step 1-4 required fixes:

```bash
git add server/apps/monitor web/src/app/monitor web/scripts web/package.json
git commit -m "fix(monitor): 完善多指标公式验证"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

Spec coverage:

- 单指标保持旧结构：Task 7、Task 8、Task 10 覆盖。
- 多指标 formula 结构：Task 3、Task 4、Task 7、Task 8 覆盖。
- AND/OR 条件：Task 2、Task 8、Task 10 覆盖。
- 维度匹配和 `on(...) group_left`：Task 3、Task 4、Task 6 覆盖。
- 预览和扫描：Task 5、Task 6、Task 9 覆盖。
- 无数据和模板变量：Task 6 覆盖。
- 测试和质量门禁：Task 10 覆盖。

Placeholder scan:

- 本计划每个任务都给出明确文件、命令和代码片段。

Type consistency:

- 后端统一使用 `formula`、`result_name`、`expression`、`queries[].ref`、`queries[].group_algorithm`、`queries[].group_by`。
- 前端 `MetricExpressionRow` 使用 camelCase，payload 转换函数输出后端 snake_case。

## specs: 2026-07-06-monitor-alert-metric-formula-design.md

日期：2026-07-06
状态：已确认设计
范围：bk-lite 监控告警策略的“定义指标”步骤

## 背景

当前监控告警策略是单指标模型：策略通过 `query_condition.type = metric` 指向一个指标，再使用条件维度、分组聚合方式、分组维度、策略级聚合周期、策略级聚合方式和阈值完成评估。

该模型可以覆盖 CPU、内存、磁盘、网络等单指标告警，但不能直接表达成功率、错误率、容量使用率、队列净积压等多指标计算场景。目标是在普通策略页面中把“指标”配置升级为指标表达式编辑器，支持单指标、多指标、过滤、分组和公式计算，同时不把用户暴露到 PromQL/MetricsQL 输入框。

## 目标

- 单指标策略行为与当前一致，保存结构和扫描语义保持稳定。
- 多指标策略通过多行指标输入和公式表达最终指标。
- 用户在页面中编辑 `a / b * 100` 这类公式，而不是编辑编译后的 MetricsQL。
- 多指标最终结果继续复用现有阈值、连续触发、恢复、无数据和通知链路。
- 条件维度从现有 AND 能力升级为 AND/OR，单指标和多指标都可使用。
- `${metric_name}` 在单指标取指标显示名，在多指标取公式结果名称。
- 公式结果无数据时触发无数据告警，不对子查询分别告警。

## 非目标

- 不迁移历史单指标策略。
- 不在普通策略页面新增 PromQL/MetricsQL 创建入口。
- 不开放完整 PromQL/MetricsQL 语法。
- 不在第一阶段支持多个表达式分别触发不同告警。
- 不在第一阶段支持跨数据源 join、同比环比、复杂条件表达式。

## 方案选择

采用“结构化指标输入 + 受限公式 + MetricsQL 编译器”方案。

不保存编译后的 MetricsQL。落库保存用户可编辑的公式和每行指标结构，扫描和预览时由后端编译为 MetricsQL。这样可以保留前端回填能力、做变量和维度校验、限制查询风险，并为后续函数扩展留出空间。

## 数据结构

`MonitorPolicy` 不新增数据库列，继续使用 `query_condition` JSON。现有类型保持不变：

- `metric`：旧单指标结构，继续用于历史策略和新建单指标策略。
- `pmq`：历史兼容和 Trap 场景，普通策略页不新增创建入口。
- `formula`：新增多指标结构。

示例：

```json
{
  "type": "formula",
  "result_name": "HTTP 5xx 错误率",
  "expression": "a / b * 100",
  "queries": [
    {
      "ref": "a",
      "metric_id": 101,
      "filter": [
        { "name": "service", "method": "=", "value": "checkout" },
        { "logic": "and", "name": "status", "method": "=~", "value": "5.." }
      ],
      "group_algorithm": "sum",
      "group_by": ["instance_id", "status"]
    },
    {
      "ref": "b",
      "metric_id": 102,
      "filter": [
        { "name": "service", "method": "=", "value": "checkout" }
      ],
      "group_algorithm": "sum",
      "group_by": ["instance_id"]
    }
  ]
}
```

兼容规则：

- 旧 `metric` 策略不迁移。
- 编辑旧 `metric` 策略时，前端回填为指标编辑器中的一行 `a`。
- 新建单指标策略仍保存为 `metric` 结构。
- 只有多指标策略保存为 `formula` 结构。
- `pmq` 继续兼容扫描和预览，但普通 metric 策略页面不开放原始查询创建。

## 前端交互

“定义指标”步骤升级为指标编辑器。

单指标状态：

- 默认只有一行变量 `a`。
- 不展示公式行。
- 条件维度、分组聚合方式、分组维度沿用现有控件。
- 保存时仍生成旧 `metric` payload。

多指标状态：

- 点击“添加指标”新增行，变量自动按顺序分配 `a`、`b`、`c`。
- 每行支持选择指标、条件维度、分组聚合方式、分组维度和删除。
- 多指标展示公式行：`结果名称 = 表达式`。
- 删除指标后，若表达式仍引用被删除变量，保存前提示。
- 右侧预览展示公式最终结果序列，标题取 `result_name`。

条件维度：

- 复用现有 `{name, method, value}` 结构。
- 新增可选 `logic`，从第二条条件开始生效。
- 缺省 `logic = and`，兼容旧数据。
- 条件语义为 OR 分隔 AND 组：`A AND B OR C AND D` 解释为 `(A AND B) OR (C AND D)`。
- 不支持括号和嵌套条件组。

## 表达式语言

第一阶段支持：

- 变量：`a`、`b`、`c` 等指标行变量。
- 数字：整数和小数。
- 运算符：`+`、`-`、`*`、`/`。
- 括号：`(`、`)`。

表达式中不能引用不存在的变量。变量名由前端自动分配，后端仍校验唯一性和引用合法性。

后端模块设计预留函数注册表，后续可扩展 `safe_div`、`default`、`clamp`、`abs`、`round` 等受控函数。第一阶段如未实现函数，校验阶段拒绝函数调用。

## 查询编译

新增表达式引擎模块，建议结构：

```text
server/apps/monitor/expression/
  ast.py
  parser.py
  validators.py
  compiler.py
  functions.py
  errors.py
```

职责：

- Parser：把用户公式解析成 AST。
- Validator：校验变量、函数、参数、维度、条件和注入风险。
- Compiler：把结构化指标输入和 AST 编译为 MetricsQL。
- Functions：函数注册表，定义函数签名和编译规则。
- Errors：表达式错误类型和用户可读消息。

指标输入编译复用现有 `Metric.query`、`format_to_vm_filter`、`group_algorithm` 和 `group_by` 逻辑，避免重复实现 label 拼接。

全 AND 条件继续编译为 label selector：

```promql
metric{service="checkout",status=~"5.."}
```

包含 OR 时编译为 selector 组合：

```promql
metric{service="checkout",status=~"5.."} or metric{service="checkout",status="499"}
```

## 维度匹配规则

多指标不要求所有行 `group_by` 完全相同，但必须保证公式结果有明确告警实例。

规则：

1. 公式中第一个出现的变量是结果锚点。
2. 最终公式结果维度、告警唯一性、`dimensions`、`metric_instance_id` 和 `${metric_xxx}` 维度变量跟随锚点指标的 `group_by`。
3. 非锚点指标的 `group_by` 必须是锚点 `group_by` 的子集，或与锚点完全相同。
4. 非锚点指标如果包含锚点没有的额外维度，保存和预览校验失败。
5. 非锚点指标是锚点维度子集时，编译器自动生成 `on(...) group_left`。
6. 非锚点子集不包含锚点主实例维度时允许，但返回 warning，提示该指标会跨缺失维度复用。

示例：

```text
a by(instance_id, config_type)
b by(instance_id)
公式：a / b
```

编译为：

```promql
(a_query) / on(instance_id) group_left (b_query)
```

场景表：

| 场景 | 处理 |
| --- | --- |
| `a(1,2) / b(1,2)` | 允许，直接计算 |
| `a(1,2) / b(1)` | 允许，生成 `on(1) group_left` |
| `a(1,2) / b(2)` | 允许并 warning，生成 `on(2) group_left` |
| `a(1,2) / b(1,4)` | 拦截，`b` 有锚点外额外维度 |
| `a(1,2) / b(3,4)` | 拦截，无法唯一匹配 |
| `a(1,2) / b(1) - c(2)` | 允许并 warning，结果仍按 `a(1,2)` 告警 |

该规则支持明细指标除以粗粒度总量，例如每个 `status`、`config_type` 或 `path` 的占比，同时避免 `path` 与 `method` 这类多对多误匹配。

## 评估流程

策略评估顺序保持：

```text
指标行生成基础序列
-> 多指标按公式计算最终序列
-> 策略级聚合周期和聚合方式评估
-> 阈值判断
```

`formula` 对下游表现为一个最终指标序列。阈值、连续触发、恢复、无数据、事件创建、告警创建和通知发送继续复用现有链路。

## 无数据与异常处理

- 公式最终结果无数据时，走现有无数据告警逻辑。
- 子查询单独无数据不直接触发无数据告警。
- 子查询有数据但公式结果为空时，预览返回提示：指标输入有数据，但公式结果为空，请检查分组维度和匹配关系。
- 查询失败不生成普通阈值告警。
- 编译失败或静态校验失败时策略不能保存。
- 普通 `/` 的除零行为按 MetricsQL 结果处理；预览可给出除零风险提示。后续可引导使用 `safe_div`。

## 模板变量

- 单指标：`${metric_name}` 取指标显示名。
- 多指标：`${metric_name}` 取 `result_name`。
- 多指标的 `${metric_xxx}` 维度变量来自公式最终结果序列标签，不能来自某个子查询的额外标签。

## API 与服务集成

现有策略创建和更新接口继续使用 `MonitorPolicySerializer`，但扩展 `query_condition` 校验。

预览继续复用当前策略预览入口，payload 与保存结构一致，避免预览和扫描语义分叉。

扫描集成点：

```python
if policy.query_condition.get("type") == "formula":
    query = FormulaQueryBuilder(policy).build()
else:
    query = existing_query_builder(policy)
```

表达式逻辑集中在新模块，现有 `metric` 和 `pmq` 路径尽量不改动。

## 校验规则

静态校验：

- `formula.queries.length >= 2`。
- `result_name` 必填。
- `expression` 必填。
- 变量引用必须存在。
- 每行必须有 `metric_id`、`group_algorithm`、`group_by`。
- 条件维度必须完整。
- 条件 `method` 只允许 `=`、`!=`、`=~`、`!~`。
- 条件 `logic` 只允许 `and`、`or`，缺省 `and`。
- label name 继续使用现有 Prometheus label 白名单。
- 非锚点 `group_by` 必须是锚点 `group_by` 子集或完全相同。

预览校验：

- 编译后的 MetricsQL 能成功查询。
- VM 返回语法错误、向量匹配错误、超时等错误时转成中文提示。
- 公式结果为空但子查询有数据时返回维度匹配提示。

## 测试范围

后端：

- 旧 `metric` 单指标策略保存、编辑、预览、扫描行为不变。
- 历史 `pmq` 策略扫描和预览兼容。
- 单指标条件支持 AND/OR，旧无 `logic` 条件仍按 AND。
- 多指标错误率 `a / b * 100` 可创建、预览和扫描。
- `result_name` 缺失不能保存。
- 表达式引用不存在变量不能保存。
- 删除被公式引用的变量不能保存。
- 非锚点维度是锚点子集时生成 `on(...) group_left`。
- 非锚点有锚点外额外维度时不能保存。
- `a(1,2) / b(1) - c(2)` 允许并返回 warning。
- 公式结果无数据触发无数据告警。
- `${metric_name}` 单指标和多指标取值正确。
- 表达式注入和 label 注入被拒绝。

前端：

- 单指标回填为一行且保存为旧结构。
- 添加、删除多指标行后变量正确分配。
- 多指标展示并校验 `result_name` 和 `expression`。
- 条件维度从第二条开始展示 AND/OR。
- 删除被公式引用的指标后展示错误。
- 预览成功、warning 和错误状态展示正确。

## 分期

第一阶段：

- 多指标结构化输入。
- 四则运算和括号。
- AND/OR 条件维度。
- 自动 MetricsQL 编译。
- `on(...) group_left` 维度匹配。
- 多指标预览、保存、扫描、阈值和无数据告警。

后续阶段：

- 函数注册表开放 `safe_div`、`default`、`clamp` 等函数。
- 时间窗口函数和偏移函数。
- 更高级的公式匹配设置。
- 条件表达式。

## 风险

- MetricsQL 向量匹配语义复杂，必须用预览和可读错误降低误配风险。
- 子查询有数据但公式结果为空容易误解，需要专门提示。
- 不同维度匹配可能放大序列数量，需要限制预览和扫描查询成本。
- 多指标公式的单位语义可能不再能从单个指标推导，第一阶段以 `calculation_unit` 或用户选择的结果单位为准。
