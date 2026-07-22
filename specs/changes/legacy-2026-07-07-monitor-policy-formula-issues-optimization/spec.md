# Historical Superpowers change: 2026-07-07-monitor-policy-formula-issues-optimization

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-07-monitor-policy-formula-issues-optimization.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复监控告警多指标公式的指标编辑器配置阻断、anchor 规则不一致、公式预览 OR 资产过滤错误，并补齐 focused 验证。

**Architecture:** 后端以 `queries[0].ref` 作为公式 anchor，并给公式编译器增加可选的按变量公共过滤条件，扫描路径默认不传公共过滤条件。前端停止在公式预览 payload 中追加实例过滤，编辑器改为稳定 grid 面板布局，仍沿用现有状态和 Ant Design 控件。

**Tech Stack:** Python 3.12、Django 4.2、pytest、Next.js 16、React 19、TypeScript、Ant Design、pnpm。

---

## 文件结构

- Modify: `server/apps/monitor/expression/validators.py`
  - 负责公式结构校验、anchor 选择、非 anchor group_by 子集校验。
- Modify: `server/apps/monitor/expression/compiler.py`
  - 负责把公式 AST 编译成 MetricsQL；新增 `base_filters_by_ref` 可选参数。
- Modify: `server/apps/monitor/expression/query.py`
  - 负责加载 Metric 并构造 `FormulaCompiler`；新增 `base_filters_by_ref` 透传参数。
- Modify: `server/apps/monitor/services/policy_preview.py`
  - 负责策略预览；公式预览时在后端按每个指标构造实例公共过滤条件。
- Modify: `server/apps/monitor/tests/test_formula_validator.py`
  - 增加 anchor 固定为第一行指标的测试。
- Modify: `server/apps/monitor/tests/test_formula_compiler.py`
  - 增加表达式变量顺序不改变最终 group_by 的编译测试。
- Modify: `server/apps/monitor/tests/test_formula_policy_preview.py`
  - 增加 OR 条件 + 预览资产过滤测试。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`
  - 删除公式预览前端 append 实例过滤逻辑；保留指标存在性校验。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
  - 重排指标编辑器面板、指标行、条件行、新增指标按钮、公式行。
- Modify: `web/scripts/monitor-policy-formula-payload-test.ts`
  - 更新公式预览 payload 断言；增加 `b / a` 与新增指标相关断言。

## Task 1: 后端 anchor 规则固定为第一行指标

**Files:**
- Modify: `server/apps/monitor/tests/test_formula_validator.py`
- Modify: `server/apps/monitor/tests/test_formula_compiler.py`
- Modify: `server/apps/monitor/expression/validators.py`

- [ ] **Step 1: 写 validator 失败测试**

在 `server/apps/monitor/tests/test_formula_validator.py` 追加：

```python
def test_validate_formula_uses_first_query_as_anchor_not_expression_order():
    payload = formula(
        expression="b / a * 100",
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    )

    result = validate_formula_condition(payload)

    assert result.anchor_ref == "a"
    assert result.warnings == []
```

- [ ] **Step 2: 运行 validator 测试确认失败**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_validator.py::test_validate_formula_uses_first_query_as_anchor_not_expression_order -q
```

Expected: FAIL，错误包含 `指标 a 包含锚点外额外维度` 或 `assert 'b' == 'a'`。

- [ ] **Step 3: 写 compiler 失败测试**

在 `server/apps/monitor/tests/test_formula_compiler.py` 追加：

```python
def test_compile_formula_result_group_by_uses_first_query_when_expression_starts_with_subset():
    metrics = {
        1: MetricObj(1, "error_count{__$labels__}"),
        2: MetricObj(2, "request_count{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "b / a * 100",
        "queries": [
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert compiled.anchor_ref == "a"
    assert compiled.group_by == ["instance_id", "status"]
    assert "/ on(instance_id) group_right" in compiled.query
```

- [ ] **Step 4: 运行 compiler 测试确认失败**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_compiler.py::test_compile_formula_result_group_by_uses_first_query_when_expression_starts_with_subset -q
```

Expected: FAIL，错误来自 validator 或最终 group_by 不等于 `["instance_id", "status"]`。

- [ ] **Step 5: 实现 anchor 规则**

修改 `server/apps/monitor/expression/validators.py` 中 anchor 选择和循环范围：

```python
    anchor_ref = str(queries[0].get("ref") or "")
    anchor_group_by = set(by_ref[anchor_ref].get("group_by") or [])
    warnings: list[dict] = []
    for ref in unique_variables:
        if ref == anchor_ref:
            continue
        group_by = set(by_ref[ref].get("group_by") or [])
        extra = sorted(group_by - anchor_group_by)
        if extra:
            raise FormulaValidationError(f"指标 {ref} 包含锚点外额外维度：{', '.join(extra)}")
        if group_by != anchor_group_by and "instance_id" not in group_by:
            warnings.append(
                {
                    "code": "FORMULA_DIMENSION_REUSE",
                    "message": f"指标 {ref} 将按 {', '.join(sorted(group_by))} 对齐，并跨缺失维度复用数据",
                }
            )
```

保留 `unique_variables` 对不存在变量、未使用变量、至少两个变量的校验。

- [ ] **Step 6: 运行后端公式 validator/compiler focused 测试**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_validator.py apps/monitor/tests/test_formula_compiler.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 1**

Run:

```bash
git add server/apps/monitor/expression/validators.py server/apps/monitor/tests/test_formula_validator.py server/apps/monitor/tests/test_formula_compiler.py
git commit -m "fix(monitor): 统一公式锚点规则"
```

Expected: commit succeeds。

## Task 2: 后端公式预览使用公共资产过滤

**Files:**
- Modify: `server/apps/monitor/tests/test_formula_policy_preview.py`
- Modify: `server/apps/monitor/expression/compiler.py`
- Modify: `server/apps/monitor/expression/query.py`
- Modify: `server/apps/monitor/services/policy_preview.py`

- [ ] **Step 1: 写 OR 资产过滤失败测试**

在 `server/apps/monitor/tests/test_formula_policy_preview.py` 追加：

```python
@pytest.mark.django_db
def test_preview_formula_applies_instance_filter_to_each_or_branch(mocker):
    obj = MonitorObject.objects.create(name="FormulaPreviewOrObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaPreviewOrPlugin")
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
        instance_id_keys=["node"],
    )
    captured = {}
    api = mocker.patch("apps.monitor.tasks.utils.policy_methods.VictoriaMetricsAPI")

    def fake_query_range(query, *args):
        captured["query"] = query
        return {"status": "success", "data": {"result": []}}

    api.return_value.query_range.side_effect = fake_query_range

    svc = PolicyPreviewService(
        {
            "query_condition": {
                "type": "formula",
                "result_name": "错误率",
                "expression": "a / b",
                "queries": [
                    {
                        "ref": "a",
                        "metric_id": a.id,
                        "filter": [
                            {"name": "service", "method": "=", "value": "checkout"},
                            {"logic": "or", "name": "status", "method": "=", "value": "500"},
                        ],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id", "status"],
                    },
                    {
                        "ref": "b",
                        "metric_id": b.id,
                        "filter": [
                            {"name": "service", "method": "=", "value": "checkout"},
                            {"logic": "or", "name": "status", "method": "=", "value": "200"},
                        ],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id"],
                    },
                ],
            },
            "period": {"type": "min", "value": 5},
            "algorithm": "avg_over_time",
            "preview": {"instance_id_values": ["host.1"]},
        }
    )

    svc.preview()

    assert '(a_metric{instance_id=~"host\\\\.1",service="checkout"}) or (a_metric{instance_id=~"host\\\\.1",status="500"})' in captured["query"]
    assert '(b_metric{node=~"host\\\\.1",service="checkout"}) or (b_metric{node=~"host\\\\.1",status="200"})' in captured["query"]
```

- [ ] **Step 2: 运行 OR 资产过滤测试确认失败**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_policy_preview.py::test_preview_formula_applies_instance_filter_to_each_or_branch -q
```

Expected: FAIL，captured query 中实例过滤只出现在第二个 OR 分支，或完全缺少公式预览实例过滤。

- [ ] **Step 3: 给 FormulaCompiler 增加可选公共过滤参数**

修改 `server/apps/monitor/expression/compiler.py`：

```python
class FormulaCompiler:
    def __init__(
        self,
        query_condition: dict,
        metrics_by_id: dict[int, object],
        base_filters_by_ref: dict[str, list[dict]] | None = None,
    ):
        self.query_condition = query_condition
        self.metrics_by_id = metrics_by_id
        self.base_filters_by_ref = base_filters_by_ref or {}
        self.validation = validate_formula_condition(query_condition)
        self.inputs = {item["ref"]: item for item in query_condition["queries"]}
        self.anchor_group_by = self.inputs[self.validation.anchor_ref]["group_by"]
```

并修改 `_compile_variable`：

```python
    def _compile_variable(self, ref: str) -> _CompiledNode:
        item = self.inputs[ref]
        metric = self.metrics_by_id[item["metric_id"]]
        base_query = compile_filter_to_query(
            metric.query,
            item.get("filter") or [],
            base_filters=self.base_filters_by_ref.get(ref) or [],
        )
        group_by = item.get("group_by") or []
        group_by_clause = ",".join(group_by)
        return _CompiledNode(query=f"{item['group_algorithm']}({base_query}) by ({group_by_clause})", group_by=list(group_by))
```

- [ ] **Step 4: 透传 build_formula_query 参数**

修改 `server/apps/monitor/expression/query.py`：

```python
def build_formula_query(
    query_condition: dict,
    base_filters_by_ref: dict[str, list[dict]] | None = None,
) -> CompiledFormula:
    try:
        validate_formula_condition(query_condition)
    except FormulaError as exc:
        raise BaseAppException(str(exc)) from exc

    metric_ids = [item["metric_id"] for item in query_condition.get("queries") or []]
    metrics = Metric.objects.filter(id__in=metric_ids)
    by_id = {metric.id: metric for metric in metrics}
    missing = [metric_id for metric_id in metric_ids if metric_id not in by_id]
    if missing:
        raise BaseAppException(f"metric does not exist [{missing[0]}]")
    try:
        return FormulaCompiler(query_condition, by_id, base_filters_by_ref=base_filters_by_ref).compile()
    except FormulaError as exc:
        raise BaseAppException(str(exc)) from exc
```

- [ ] **Step 5: 在 PolicyPreviewService 构造公式公共过滤条件**

修改 `server/apps/monitor/services/policy_preview.py`，新增 helper：

```python
    def _build_formula_instance_filters(self, query_condition):
        preview = self._require_dict("preview")
        values = preview.get("instance_id_values")
        if not values:
            raise BaseAppException("preview.instance_id_values is required")

        metric_ids = [item["metric_id"] for item in query_condition.get("queries") or []]
        metrics = Metric.objects.filter(id__in=metric_ids)
        metrics_by_id = {metric.id: metric for metric in metrics}

        filters_by_ref = {}
        for item in query_condition.get("queries") or []:
            metric = metrics_by_id.get(item["metric_id"])
            if not metric:
                raise BaseAppException(f"metric does not exist [{item['metric_id']}]")
            filters = []
            for key, value in zip(getattr(metric, "instance_id_keys", []) or [], values):
                filters.append(
                    {
                        "name": key,
                        "method": "=~",
                        "value": self._escape_regex_value(value),
                    }
                )
            filters_by_ref[item["ref"]] = filters
        return filters_by_ref
```

修改公式预览分支：

```python
        if query_condition.get("type") == "formula":
            compiled_formula = build_formula_query(
                query_condition,
                base_filters_by_ref=self._build_formula_instance_filters(query_condition),
            )
            metric_query = compiled_formula.query
            group_by = compiled_formula.group_by
            self.warnings.extend(compiled_formula.warnings)
            query = build_formula_policy_query(algorithm, metric_query, step)
```

- [ ] **Step 6: 运行公式预览测试**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_policy_preview.py -q
```

Expected: PASS。

- [ ] **Step 7: 运行后端公式 focused 测试**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_expression_parser.py apps/monitor/tests/test_formula_condition_compiler.py apps/monitor/tests/test_formula_validator.py apps/monitor/tests/test_formula_compiler.py apps/monitor/tests/test_formula_policy_preview.py apps/monitor/tests/test_formula_policy_scan.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交 Task 2**

Run:

```bash
git add server/apps/monitor/expression/compiler.py server/apps/monitor/expression/query.py server/apps/monitor/services/policy_preview.py server/apps/monitor/tests/test_formula_policy_preview.py
git commit -m "fix(monitor): 修正公式预览资产过滤"
```

Expected: commit succeeds。

## Task 3: 前端 payload 不再为公式预览追加实例过滤

**Files:**
- Modify: `web/scripts/monitor-policy-formula-payload-test.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`

- [ ] **Step 1: 更新前端 payload 失败断言**

修改 `web/scripts/monitor-policy-formula-payload-test.ts` 中 `formulaPreviewPayload` 断言，把公式预览 filter 断言改成不包含实例过滤：

```typescript
assert.equal(formulaPreviewPayload?.query_condition.type, 'formula');
if (formulaPreviewPayload?.query_condition.type === 'formula') {
  assert.deepEqual(formulaPreviewPayload.query_condition.queries[0].filter, [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'and', name: 'status', method: '=~', value: '5..' }
  ]);
  assert.deepEqual(formulaPreviewPayload.query_condition.queries[1].filter, [
    { name: 'service', method: '=', value: 'checkout' },
    { logic: 'or', name: 'status', method: '=', value: '200' }
  ]);
}
```

追加表达式顺序断言：

```typescript
const reversedExpressionPayload = buildMetricExpressionQueryCondition({
  mode: 'formula',
  resultName: 'HTTP 5xx 错误率',
  expression: 'b / a * 100',
  rows: formulaRows
});

assert.equal(reversedExpressionPayload.type, 'formula');
assert.equal(reversedExpressionPayload.expression, 'b / a * 100');
assert.equal(reversedExpressionPayload.queries[0].ref, 'a');
assert.deepEqual(reversedExpressionPayload.queries[0].group_by, ['instance_id', 'status']);
```

- [ ] **Step 2: 运行前端脚本确认失败**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload
```

Expected: FAIL，旧实现仍把实例过滤追加到公式 query filters。

- [ ] **Step 3: 删除公式预览 append 实例过滤逻辑**

修改 `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`：

删除 `buildPreviewInstanceFilters` 和 `appendFormulaPreviewInstanceFilters`。

保留 metric 查找 helper：

```typescript
const findMetricForRow = (
  row: MetricExpressionRow,
  metrics: MetricItem[]
): MetricItem | undefined =>
  metrics.find(
    (item) => item.id === row.metricId || item.name === row.metricName
  );
```

在 `buildMetricExpressionPreviewPayload` 中校验公式每个指标已加载：

```typescript
  if (isFormula) {
    queryCondition.queries.forEach((query, index) => {
      const row = rows.find((item) => item.ref === query.ref) || rows[index];
      const metric = row ? findMetricForRow(row, metrics) : undefined;
      if (!metric) {
        throw new Error(METRIC_NOT_READY_MESSAGE);
      }
    });
  }
```

并设置：

```typescript
  const previewQueryCondition = queryCondition;
```

保留单指标预览 payload 不变。

- [ ] **Step 4: 运行前端脚本确认通过**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload
```

Expected: PASS。

- [ ] **Step 5: 提交 Task 3**

Run:

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/formulaExpressionUtils.ts web/scripts/monitor-policy-formula-payload-test.ts
git commit -m "fix(monitor): 调整公式预览 payload 构建"
```

Expected: commit succeeds。

## Task 4: 重排指标编辑器 UI

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`

- [ ] **Step 1: 定义本地展示 helper**

在 `MetricExpressionEditor` 组件内、`getRowGroupByOptions` 后新增：

```typescript
  const translateWithFallback = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const groupMethodOptions = groupMethods.map((item) => ({
    label: `${item.label.toString().toLowerCase()} by`,
    value: item.value
  }));
```

- [ ] **Step 2: 替换外层面板容器**

把 `return (` 内最外层容器和标题栏替换为下面结构。`<div className="flex flex-col gap-3 p-3">` 的内部内容由 Step 3、Step 4、Step 5 组成。

```tsx
  return (
    <div className="overflow-hidden rounded-md border border-[#b8d4ff] bg-[#f8fbff]">
      <div className="flex items-center gap-2 border-b border-[#dbe8ff] bg-[#f3f8ff] px-3 py-2">
        <span className="text-sm font-medium text-[var(--color-text-1)]">
          指标编辑器
        </span>
        {showFormula && (
          <span className="rounded border border-[#9fc4ff] bg-[#eaf3ff] px-2 py-[2px] text-xs text-[var(--color-primary)]">
            表达式
          </span>
        )}
      </div>
      <div className="flex flex-col gap-3 p-3">
      </div>
    </div>
  );
```

- [ ] **Step 3: 替换指标卡片主行 JSX**

在 `<div className="flex flex-col gap-3 p-3">` 内先放入下面的 `rows.map`。每个指标卡片主行之后，紧接 Step 4 的条件行内容，然后关闭指标卡片。

```tsx
        {rows.map((row, rowIndex) => (
          <div
            key={row.ref}
            className="rounded-md border border-[#d8e4f7] bg-[var(--color-bg-1)] p-3"
          >
            <div className="grid grid-cols-[24px_minmax(220px,1fr)_120px_minmax(180px,1fr)_34px] items-center gap-2">
              <span className="inline-flex h-8 w-6 items-center justify-center rounded border border-[#b8d4ff] bg-[#eef6ff] font-mono text-sm font-semibold text-[var(--color-primary)]">
                {row.ref}
              </span>
              <Select
                allowClear
                className="min-w-0"
                showSearch
                value={row.metricName}
                loading={metricsLoading}
                placeholder={t('monitor.metric')}
                options={metricOptions}
                filterOption={(input, option) =>
                  (option?.label || '')
                    .toString()
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
                onChange={(value) => handleMetricChange(rowIndex, value)}
              />
              <Select
                className="min-w-0"
                value={row.groupAlgorithm || 'avg'}
                placeholder={t('monitor.events.groupAggregationMethod')}
                options={groupMethodOptions}
                onChange={(value) =>
                  updateRow(rowIndex, { groupAlgorithm: value })
                }
              />
              <Select
                allowClear
                className="min-w-0"
                maxTagCount="responsive"
                mode="multiple"
                showSearch
                value={row.groupBy}
                placeholder={t('monitor.events.groupDimension')}
                options={getRowGroupByOptions(row)}
                onChange={(value) =>
                  updateRow(rowIndex, { groupBy: sanitizeGroupBy(value) })
                }
              />
              {rows.length > 1 ? (
                <Tooltip title={t('common.delete')}>
                  <Button
                    aria-label={t('common.delete')}
                    className="h-8 w-8"
                    icon={<CloseOutlined />}
                    onClick={() => removeMetricRow(rowIndex)}
                  />
                </Tooltip>
              ) : (
                <span />
              )}
            </div>
          </div>
        ))}
```

删除孤立的 `by` 文本。

- [ ] **Step 4: 替换条件行 JSX**

在指标卡片内主行后放入：

```tsx
            <div className="ml-8 mt-2 flex flex-col gap-2">
              {row.filters.map((filter, filterIndex) => (
                <div
                  className="grid grid-cols-[72px_minmax(150px,1fr)_88px_minmax(150px,1fr)_34px] items-center gap-2"
                  key={`${row.ref}-${filterIndex}`}
                >
                  {filterIndex > 0 ? (
                    <Select
                      className="min-w-0"
                      value={filter.logic || 'and'}
                      options={[
                        { label: 'AND', value: 'and' },
                        { label: 'OR', value: 'or' }
                      ]}
                      onChange={(value) =>
                        updateCondition(rowIndex, filterIndex, {
                          logic: value
                        })
                      }
                    />
                  ) : (
                    <span className="text-xs text-[var(--color-text-3)]">
                      {t('monitor.events.conditionDimension')}
                    </span>
                  )}
                  <Select
                    className="min-w-0"
                    showSearch
                    value={filter.name}
                    placeholder={t('monitor.label')}
                    options={(labelsByRef[row.ref] || []).map((item) => ({
                      label: item,
                      value: item
                    }))}
                    onChange={(value) =>
                      updateCondition(rowIndex, filterIndex, { name: value })
                    }
                  />
                  <Select
                    className="min-w-0"
                    value={filter.method}
                    placeholder={t('monitor.term')}
                    options={conditionMethods.map((item) => ({
                      label: item.name,
                      value: item.id
                    }))}
                    onChange={(value) =>
                      updateCondition(rowIndex, filterIndex, { method: value })
                    }
                  />
                  <Input
                    className="min-w-0"
                    value={filter.value}
                    placeholder={t('monitor.value')}
                    onChange={(event) =>
                      updateCondition(rowIndex, filterIndex, {
                        value: event.target.value
                      })
                    }
                  />
                  <Tooltip title={t('common.delete')}>
                    <Button
                      aria-label={t('common.delete')}
                      className="h-8 w-8"
                      icon={<CloseOutlined />}
                      onClick={() => removeCondition(rowIndex, filterIndex)}
                    />
                  </Tooltip>
                </div>
              ))}
              <Button
                className="w-fit"
                icon={<PlusOutlined />}
                onClick={() => addCondition(rowIndex)}
              >
                {t('monitor.addCondition')}
              </Button>
            </div>
```

- [ ] **Step 5: 替换新增指标按钮和公式行**

在 `rows.map` 后放入：

```tsx
        <Button className="w-fit" icon={<PlusOutlined />} onClick={addMetricRow}>
          {translateWithFallback('monitor.events.addMetric', '添加指标')}
        </Button>
        {showFormula && (
          <div className="grid grid-cols-[34px_220px_20px_minmax(220px,1fr)] items-center gap-2 border-t border-[#dbe8ff] pt-3">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded border border-[#b8d4ff] bg-[#eef6ff] font-mono text-xs font-semibold text-[var(--color-primary)]">
              fx
            </span>
            <Input
              className="min-w-0"
              value={resultName}
              placeholder={t('monitor.events.formulaResultName')}
              onChange={(event) => onResultNameChange(event.target.value)}
            />
            <span className="text-center text-[var(--color-text-3)]">=</span>
            <Input
              className="min-w-0"
              value={expression}
              placeholder="a / b * 100"
              onChange={(event) => onExpressionChange(event.target.value)}
            />
          </div>
        )}
```

- [ ] **Step 6: 运行编辑器 eslint**

Run:

```bash
cd web && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx'
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 4**

Run:

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/metricExpressionEditor.tsx
git commit -m "fix(monitor): 优化公式指标编辑器布局"
```

Expected: commit succeeds。

## Task 5: 回归验证与收口

**Files:**
- Read only: touched files from Tasks 1-4.

- [ ] **Step 1: 运行后端公式 focused 测试**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=':memory:' uv run pytest apps/monitor/tests/test_formula_expression_parser.py apps/monitor/tests/test_formula_condition_compiler.py apps/monitor/tests/test_formula_validator.py apps/monitor/tests/test_formula_compiler.py apps/monitor/tests/test_formula_policy_preview.py apps/monitor/tests/test_formula_policy_scan.py apps/monitor/tests/test_monitor_policy_serializer_validation.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行前端 payload 脚本**

Run:

```bash
cd web && pnpm test:monitor-policy-formula-payload
```

Expected: PASS。

- [ ] **Step 3: 运行 focused eslint**

Run:

```bash
cd web && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' 'src/app/monitor/(pages)/event/strategy/detail/page.tsx'
```

Expected: PASS。

- [ ] **Step 4: 手工检查 UI**

Run:

```bash
cd web && pnpm dev
```

Open the strategy create page in browser and check:

- 单指标空态：指标编辑器控件无遮挡，无横向溢出。
- 点击“添加指标”：出现第二个指标行，变量 badge 为 `b`，按钮显示“添加指标”。
- 公式行：显示 `fx`、结果名称、`=`、表达式输入框。
- 条件行：第一行显示“条件”，第二行显示 AND/OR Select。
- 删除第二个指标：布局不塌陷，表达式引用缺失变量时表单校验提示清晰。

Expected: all checks pass。

- [ ] **Step 5: 记录已知非本功能阻塞**

如果执行 `cd web && pnpm type-check`，仍可能因既有 stories 缺失 `ops-analysis` 模块失败：

- `src/stories/ops-analysis-event-table.stories.tsx`
- `src/stories/ops-analysis-widgets.stories.tsx`

本计划不要求修复该既有问题。最终汇报需明确是否运行了 full type-check，以及结果是否仍为既有阻塞。

- [ ] **Step 6: 最终提交验证说明**

Run:

```bash
git status --short
```

Expected: only intentional files changed, no unrelated historical dirty files staged.

If there are verification-only changes, do not commit them. If all implementation commits already exist, no extra commit is required.

## Self-Review

- Spec coverage: UI 阻断由 Task 4 覆盖；anchor 规则由 Task 1 覆盖；预览 OR 资产过滤由 Task 2 和 Task 3 覆盖；focused 验证由 Task 5 覆盖；单指标兼容由 Task 2/3 的默认参数和 Task 5 focused 测试覆盖。
- Placeholder scan: 本计划没有占位章节或空泛步骤；每个代码修改任务都有具体路径、代码片段、运行命令和预期结果。
- Type consistency: 后端新增参数名统一为 `base_filters_by_ref: dict[str, list[dict]] | None`；前端函数继续使用现有 `MetricExpressionRow`、`MetricItem`、`FormulaQueryCondition` 类型，不新增跨文件类型。

## specs: 2026-07-07-monitor-policy-formula-issues-optimization-design.md

## 背景

多指标公式功能已合入 master。审查发现三类需要发布前收口的问题：

- 指标编辑器布局错乱，新增/配置指标时控件挤压，影响策略配置主流程。
- 公式 anchor 规则前后端不一致：后端按表达式首变量，前端按第一行指标，可能导致预览/保存语义不一致。
- 公式预览追加资产过滤时，把实例过滤直接追加到 filter 尾部；遇到 OR 条件时，实例过滤只作用在最后一个 OR 分支，预览可能混入非选中资产数据。

本次优化只覆盖多指标公式相关路径，保持单指标 `query_condition.type=metric` 旧结构和旧行为不变，不新增普通策略 PromQL 创建入口，Trap PMQ 旧入口保留。

## 目标

1. 让指标编辑器在新增、删除、空指标、双指标公式等状态下布局稳定，可完成策略配置。
2. 统一公式最终维度来源，避免表达式变量顺序改变 anchor。
3. 让公式预览资产过滤与单指标预览的 AND/OR 语义一致。
4. 补齐 focused 测试，覆盖本次审查发现的风险场景。

## 非目标

- 不重做策略创建页面整体流程。
- 不调整告警扫描调度、通知、恢复逻辑。
- 不引入新的 PromQL/MetricQL 编辑入口。
- 不处理主工作区已有历史脏文件。

## 方案选择

采用完整收口方案：同时修 UI 阻断、anchor 规则、公式预览资产过滤，并补测试。

不采用只修 UI 的临时方案，因为 anchor 与预览过滤会继续留下隐性错误；不采用只修后端语义的方案，因为编辑器布局已经影响主流程配置。

## UI 设计

调整 `MetricExpressionEditor` 的结构和样式，保持现有状态字段不变。

指标编辑器面板：

- 外层显示轻量面板，标题栏包含“指标编辑器”和“表达式”标签。
- 面板宽度跟随表单区域，内部控件不得横向溢出。
- 保持 6px 左右圆角和现有 BK-Lite 表单视觉，不引入新的设计系统。

指标行：

- 每个指标用一张轻量行卡片承载。
- 主行使用稳定 grid：变量 badge、指标 Select、聚合 Select、group_by Select、删除按钮。
- 指标 Select 和 group_by Select 使用明确的 `minmax` 约束；窄宽度时允许自然换行，不遮挡按钮。
- 聚合 Select 展示为 `sum by` / `avg by` 这类完整语义，避免旁边再放一个孤立 `by` 文本导致错位。
- 变量 badge 使用窄蓝色标签，显示 `a`、`b`、`m27` 等变量名。

条件行：

- 条件行缩进到指标主行下方。
- 第一条显示“条件”，后续显示 AND/OR Select。
- 条件行列为：逻辑/标题、label、operator、value、删除按钮。
- `添加条件` 按钮放在条件列表下方，左侧与条件内容对齐。

新增指标与公式行：

- `添加指标` 按钮放在指标卡片列表下方，使用中文文案和加号图标。
- 修复文案 key 未解析时显示 `monitor.events.addMetric` 的问题；优先确认 i18n namespace，必要时使用当前页面已生效的 key。
- 公式模式下底部固定显示 `fx` 行：`fx badge`、`result_name`、`=`、`expression`。
- 删除指标后，表达式引用不存在变量时继续给出校验错误，不自动猜测替换表达式。

## Anchor 规则

统一以 `query_condition.queries[0].ref` 作为公式 anchor。

具体规则：

- 后端 `validate_formula_condition` 不再用表达式中第一个出现的变量作为 anchor。
- 后端校验非 anchor 指标的 `group_by` 必须是 anchor `group_by` 的子集。
- 后端编译完成后，最终公式结果 `group_by` 必须等于 anchor `group_by`。
- 前端预览、payload 构建、展示均以第一行指标作为 anchor。
- 表达式 `a / b`、`b / a`、`(b / a) * 100` 不改变最终告警身份/维度，最终维度始终来自第一行指标。

该规则与 UI 模型一致：第一行指标是公式结果维度的来源。

## 预览资产过滤

公式预览的实例过滤必须作为公共过滤条件作用于每个 OR 分支。

推荐实现：

- 后端公式编译支持按 ref 传入 `base_filters_by_ref`。
- `FormulaCompiler._compile_variable` 调用 `compile_filter_to_query(metric.query, filter, base_filters)`。
- `PolicyPreviewService` 在公式预览时，根据每个查询指标的 `instance_id_keys` 和 `preview.instance_id_values` 构造 `base_filters_by_ref`。
- 前端不再把预览实例过滤直接 append 到 `query_condition.queries[].filter` 尾部。

示例：

用户条件为 `service="checkout" OR status="500"`，预览资产为 `instance_id="host-1"`。

编译结果应等价于：

- `(metric{instance_id=~"host-1", service="checkout"})`
- `or`
- `(metric{instance_id=~"host-1", status="500"})`

不得生成：

- `(metric{service="checkout"}) or (metric{status="500", instance_id=~"host-1"})`

## 单指标兼容

单指标策略继续使用旧结构：

```json
{
  "type": "metric",
  "metric_id": 1,
  "filter": []
}
```

单指标预览继续使用现有 `base_filters` 路径，不改变现有 AND/OR 编译语义。

## 错误处理

- anchor 校验失败、表达式非法、指标缺失继续返回受控 `BaseAppException` / serializer validation error，避免 500。
- 公式预览缺少指标、缺少实例、缺少算法时保持现有前端校验提示。
- UI 文案未命中 i18n key 时不得展示原始 key；需回退为明确中文文案。

## 测试设计

后端 focused 测试：

- `test_formula_validator.py`：新增表达式顺序不影响 anchor 的用例，`queries[0]=a` 且表达式 `b / a` 时 anchor 仍为 `a`。
- `test_formula_compiler.py`：新增 `b / a` 场景，最终 group_by 等于第一行指标 group_by，MetricsQL modifier 方向正确。
- `test_formula_policy_preview.py`：新增 OR 条件 + 资产过滤用例，断言每个 OR selector 都带实例过滤。
- `test_formula_policy_scan.py`：保留最终公式结果 group_by、无数据基准、无数据告警测试。

前端 focused 测试：

- `web/scripts/monitor-policy-formula-payload-test.ts`：覆盖新增指标、删除变量后的校验、`b / a` payload、公式预览不直接 append 实例过滤。
- focused eslint 覆盖 `formulaExpressionUtils.ts`、`metricExpressionEditor.tsx`、`metricDefinitionForm.tsx`、`metricPreview.tsx`、`page.tsx`。

手工验收：

- 新建策略默认单指标空态不挤压。
- 点击“添加指标”后进入公式模式，两个指标行与 fx 行布局稳定。
- 删除第二个指标后校验提示清晰，不出现控件错位。
- 带 OR 条件的公式预览只展示所选资产数据。

## 验收标准

- 指标编辑器视觉接近参考图，控件无遮挡、无横向溢出、按钮文案正确。
- 表达式变量顺序不影响最终告警身份/维度。
- 公式预览与单指标预览的 AND/OR + 资产过滤语义一致。
- 单指标旧 payload、扫描、预览行为不变。
- focused 后端测试、前端脚本测试、focused eslint 通过。

## 风险与回滚

- UI 重排风险：Ant Design Select 宽度与响应式行为可能在不同容器下表现不同。通过固定 grid 轨道和手工截图验收降低风险。
- Anchor 规则变更风险：已有公式策略如果依赖“表达式首变量”为 anchor，行为会变化。由于 UI 一直以第一行作为主指标，此变更是纠偏；需要在测试中覆盖历史策略编辑回填。
- 预览编译参数风险：公式编译器新增可选 base filters 时必须保持默认值为空，避免影响扫描路径。

回滚方式：

- UI 可单独回滚 `MetricExpressionEditor` 布局变更。
- Anchor 与预览过滤变更需连同对应测试一起回滚，避免前后端规则再次不一致。
