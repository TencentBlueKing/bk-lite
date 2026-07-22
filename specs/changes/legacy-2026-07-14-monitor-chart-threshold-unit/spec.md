# Historical Superpowers change: 2026-07-14-monitor-chart-threshold-unit

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-14-monitor-chart-threshold-unit.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让监控策略预览图和告警详情图的曲线、Y 轴与阈值线统一使用 `threshold_unit` 展示，同时保持告警扫描、比较和持久化继续使用 `calculation_unit`。

**Architecture:** 在后端新增共享的图表单位转换模块，统一负责有效图表单位解析和响应副本换算。策略预览直接把查询结果转换到阈值单位；告警快照接口把已按计算单位存储的历史快照副本转换到阈值单位。前端只消费后端返回的 `chart_unit`，不复制单位倍率规则，也不改写指标元数据单位。

**Tech Stack:** Python 3.12、Django 4.2、DRF、Next.js 16、React 19、TypeScript、Ant Design、项目 `UnitConverter`。

## Global Constraints

- `metric_unit` 表示原始采集单位，`calculation_unit` 表示内部计算单位，`threshold_unit` 表示阈值输入和阈值型图表展示单位。
- 只转换响应副本，不修改策略阈值、告警事件或 S3 快照。
- 历史空 `threshold_unit` 依次回退 `calculation_unit`、`metric_unit`。
- 跨体系单位返回受控业务错误，不允许标签单位与数值口径不一致。
- 枚举指标、无单位策略和无数据告警保持现有行为。
- 新行为严格执行 TDD；只改本需求相关文件。

---

### Task 1: 提取共享图表单位转换服务

**Files:**
- Create: `server/apps/monitor/services/chart_unit.py`
- Create: `server/apps/monitor/tests/test_chart_unit_service.py`

**Interfaces:**
- Produces: `resolve_chart_unit(metric_unit: str, calculation_unit: str, threshold_unit: str) -> str`
- Produces: `convert_vm_result_copy(data: dict, source_unit: str, target_unit: str) -> dict`
- Produces: `convert_snapshots_copy(snapshots: list[dict], source_unit: str, target_unit: str) -> list[dict]`
- Depends on: `apps.monitor.utils.unit_converter.UnitConverter`

- [ ] **Step 1: 写有效图表单位解析失败测试**

```python
def test_resolve_chart_unit_prefers_threshold_and_supports_legacy_fallback():
    assert resolve_chart_unit("bytes", "bytes", "kibibytes") == "kibibytes"
    assert resolve_chart_unit("bytes", "kibibytes", "") == "kibibytes"
    assert resolve_chart_unit("bytes", "", "") == "bytes"
```

- [ ] **Step 2: 写 VM 数据和快照副本换算失败测试**

```python
def test_converts_vm_result_and_snapshot_copies_without_mutating_inputs():
    vm_data = {"data": {"result": [{"values": [[1, "2048"]]}]}}
    snapshots = [{"raw_data": {"values": [[1, "2048"]]}}]

    converted_vm = convert_vm_result_copy(vm_data, "bytes", "kibibytes")
    converted_snapshots = convert_snapshots_copy(snapshots, "bytes", "kibibytes")

    assert converted_vm["data"]["result"][0]["values"][0][1] == "2.0"
    assert converted_snapshots[0]["raw_data"]["values"][0][1] == "2.0"
    assert vm_data["data"]["result"][0]["values"][0][1] == "2048"
    assert snapshots[0]["raw_data"]["values"][0][1] == "2048"
```

同时覆盖空数据、`None` 值和跨体系抛出 `BaseAppException`。

- [ ] **Step 3: 运行测试确认 RED**

Run: `cd server && .venv/bin/pytest apps/monitor/tests/test_chart_unit_service.py -q --no-cov`

Expected: FAIL，提示 `apps.monitor.services.chart_unit` 或目标函数不存在。

- [ ] **Step 4: 实现最小共享服务**

```python
from copy import deepcopy

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.unit_converter import UnitConverter


def resolve_chart_unit(metric_unit="", calculation_unit="", threshold_unit=""):
    return threshold_unit or calculation_unit or metric_unit or ""


def _convert_values(values, source_unit, target_unit):
    if not source_unit or not target_unit or source_unit == target_unit:
        return values
    if not UnitConverter.is_convertible(source_unit, target_unit):
        raise BaseAppException(
            f"chart unit is not convertible: {source_unit} -> {target_unit}"
        )
    return UnitConverter.convert_values(values, source_unit, target_unit)
```

`convert_vm_result_copy` 和 `convert_snapshots_copy` 必须先 `deepcopy`，只替换数值位并保留时间戳、维度和其他快照字段。

- [ ] **Step 5: 运行测试确认 GREEN**

Run: `cd server && .venv/bin/pytest apps/monitor/tests/test_chart_unit_service.py -q --no-cov`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add server/apps/monitor/services/chart_unit.py server/apps/monitor/tests/test_chart_unit_service.py
git commit -m "新增监控图表单位转换服务"
```

### Task 2: 策略预览以阈值单位返回曲线和阈值

**Files:**
- Modify: `server/apps/monitor/services/policy_preview.py`
- Modify: `server/apps/monitor/tests/test_policy_preview_service.py`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`

**Interfaces:**
- Consumes: `resolve_chart_unit`、`convert_vm_result_copy`
- Produces API fields: `chart_unit: string`、`threshold: ThresholdField[]`
- Produces frontend helper: `resolvePreviewChartUnit(responseUnit, thresholdUnit, calculationUnit) -> string | null`

- [ ] **Step 1: 写后端预览 RED 测试**

覆盖两条源单位规则：

```python
def test_metric_preview_converts_series_to_threshold_unit():
    # metric_unit=bytes, calculation_unit=bytes, threshold_unit=kibibytes
    # VM 返回 2048，响应曲线应为 2，chart_unit=kibibytes，阈值仍为用户输入值 2

def test_formula_preview_converts_calculation_unit_to_threshold_unit():
    # formula 的查询结果按 calculation_unit=bytes 解释，转换到 threshold_unit=kibibytes
```

另断言输入 VM 响应和 `payload["threshold"]` 未被修改。

- [ ] **Step 2: 运行后端测试确认 RED**

Run: `cd server && .venv/bin/pytest apps/monitor/tests/test_policy_preview_service.py -q --no-cov`

Expected: FAIL，现有响应仍以 `calculation_unit` 展示且阈值被转换到计算单位。

- [ ] **Step 3: 调整预览服务**

在 `preview()` 中按查询类型确定图表源单位：

```python
chart_unit = resolve_chart_unit(
    self.payload.get("metric_unit") or getattr(self.metric, "unit", ""),
    self.payload.get("calculation_unit") or "",
    self.payload.get("threshold_unit") or "",
)
source_unit = (
    self.payload.get("calculation_unit")
    if query_condition.get("type") == "formula"
    else self.payload.get("metric_unit") or getattr(self.metric, "unit", "")
)
data = convert_vm_result_copy(data, source_unit or chart_unit, chart_unit)
```

响应返回 `chart_unit`；`threshold` 只深拷贝，不再从阈值单位转换到计算单位；`data.unit` 使用图表单位展示符号。

- [ ] **Step 4: 写前端图表单位 RED 测试**

```typescript
assert.equal(
  resolvePreviewChartUnit('kibibytes', 'kibibytes', 'bytes'),
  'kibibytes'
);
assert.equal(resolvePreviewChartUnit('', null, 'bytes'), 'bytes');
```

- [ ] **Step 5: 运行前端测试确认 RED**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: FAIL，helper 尚不存在。

- [ ] **Step 6: 接入策略预览图**

`MetricPreview` 保存响应的 `chart_unit`，标题和 `LineChart.unit` 都使用：

```typescript
const effectiveChartUnit =
  previewChartUnit || thresholdUnit || calculationUnit || null;
```

阈值线使用服务端返回的原始阈值单位数值；请求失败或条件变化时清理旧的响应图表单位，避免显示上一请求单位。

- [ ] **Step 7: 运行 Task 2 回归并提交**

Run:

```bash
cd server && .venv/bin/pytest apps/monitor/tests/test_policy_preview_service.py apps/monitor/tests/test_chart_unit_service.py -q --no-cov
cd ../web && pnpm test:monitor-strategy-detail-logic
```

Expected: 全部 PASS。

```bash
git add server/apps/monitor/services/policy_preview.py server/apps/monitor/tests/test_policy_preview_service.py web/src/app/monitor/\(pages\)/event/strategy/detail/metricPreview.tsx web/src/app/monitor/\(pages\)/event/strategy/detail/strategyDetailUtils.ts web/scripts/monitor-strategy-detail-logic-test.ts
git commit -m "统一监控策略预览图阈值单位"
```

### Task 3: 告警详情快照图以阈值单位展示

**Files:**
- Modify: `server/apps/monitor/views/monitor_alert.py`
- Modify: `server/apps/monitor/tests/test_monitor_alert_view.py`
- Modify: `web/src/app/monitor/(pages)/event/alert/alertDetail.tsx`
- Modify: `web/src/app/monitor/(pages)/event/alert/information.tsx`
- Modify: `web/src/app/monitor/(pages)/event/alert/alertDetailUtils.ts`
- Modify: `web/scripts/monitor-alert-detail-snapshot-test.ts`

**Interfaces:**
- Consumes: `resolve_chart_unit`、`convert_snapshots_copy`
- Snapshot API adds: `chart_unit: string`
- Produces frontend helper: `resolveAlertDetailChartUnit(alert, responseUnit) -> string`
- `Information` adds prop: `chartUnit: string | null`

- [ ] **Step 1: 写快照接口 RED 测试**

在 `test_monitor_alert_view.py` 创建关联策略：

```python
policy.metric_unit = "bytes"
policy.calculation_unit = "bytes"
policy.threshold_unit = "kibibytes"
```

快照包含 `2048` 时，接口断言：

```python
assert response.data["data"]["chart_unit"] == "kibibytes"
assert response.data["data"]["snapshots"][0]["raw_data"]["values"][0][1] == "2.0"
assert stored_snapshot_value == "2048"
```

同时覆盖空 `threshold_unit` 回退计算单位和空快照。

- [ ] **Step 2: 运行接口测试确认 RED**

Run: `cd server && .venv/bin/pytest apps/monitor/tests/test_monitor_alert_view.py -q --no-cov`

Expected: FAIL，响应没有 `chart_unit` 且快照未转换。

- [ ] **Step 3: 接入快照响应转换**

`get_snapshots` 在权限检查和 S3 读取成功后，从 `alert_obj.policy` 解析：

```python
source_unit = policy.calculation_unit or policy.metric_unit or ""
chart_unit = resolve_chart_unit(
    policy.metric_unit,
    policy.calculation_unit,
    policy.threshold_unit,
)
snapshots_data = convert_snapshots_copy(
    snapshots_data, source_unit or chart_unit, chart_unit
)
```

响应增加 `chart_unit`。S3 异常和无快照路径仍返回空列表，并尽可能返回可解析的图表单位。

- [ ] **Step 4: 写告警详情前端 RED 测试**

```typescript
assert.equal(
  resolveAlertDetailChartUnit(
    { policy: { threshold_unit: 'kibibytes', calculation_unit: 'bytes' } },
    ''
  ),
  'kibibytes'
);
assert.equal(
  resolveAlertDetailChartUnit(
    { policy: { threshold_unit: 'kibibytes', calculation_unit: 'bytes' } },
    'mebibytes'
  ),
  'mebibytes'
);
```

- [ ] **Step 5: 运行前端测试确认 RED**

Run: `cd web && pnpm test:monitor-alert-detail-snapshot`

Expected: FAIL，helper 尚不存在。

- [ ] **Step 6: 告警详情使用独立 chartUnit**

`alertDetail.tsx` 从快照响应保存 `chart_unit`；`Information` 使用 `chartUnit` 渲染指标标题和 `LineChart.unit`。保留 `resolveAlertDetailMetric` 的计算单位逻辑，避免直接改变告警摘要 `alertValue` 的数值单位。

- [ ] **Step 7: 运行 Task 3 回归并提交**

Run:

```bash
cd server && .venv/bin/pytest apps/monitor/tests/test_monitor_alert_view.py apps/monitor/tests/test_chart_unit_service.py -q --no-cov
cd ../web && pnpm test:monitor-alert-detail-snapshot
```

Expected: 全部 PASS。

```bash
git add server/apps/monitor/views/monitor_alert.py server/apps/monitor/tests/test_monitor_alert_view.py web/src/app/monitor/\(pages\)/event/alert/alertDetail.tsx web/src/app/monitor/\(pages\)/event/alert/information.tsx web/src/app/monitor/\(pages\)/event/alert/alertDetailUtils.ts web/scripts/monitor-alert-detail-snapshot-test.ts
git commit -m "统一告警详情图阈值单位"
```

### Task 4: 最终门禁与交付

**Files:**
- Verify only: all files changed in Tasks 1-3

**Interfaces:**
- Verifies: 策略预览和告警详情都返回/消费 `chart_unit`
- Verifies: 阈值、快照与 VM 原始响应不被修改

- [ ] **Step 1: 运行后端聚焦回归**

```bash
cd server
.venv/bin/pytest \
  apps/monitor/tests/test_chart_unit_service.py \
  apps/monitor/tests/test_policy_preview_service.py \
  apps/monitor/tests/test_monitor_alert_view.py \
  apps/monitor/tests/test_formula_policy_preview.py \
  apps/monitor/tests/test_formula_policy_scan.py \
  apps/monitor/tests/test_policy_scan_metric_query_service.py \
  -q --no-cov
.venv/bin/python manage.py makemigrations --check --dry-run monitor
```

Expected: 全部 PASS；迁移检查输出 `No changes detected in app 'monitor'`。

- [ ] **Step 2: 运行前端聚焦回归和静态检查**

```bash
cd web
pnpm test:monitor-strategy-detail-logic
pnpm test:monitor-alert-detail-snapshot
pnpm exec eslint \
  'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' \
  'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' \
  'src/app/monitor/(pages)/event/alert/alertDetail.tsx' \
  'src/app/monitor/(pages)/event/alert/information.tsx' \
  'src/app/monitor/(pages)/event/alert/alertDetailUtils.ts'
NEXTAPI_INSTALL_APP=monitor pnpm type-check
```

Expected: 全部 PASS。

- [ ] **Step 3: 核对工作区和提交历史**

```bash
git diff --check
git status --short
git log --oneline --max-count=5
```

Expected: 仅保留用户原有未提交文件；本功能文件均已提交。

## specs: 2026-07-14-monitor-chart-threshold-unit-design.md

- 日期：2026-07-14
- 范围：监控策略预览图、告警详情图
- 关联决策：`docs/design/product-decisions/monitor-alert-threshold-units.md`

## 1. 问题与目标

监控策略已经将 `calculation_unit`（计算结果单位）与 `threshold_unit`（阈值输入单位）解耦，但策略预览图和告警详情图仍以计算单位展示曲线。用户选择 `KB` 配置阈值时，曲线和 Y 轴却显示 `B`，导致阈值线与数据的阅读口径不一致。

本次目标是让阈值型图表统一使用阈值单位展示：曲线数据、Y 轴、指标标题单位和阈值线处于同一单位体系；后台计算与历史存储语义保持不变。

## 2. 产品规则

1. 告警扫描、表达式计算和阈值比较继续以 `calculation_unit` 为内部计算口径。
2. 策略预览图和告警详情图以 `threshold_unit` 为展示口径。
3. 历史策略的 `threshold_unit` 为空时，展示单位依次回退到 `calculation_unit`、`metric_unit`。
4. 图表转换只处理响应数据副本，不改写策略阈值、告警事件或 S3 历史快照。
5. 单位不可换算时不得展示混合单位图表：服务端返回受控错误；正常新策略已由保存校验阻止此状态。
6. 枚举指标和无单位策略保持现有展示，不进入数值单位换算。

## 3. 推荐架构

采用服务端统一换算、前端只消费图表单位的方案，避免前端复制 `UnitConverter` 规则。

### 3.1 策略预览

`PolicyPreviewService` 计算图表源单位与目标单位：

- 单指标：源单位为 `metric_unit`，目标单位为有效 `threshold_unit`。
- 公式：表达式结果按声明的 `calculation_unit` 解释，目标单位为有效 `threshold_unit`。

服务端把查询结果副本转换到目标单位，阈值保持用户输入数值不变，并返回 `chart_unit`（单位 ID）与展示符号。前端使用 `chart_unit` 渲染标题和 Y 轴，不再用 `calculation_unit` 覆盖图表单位。

### 3.2 告警详情

告警快照保存的是扫描阶段的计算单位数据。快照接口读取 `MonitorAlert` 关联策略后：

1. 解析源单位：`calculation_unit || metric_unit`；
2. 解析目标单位：`threshold_unit || calculation_unit || metric_unit`；
3. 深拷贝快照列表，并仅转换每个 `raw_data.values[*][1]`；
4. 返回转换后的 `snapshots` 和 `chart_unit`。

前端告警详情为图表单独维护 `chartUnit`，不修改指标元数据单位，避免影响告警摘要中既有数值语义。

## 4. 数据示例

策略配置：

- `metric_unit = bytes`
- `calculation_unit = bytes`
- `threshold_unit = kibibytes`
- 严重阈值 `50`

服务端查询值 `51200 B` 在图表响应中转换为 `50 KiB`。前端展示：

- Y 轴单位：`KiB`
- 曲线值：`50`
- 严重阈值线：`50`

## 5. 错误与兼容处理

- 缺少阈值单位：回退计算单位，保持历史行为。
- 空快照、无数据告警：返回空图表数据和有效 `chart_unit`，不报错。
- `None`、NaN、Infinity：沿用现有过滤或跳过规则，不生成无效图点。
- 跨体系单位：返回受控业务错误，不静默保留原值，防止曲线和标签单位不一致。
- API 增加字段，不删除现有字段，现有调用方保持兼容。

## 6. 验收标准

1. 策略预览中 `51200 B` 在阈值单位为 `KiB` 时展示为 `50 KiB`，阈值线仍为 `50`。
2. 公式结果为 `bytes`、阈值单位为 `kibibytes` 时，预览数据按 `bytes → kibibytes` 转换。
3. 告警详情的历史快照数据转换到关联策略的阈值单位，Y 轴与阈值线一致。
4. `threshold_unit` 为空时，两类图表继续按计算单位展示。
5. 策略配置、告警事件和快照持久化内容在展示过程中不被修改。
6. 后端转换、历史回退、空数据和不修改输入均有自动化测试；前端图表单位解析有专项测试。

## 7. 明确不做

- 不改变告警扫描和阈值比较的内部计算口径。
- 不批量改写历史快照。
- 不在前端维护第二套单位倍率表。
- 不扩展到与阈值无关的普通指标视图。
