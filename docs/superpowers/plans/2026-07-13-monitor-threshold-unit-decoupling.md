# 监控告警阈值单位解耦实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将公式结果单位与告警阈值单位拆成独立字段，在同体系内可靠换算阈值，并允许负数、零和小数阈值。

**Architecture:** `MonitorPolicy` 新增 `threshold_unit` 保存用户输入阈值的单位，`calculation_unit` 继续表示最终结果单位。扫描时保留原始策略阈值，通过 `MetricQueryService.convert_thresholds()` 生成换算到结果单位的临时副本，再交给现有 `calculate_alerts()`；前端分别维护两个单位状态，并由纯函数决定候选范围和历史回退。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、pytest、Next.js 16、React 19、TypeScript、Ant Design、pnpm。

## Global Constraints

- 只修改监控策略单位与阈值相关文件，不做全仓格式化。
- 后端数据库访问只使用 Django ORM，不写原生 SQL。
- 新行为必须先写失败测试并观察 RED，再写最小实现使其 GREEN。
- 阈值支持任意有限数；空值表示未配置，拒绝布尔值、`NaN` 和无穷值。
- `metric_unit` 表示采集原始单位，`calculation_unit` 表示最终结果单位，`threshold_unit` 表示阈值输入单位。
- 只允许相同单位或 `UnitConverter.is_convertible()` 为真的同体系换算；不实现容量、时长等单位到 `%` 的隐式转换。
- 历史空 `threshold_unit` 依次回退 `calculation_unit`、合法 `metric_unit`，不得改写历史阈值数值。
- 公式模式默认结果单位和阈值单位均为 `percent`；枚举指标与 Trap 策略不展示阈值单位。

---

## 文件职责

- `server/apps/monitor/models/monitor_policy.py`：持久化 `threshold_unit`。
- `server/apps/monitor/migrations/0046_monitorpolicy_threshold_unit.py`：只新增字段，不执行数据迁移。
- `server/apps/monitor/serializers/monitor_policy.py`：阈值有限数校验、单位合法性与可换算性校验、历史/旧客户端回退。
- `server/apps/monitor/utils/unit_converter.py`：提供公开的有效单位判定，供 API 和扫描共享。
- `server/apps/monitor/services/policy_bulk.py`：批量策略 payload 补齐阈值单位。
- `server/apps/monitor/tasks/services/policy_scan/metric_query.py`：解析有效结果/阈值单位并转换阈值临时副本。
- `server/apps/monitor/tasks/services/policy_scan/alert_detector.py`：将换算后的临时阈值交给现有告警计算函数。
- `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`：阈值单位候选、默认值、历史回退与结果单位切换决策。
- `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`：分别维护、回填和提交结果单位与阈值单位。
- `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`：以结果单位筛选阈值单位候选。
- `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx`：展示独立阈值单位并允许负数输入。
- `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`：预览 payload 透传 `threshold_unit`。
- `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`：把两个单位分别传给预览构建函数。
- `web/scripts/monitor-strategy-detail-logic-test.ts`：覆盖单位状态纯函数和 payload。

---

### Task 1: 后端字段、数值校验与 API 单位契约

**Files:**
- Modify: `server/apps/monitor/models/monitor_policy.py`
- Create: `server/apps/monitor/migrations/0046_monitorpolicy_threshold_unit.py`
- Modify: `server/apps/monitor/serializers/monitor_policy.py`
- Modify: `server/apps/monitor/utils/unit_converter.py`
- Modify: `server/apps/monitor/services/policy_bulk.py`
- Test: `server/apps/monitor/tests/test_monitor_policy_serializer_validation.py`
- Test: `server/apps/monitor/tests/test_unit_converter_extra.py`
- Test: `server/apps/monitor/tests/test_policy_bulk_payload.py`

**Interfaces:**
- Produces: `MonitorPolicy.threshold_unit: str`。
- Produces: `MonitorPolicySerializer.get_effective_units(attrs) -> tuple[str, str]`，返回 `(calculation_unit, threshold_unit)`；只在对象级校验内部使用。
- Produces: 批量策略 payload 的 `threshold_unit`，默认顺序为模板 `threshold_unit`、模板 `calculation_unit`、模板 `metric_unit`、空字符串。

- [ ] **Step 1: 为字段、历史回退、跨体系拒绝和负数阈值写失败测试**

在 `test_monitor_policy_serializer_validation.py` 增加独立测试：

```python
def test_threshold_accepts_negative_zero_and_decimal_values():
    serializer = MonitorPolicySerializer()
    value = [
        {"level": "critical", "method": "<", "value": -10},
        {"level": "error", "method": ">=", "value": 0},
        {"level": "warning", "method": ">", "value": 0.5},
    ]
    assert serializer.validate_threshold(value) == value


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf")])
def test_threshold_rejects_non_finite_or_boolean_values(invalid):
    serializer = MonitorPolicySerializer()
    with pytest.raises(serializers.ValidationError):
        serializer.validate_threshold(
            [{"level": "critical", "method": ">", "value": invalid}]
        )
```

使用现有 `formula_metrics` 构造完整 payload：

```python
def _formula_policy_payload(formula_metrics):
    metric_a, metric_b = formula_metrics
    return {
        "name": "容量差值策略",
        "alert_name": "容量差值 ${value}",
        "monitor_object": metric_a.monitor_object_id,
        "query_condition": {
            "type": "formula",
            "result_name": "容量差值",
            "expression": "a - b",
            "queries": [
                {
                    "ref": "a",
                    "metric_id": metric_a.id,
                    "filter": [],
                    "group_algorithm": "sum",
                    "group_by": ["instance_id"],
                },
                {
                    "ref": "b",
                    "metric_id": metric_b.id,
                    "filter": [],
                    "group_algorithm": "sum",
                    "group_by": ["instance_id"],
                },
            ],
        },
        "source": {"type": "instance", "values": ["('host-a',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_algorithm": "sum",
        "algorithm": "avg_over_time",
        "group_by": ["instance_id"],
        "enable_alerts": ["threshold"],
    }


def test_serializer_accepts_convertible_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["metric_unit"] = ""
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = "gibibytes"
    payload["threshold"] = [{"level": "critical", "method": ">", "value": 10}]
    serializer = MonitorPolicySerializer(data=payload)
    assert serializer.is_valid(), serializer.errors


def test_serializer_rejects_cross_system_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = "percent"
    payload["threshold"] = [{"level": "critical", "method": ">", "value": 80}]
    serializer = MonitorPolicySerializer(data=payload)
    assert not serializer.is_valid()
    assert "threshold_unit" in serializer.errors


def test_serializer_accepts_legacy_empty_threshold_unit(formula_metrics):
    payload = _formula_policy_payload(formula_metrics)
    payload["calculation_unit"] = "bytes"
    payload["threshold_unit"] = ""
    payload["threshold"] = [{"level": "critical", "method": ">", "value": 10}]
    serializer = MonitorPolicySerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
```

在 `test_policy_bulk_payload.py` 断言 `payload["threshold_unit"]` 优先取模板阈值单位，缺失时回退计算单位。

- [ ] **Step 2: 运行聚焦测试，确认因字段和校验缺失而失败**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_bulk_payload.py -q
```

Expected: FAIL，错误包含 `threshold_unit` 字段不存在、跨体系组合未拒绝或非有限阈值未拒绝；不得是 fixture/import 错误。

- [ ] **Step 3: 新增模型字段和 0046 迁移**

在 `MonitorPolicy.calculation_unit` 后新增：

```python
threshold_unit = models.CharField(
    max_length=50,
    default="",
    blank=True,
    verbose_name="告警阈值单位",
)
```

迁移只包含一个 `AddField`，依赖 `("monitor", "0045_alter_monitorinstance_interval_and_more")`，不写 `RunPython`。

- [ ] **Step 4: 实现阈值有限数和对象级单位校验**

在 `validate_threshold` 中把每个 `item["value"]` 转为 `float` 只用于校验，不改写原值：布尔值、不能转换的值和 `not math.isfinite(number)` 均抛出带索引的 `ValidationError`。

新增对象级 `validate(self, attrs)`：

```python
def validate(self, attrs):
    attrs = super().validate(attrs)
    threshold = attrs.get("threshold", getattr(self.instance, "threshold", []))
    enable_alerts = attrs.get(
        "enable_alerts", getattr(self.instance, "enable_alerts", [])
    )
    query_condition = attrs.get(
        "query_condition", getattr(self.instance, "query_condition", {})
    )
    if not threshold or "threshold" not in enable_alerts:
        return attrs
    if query_condition.get("type") == "pmq" and not attrs.get(
        "calculation_unit", getattr(self.instance, "calculation_unit", "")
    ):
        return attrs
    calculation_unit, threshold_unit = self.get_effective_units(attrs)
    if not calculation_unit or not threshold_unit:
        raise serializers.ValidationError(
            {"threshold_unit": "数值型告警阈值必须配置结果单位和阈值单位"}
        )
    if not UnitConverter.is_known_unit(calculation_unit):
        raise serializers.ValidationError({"calculation_unit": "结果单位无效"})
    if not UnitConverter.is_known_unit(threshold_unit):
        raise serializers.ValidationError({"threshold_unit": "阈值单位无效"})
    if not UnitConverter.is_convertible(threshold_unit, calculation_unit):
        raise serializers.ValidationError(
            {"threshold_unit": f"阈值单位 {threshold_unit} 不能转换为结果单位 {calculation_unit}"}
        )
    return attrs
```

同时在 `UnitConverter` 增加公开纯函数：

```python
@classmethod
def is_known_unit(cls, unit: str) -> bool:
    normalized = cls._normalize_unit(unit)
    if normalized in {"none", "short"}:
        return False
    return any(
        normalized in config["units"]
        for config in UnitConverterConstants.UNIT_SYSTEMS.values()
    ) or normalized in UnitConverterConstants.STANDALONE_UNITS
```

因此本 Task 还需修改 `server/apps/monitor/utils/unit_converter.py`，并在 `server/apps/monitor/tests/test_unit_converter_extra.py` 先增加 `is_known_unit` 的 RED/GREEN 测试，覆盖 `bytes/percent/watts` 为真、`none/short/unknown/枚举 JSON` 为假。

- [ ] **Step 5: 批量 payload 透传阈值单位**

在 `build_bulk_policy_payloads()` 增加：

```python
"threshold_unit": (
    template.get("threshold_unit")
    or template.get("calculation_unit")
    or template.get("metric_unit")
    or ""
),
```

- [ ] **Step 6: 运行模型、序列化和批量 payload 测试**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_unit_converter_extra.py apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_bulk_payload.py -q
```

Expected: PASS，0 failed。

- [ ] **Step 7: 检查迁移漂移并提交**

Run:

```bash
cd server && uv run python manage.py makemigrations --check --dry-run monitor
```

Expected: `No changes detected in app 'monitor'`。

Commit:

```bash
git add server/apps/monitor/models/monitor_policy.py server/apps/monitor/migrations/0046_monitorpolicy_threshold_unit.py server/apps/monitor/serializers/monitor_policy.py server/apps/monitor/utils/unit_converter.py server/apps/monitor/services/policy_bulk.py server/apps/monitor/tests/test_unit_converter_extra.py server/apps/monitor/tests/test_monitor_policy_serializer_validation.py server/apps/monitor/tests/test_policy_bulk_payload.py
git commit -m "新增监控策略阈值单位字段"
```

---

### Task 2: 扫描链路按阈值单位换算临时副本

**Files:**
- Modify: `server/apps/monitor/tasks/services/policy_scan/metric_query.py`
- Modify: `server/apps/monitor/tasks/services/policy_scan/alert_detector.py`
- Test: `server/apps/monitor/tests/test_policy_scan_metric_query_service.py`
- Test: `server/apps/monitor/tests/test_policy_calculate_service.py`

**Interfaces:**
- Consumes: `MonitorPolicy.threshold_unit` 与 `UnitConverter.is_known_unit()`。
- Produces: `MetricQueryService.get_effective_calculation_unit() -> str`。
- Produces: `MetricQueryService.get_effective_threshold_unit() -> str`。
- Produces: `MetricQueryService.convert_thresholds(thresholds: list[dict]) -> list[dict]`，始终返回深拷贝，不修改输入。

- [ ] **Step 1: 为历史回退、GiB→bytes、负数和不可换算组合写失败测试**

扩展测试 `_policy()` 默认值：

```python
threshold_unit="",
```

增加：

```python
class TestConvertThresholds:
    def test_legacy_empty_threshold_unit_uses_calculation_unit(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit=""), {}
        )
        original = [{"level": "critical", "method": ">", "value": 10}]
        converted = svc.convert_thresholds(original)
        assert converted == original
        assert converted is not original

    def test_gibibytes_threshold_converts_to_bytes_without_mutating_policy(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit="gibibytes"), {}
        )
        original = [{"level": "critical", "method": ">", "value": -2}]
        converted = svc.convert_thresholds(original)
        assert converted[0]["value"] == pytest.approx(-2 * 1024**3)
        assert original[0]["value"] == -2

    def test_cross_system_threshold_raises(self):
        svc = MetricQueryService(
            _policy(calculation_unit="bytes", threshold_unit="percent"), {}
        )
        with pytest.raises(BaseAppException, match="不能转换"):
            svc.convert_thresholds(
                [{"level": "critical", "method": ">", "value": 80}]
            )
```

增加一个 `AlertDetector` 或现有 `calculate_alerts` 集成测试：结果 `-20 GiB`、阈值 `< -10 GiB` 时触发；结果 `-5 GiB` 时不触发。测试行为，不 mock `convert_thresholds()`。

- [ ] **Step 2: 运行测试，确认转换接口缺失导致 RED**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_scan_metric_query_service.py apps/monitor/tests/test_policy_calculate_service.py -q
```

Expected: FAIL with `AttributeError: 'MetricQueryService' object has no attribute 'convert_thresholds'`。

- [ ] **Step 3: 实现有效单位回退与阈值深拷贝转换**

在 `MetricQueryService` 中实现：

```python
def get_effective_calculation_unit(self):
    return self.policy.calculation_unit or self.policy.metric_unit or ""

def get_effective_threshold_unit(self):
    return (
        getattr(self.policy, "threshold_unit", "")
        or self.get_effective_calculation_unit()
    )

def convert_thresholds(self, thresholds):
    converted = copy.deepcopy(thresholds)
    if not converted:
        return converted
    source_unit = self.get_effective_threshold_unit()
    target_unit = self.get_effective_calculation_unit()
    if not source_unit or not target_unit:
        return converted
    if not UnitConverter.is_convertible(source_unit, target_unit):
        raise BaseAppException(
            f"策略 {self.policy.id}: 阈值单位 '{source_unit}' 不能转换为结果单位 '{target_unit}'"
        )
    values = [float(item["value"]) for item in converted]
    converted_values = UnitConverter.convert_values(values, source_unit, target_unit)
    for item, value in zip(converted, converted_values):
        item["value"] = value
    return converted
```

`get_display_unit()` 改为展示 `get_effective_calculation_unit()`，不展示阈值单位。

- [ ] **Step 4: 将转换后的阈值接入扫描**

在 `AlertDetector.detect_threshold_alerts()` 中：

```python
thresholds = self.metric_query_service.convert_thresholds(self.policy.threshold)
alert_events, info_events = calculate_alerts(
    self.policy.alert_name,
    df,
    thresholds,
    template_context,
    n=trigger_count,
)
```

不修改 `self.policy.threshold`，确保告警策略快照、详情和通知仍能读取用户输入值及 `threshold_unit`。

- [ ] **Step 5: 运行扫描和计算聚焦测试**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_scan_metric_query_service.py apps/monitor/tests/test_policy_calculate_service.py apps/monitor/tests/test_formula_policy_scan.py -q
```

Expected: PASS，0 failed。

- [ ] **Step 6: 提交扫描链路改动**

```bash
git add server/apps/monitor/tasks/services/policy_scan/metric_query.py server/apps/monitor/tasks/services/policy_scan/alert_detector.py server/apps/monitor/tests/test_policy_scan_metric_query_service.py server/apps/monitor/tests/test_policy_calculate_service.py
git commit -m "按阈值单位换算监控告警条件"
```

---

### Task 3: 前端双单位状态、历史回填与保存 payload

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`
- Test: `web/scripts/monitor-strategy-detail-logic-test.ts`

**Interfaces:**
- Produces: `resolveThresholdUnit({ thresholdUnit, calculationUnit, unitList }): string | null`。
- Produces: `getThresholdUnitOnCalculationUnitChange({ currentThresholdUnit, nextCalculationUnit, unitList }): string | null`。
- Extends: `resolveMetricExpressionUnits()` 返回 `{ metricUnit, calculationUnit, thresholdUnit }`。
- Extends: `buildMetricPreviewPayload()` 接收 `thresholdUnit` 并输出 `threshold_unit`。

- [ ] **Step 1: 为双单位纯函数和 payload 写失败断言**

在逻辑测试中增加：

```typescript
assert.equal(
  resolveThresholdUnit({
    thresholdUnit: null,
    calculationUnit: 'bytes',
    unitList,
  }),
  'bytes'
);

assert.equal(
  resolveThresholdUnit({
    thresholdUnit: 'kilobytes',
    calculationUnit: 'bytes',
    unitList,
  }),
  'kilobytes'
);

assert.equal(
  getThresholdUnitOnCalculationUnitChange({
    currentThresholdUnit: 'milliseconds',
    nextCalculationUnit: 'bytes',
    unitList,
  }),
  'bytes'
);

assert.deepEqual(
  resolveMetricExpressionUnits({
    queryType: 'formula',
    metricUnit: 'bytes',
    calculationUnit: 'percent',
    thresholdUnit: 'percent',
  }),
  { metricUnit: '', calculationUnit: 'percent', thresholdUnit: 'percent' }
);
```

扩展预览 payload 断言：`metric_unit === ''`、`calculation_unit === 'percent'`、`threshold_unit === 'percent'`。

- [ ] **Step 2: 运行前端逻辑测试，确认新接口缺失导致 RED**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
```

Expected: FAIL，错误为新 helper 未导出或 `thresholdUnit` 参数/返回字段缺失。

- [ ] **Step 3: 实现阈值单位解析纯函数**

复用 `getThresholdUnitOptions()`，不复制单位体系判断：

```typescript
export const resolveThresholdUnit = ({
  thresholdUnit,
  calculationUnit,
  unitList
}: {
  thresholdUnit: string | null | undefined;
  calculationUnit: string | null | undefined;
  unitList: UnitListItem[];
}): string | null => {
  if (!calculationUnit || !unitList.length) return thresholdUnit || null;
  const optionIds = new Set(
    getThresholdUnitOptions({
      unitList,
      metricUnit: calculationUnit,
      isEnumMetric: false
    }).map((item) => item.unit_id)
  );
  return thresholdUnit && optionIds.has(thresholdUnit)
    ? thresholdUnit
    : calculationUnit;
};
```

`getThresholdUnitOnCalculationUnitChange()` 调用同一 helper；新结果单位为空时返回 `null`，合法同体系旧值保留，跨体系旧值回退新结果单位。

- [ ] **Step 4: 拆分页面状态并实现历史回填**

把当前承担结果单位语义的 `thresholdUnit` state 重命名为 `calculationUnit`，再新增真正的：

```typescript
const [thresholdUnit, setThresholdUnit] = useState<string | null>(null);
```

详情回填规则：

```typescript
const restoredCalculationUnit = restoreCalculationUnitState(data.calculation_unit);
setCalculationUnit(restoredCalculationUnit);
setThresholdUnit(
  restoreCalculationUnitState(data.threshold_unit) || restoredCalculationUnit
);
```

单位库加载或结果单位变化时，通过 `resolveThresholdUnit()` 校准阈值单位；在 `unitList=[]` 阶段不得覆盖历史值。切换单指标/公式时，现有 calculation-unit helper 只更新结果单位，随后用 `getThresholdUnitOnCalculationUnitChange()` 决定阈值单位。

- [ ] **Step 5: 保存和预览分别透传两个单位**

扩展：

```typescript
resolveMetricExpressionUnits({
  queryType,
  metricUnit,
  calculationUnit,
  thresholdUnit
})
```

公式返回 `metricUnit: ''`，但保留两个独立单位；单指标保留原始 `metricUnit`。页面保存：

```typescript
params.metric_unit = policyUnits.metricUnit;
params.calculation_unit = policyUnits.calculationUnit;
params.threshold_unit = policyUnits.thresholdUnit;
```

`MetricPreview` 与 `buildMetricPreviewPayload` 同样输出三个字段，图表仍使用 `calculationUnit` 展示，不使用 `thresholdUnit`。

- [ ] **Step 6: 运行逻辑测试与触及文件 lint**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
cd web && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' 'scripts/monitor-strategy-detail-logic-test.ts'
```

Expected: 两条命令均退出 0。

- [ ] **Step 7: 提交双单位数据流**

```bash
git add 'web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' 'web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts' 'web/src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' web/scripts/monitor-strategy-detail-logic-test.ts
git commit -m "拆分监控结果单位与阈值单位状态"
```

---

### Task 4: 阈值交互支持公式单位选择和负数

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`

**Interfaces:**
- Consumes: `calculationUnit` 作为阈值单位候选基准，`thresholdUnit` 作为当前选择。
- Produces: `shouldShowThresholdUnitSelector({ isTrap, isEnumMetric }): boolean`，公式数值策略返回 `true`。

- [ ] **Step 1: 写公式模式显示单位选择器的失败断言**

把旧断言“公式模式返回 false”改为：

```typescript
assert.equal(
  shouldShowThresholdUnitSelector({ isTrap: false, isEnumMetric: false }),
  true
);
assert.equal(
  shouldShowThresholdUnitSelector({ isTrap: false, isEnumMetric: true }),
  false
);
assert.equal(
  shouldShowThresholdUnitSelector({ isTrap: true, isEnumMetric: false }),
  false
);
```

- [ ] **Step 2: 运行逻辑测试，确认旧公式隐藏行为导致 RED**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
```

Expected: FAIL，公式数值策略的实际值仍为 `false` 或函数签名不匹配。

- [ ] **Step 3: 调整表单属性和候选过滤基准**

`AlertConditionsFormProps` 新增 `calculationUnit: string | null`。候选统一使用结果单位：

```typescript
const filteredUnitOptions = useMemo(
  () => getThresholdUnitOptions({
    unitList,
    metricUnit: calculationUnit,
    isEnumMetric
  }),
  [unitList, calculationUnit, isEnumMetric]
);
```

公式模式不再隐藏单位选择器；Trap 判断由现有外层 `isTrap(getFieldValue)` 保持不渲染整个阈值区，helper 仍接受显式 `isTrap` 便于纯函数测试。

- [ ] **Step 4: 允许负数阈值并补充说明**

从 `ThresholdList` 的数值 `InputNumber` 删除：

```tsx
min={0}
```

保留 `value={item.value}`、`addonAfter={getUnitLabel()}` 和原有空值处理。阈值单位标题旁使用现有 Tooltip/文案组件增加：

```text
阈值单位可在结果单位的同类单位中选择，系统将在比较前自动换算。
```

在 `web/src/app/monitor/locales/zh.json` 与 `en.json` 的 `events` 对象新增：

```json
"thresholdUnitHelp": "阈值单位可在结果单位的同类单位中选择，系统将在比较前自动换算。"
```

```json
"thresholdUnitHelp": "Choose a threshold unit from the result unit's compatible unit family. Values are converted before comparison."
```

JSX 通过 `t('monitor.events.thresholdUnitHelp')` 读取，禁止硬编码。

- [ ] **Step 5: 运行前端聚焦验证**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
cd web && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx' 'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' 'scripts/monitor-strategy-detail-logic-test.ts'
```

Expected: PASS，0 errors。

- [ ] **Step 6: 提交交互改动**

```bash
git add 'web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx' 'web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx' 'web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' web/scripts/monitor-strategy-detail-logic-test.ts web/src/app/monitor/locales/zh.json web/src/app/monitor/locales/en.json
git commit -m "支持负数监控阈值与独立单位选择"
```

---

### Task 5: 全链路回归、迁移与规格核对

**Files:**
- Verify only; only fix failures caused by Tasks 1-4 in already listed files.

**Interfaces:**
- Consumes: 前四个 Task 的所有接口。
- Produces: 可交付的后端字段、扫描换算和前端双单位闭环。

- [ ] **Step 1: 运行后端监控单位与策略聚焦测试**

Run:

```bash
cd server && uv run pytest \
  apps/monitor/tests/test_unit_converter_extra.py \
  apps/monitor/tests/test_monitor_policy_serializer_validation.py \
  apps/monitor/tests/test_policy_bulk_payload.py \
  apps/monitor/tests/test_policy_scan_metric_query_service.py \
  apps/monitor/tests/test_policy_calculate_service.py \
  apps/monitor/tests/test_formula_policy_scan.py \
  apps/monitor/tests/test_policy_preview_service.py -q
```

Expected: PASS，0 failed。

- [ ] **Step 2: 运行 Django 迁移门禁**

Run:

```bash
cd server && uv run python manage.py makemigrations --check --dry-run monitor
```

Expected: `No changes detected in app 'monitor'`。

- [ ] **Step 3: 运行前端逻辑、lint 与 TypeScript 门禁**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
cd web && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' 'src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx' 'scripts/monitor-strategy-detail-logic-test.ts'
cd web && NEXTAPI_INSTALL_APP=monitor pnpm type-check
```

Expected: 逻辑测试和触及文件 ESLint 退出 0；TypeScript 退出 0。若全局基线错误重现，只记录与本次触及文件无关的既有错误，不修改任务外文件。

- [ ] **Step 4: 按规格逐项核对行为**

逐项确认：

```text
[ ] a-b 可配置 < -10 GiB
[ ] a/b*100 默认结果单位和阈值单位均为 %
[ ] bytes 结果可选择 GiB 阈值并在扫描前换算
[ ] bytes 结果不能保存 percent 阈值
[ ] 历史空 threshold_unit 回退 calculation_unit
[ ] 枚举指标与 Trap 不展示单位选择器
[ ] 预览图表展示 calculation_unit，不展示 threshold_unit
[ ] 保存 payload 同时包含 metric_unit/calculation_unit/threshold_unit
```

- [ ] **Step 5: 检查最终 diff 与提交状态**

Run:

```bash
git diff --check
git status --short
git log -5 --oneline
```

Expected: 无未提交的任务文件，diff 无空白错误，提交仅包含本计划列出的相关文件。

- [ ] **Step 6: 记录修复并准备交付**

在 projectmem 中依次记录本次成功尝试和确认修复，摘要必须包含：独立 `threshold_unit`、负数阈值、同体系换算、历史回退以及实际通过的测试命令。
