# CMDB 数据治理健康度快照设计

日期：2026-06-11

## 背景

CMDB 已支持模型字段治理标记，用于声明关键属性与时效性档位。下一阶段运营分析需要展示数据治理健康度，包括整体健康度、完整性健康度、新鲜度健康度、趋势以及按模型/组织下钻。

本阶段先交付商业版后端底座：计算完整性与新鲜度两个维度，并按天保存聚合快照。前端页面、查询接口、数据治理页、问题清单与修复动作不在本期实现。

## 目标

- 基于模型字段治理标记计算完整性健康度。
- 基于实例级操作日志计算新鲜度健康度。
- 计算总健康度，即完整性与新鲜度同时达标的资产占比。
- 每日保存聚合快照，服务后续运营分析展示。
- 支持手动触发生成指定日期快照，便于验收与联调。
- 在社区版采集链路补齐自动采集产生的实例级操作日志，使采集新增、更新、无变化核实均可作为新鲜度事实源。
- 商业版实现治理健康度计算、快照、周期任务与手动命令；社区版仅承载采集实例操作日志这一 CMDB 基础历史能力。

## 非目标

- 不实现 CMDB 数据治理页。
- 不实现前端页面。
- 不实现后端查询接口。
- 不保存实例级问题明细。
- 不实现批量修复、重新采集、人工编辑、确认仍有效。
- 不实现关系完整性、僵尸资产、重复性、一致性等其他治理维度。
- 不处理自定义上报的操作日志补齐；该能力由自定义上报方向独立处理。

## 总体方案

采用商业版聚合快照方案。

后台任务每日扫描纳入治理的模型和实例，计算每个实例的完整性、新鲜度与完全健康状态，然后按以下四类维度聚合并保存快照：

- `global`：系统全局维度，不带用户权限过滤。
- `model`：按模型聚合。
- `organization`：按组织聚合。
- `model_organization`：按模型与组织交叉聚合。

后续运营分析查询接口可根据用户组织权限读取 `organization` 与 `model_organization` 快照并汇总；只有全局权限场景才直接使用 `global`。

## 聚合维度

### global

统计全系统范围内所有纳入治理的 CMDB 资产。该维度不绑定某个用户权限。

### model

按模型统计，例如服务器、K8s 集群、数据库等。一个实例只计入所属模型一次。

### organization

按组织统计。实例归属多个组织时，分别计入每个组织。

### model_organization

按模型与组织组合统计。用于后续页面同时筛选模型和组织时直接读取趋势快照。

## 快照数据模型

商业版新增聚合快照表，建议模型放在 `enterprise/server/apps/cmdb_enterprise/governance/models.py`。

表名建议：

```text
cmdb_governance_health_snapshot
```

核心字段：

```text
snapshot_date          快照日期，按天
dimension              聚合维度: global / model / organization / model_organization
model_id               模型 ID，仅模型相关维度填写
organization_id        组织 ID，仅组织相关维度填写
model_key              模型唯一约束归一化值，无模型时为 ""
organization_key       组织唯一约束归一化值，无组织时为 0

total_count            纳入治理统计的资产数
complete_count         完整性达标资产数
fresh_count            新鲜度达标资产数
healthy_count          完全健康资产数

completeness_score     完整性健康度
freshness_score        新鲜度健康度
overall_score          总健康度

metadata               扩展信息 JSON
created_at / updated_at
```

唯一约束：

```text
(snapshot_date, dimension, model_key, organization_key)
```

使用 `model_key` 与 `organization_key` 是为了避免不同数据库对 `NULL` 唯一约束行为不一致，保证同一天同一维度重复执行时可以稳定 upsert。

分数口径：

```text
completeness_score = complete_count / total_count
freshness_score    = fresh_count / total_count
overall_score      = healthy_count / total_count
```

当 `total_count = 0` 时，三个分数字段保存为 `null`，后续展示为 `--`。

## 模型纳入治理条件

只统计存在治理标记字段的模型。模型满足以下任一条件即纳入治理：

- 存在 `governance.key_attribute = true` 的字段。
- 存在 `governance.freshness = timely` 或 `governance.freshness = occasional` 的字段。

以下字段不使模型纳入治理：

- `governance.freshness = stable`
- `governance.freshness = ""`
- 缺失 `governance`

如果模型完全没有关键属性字段，也没有 `timely/occasional` 时效字段，则不统计该模型下的实例。

## 完整性计算

完整性以关键属性字段为准：

```text
实例所属模型的所有关键属性字段均已填写 => 完整性达标
```

关键属性字段：

```text
governance.key_attribute = true
```

空值口径：

- 未填写：`null`、空字符串、空白字符串、空数组、空对象。
- 已填写：`0`、`false`、非空字符串、非空数组、非空对象。

如果模型纳入治理但没有关键属性字段，则该模型实例的完整性视为达标，不让缺失该维度拖累健康度。

## 新鲜度计算

新鲜度以时效字段为准：

```text
governance.freshness = timely 或 occasional
```

时效窗口沿用字段治理标记的系统预定义口径：

```text
timely      = 7 天
occasional  = 90 天
stable      = 不参与新鲜度计算
```

如果模型纳入治理但没有 `timely/occasional` 时效字段，则该模型实例的新鲜度视为达标。

### 操作日志作为事实源

本期新鲜度完全由实例级 `ChangeRecord` 计算。操作日志分为两类解释。

#### 全字段核实日志

这些日志表示实例被可信来源整体核实过，实例下所有参与新鲜度计算的字段都刷新核实时间。

本期纳入：

```text
scenario = COLLECT_AUTOMATION_CHANGE
type in CREATE_INST / UPDATE_INST
model_object = OPERATOR_INSTANCE
```

包括：

- 自动采集新增实例。
- 自动采集更新实例且字段有变化。
- 自动采集核实实例但字段无变化。

后续自定义上报方向补齐实例级 `CUSTOM_REPORTING_CHANGE` 日志后，可按同一规则纳入：

```text
scenario = CUSTOM_REPORTING_CHANGE
type in CREATE_INST / UPDATE_INST
model_object = OPERATOR_INSTANCE
```

#### 字段变更日志

这些日志只刷新实际变化的字段。

本期纳入：

```text
scenario in ORDINARY_ATTRIBUTE_CHANGE / DEVICE_LIFECYCLE
type in CREATE_INST / UPDATE_INST
model_object = OPERATOR_INSTANCE
```

规则：

- `CREATE_INST`：实例新增，视为 `after_data` 中出现的时效字段已核实。
- `UPDATE_INST`：比较 `before_data` 与 `after_data`，只有值发生变化的时效字段刷新核实时间。
- 普通属性或导入产生的无变化更新不刷新新鲜度。

不纳入新鲜度的日志：

- 关系变更。
- 模型管理变更。
- 采集任务本身的执行日志。
- 删除实例日志。
- 导入无变化日志。
- 自定义上报日志补齐前暂不作为本期验收点。

### 实例新鲜度达标

对每个参与新鲜度计算的字段：

```text
存在核实时间
且 snapshot_time - verified_at <= 字段时效窗口
```

实例所有参与新鲜度计算的字段都达标时，实例新鲜度达标。任一字段无核实记录或超过时窗，实例新鲜度不达标。

## 自动采集实例级操作日志补齐

为了让操作日志成为新鲜度统一事实源，本期需要在社区版采集链路补齐自动采集产生的实例级 `ChangeRecord`。商业版治理健康度只消费这些操作日志，不负责写入采集实例日志。

统一字段：

```text
scenario = COLLECT_AUTOMATION_CHANGE
model_object = OPERATOR_INSTANCE
```

规则：

- 采集新增成功：
  - `type = CREATE_INST`
  - `after_data = 新实例快照`
  - message：`自动采集新增实例`

- 采集更新成功且字段有变化：
  - `type = UPDATE_INST`
  - `before_data = 更新前实例快照`
  - `after_data = 更新后实例快照`
  - message：`自动采集更新实例`

- 采集更新成功但字段无变化：
  - `type = UPDATE_INST`
  - `before_data = 当前实例快照`
  - `after_data = 当前实例快照`
  - message：`自动采集核实实例，字段无变化`

- 采集删除成功：
  - `type = DELETE_INST`
  - `before_data = 删除前实例快照`
  - message：`自动采集删除实例`
  - 删除日志用于审计，不刷新新鲜度。

`PARTIAL_SUCCESS` 时，只对成功的 `add/update/delete` 行写日志，失败行不写。

实现建议：

- 不在循环中逐条创建日志，优先批量构造 `change_records` 并调用 `batch_create_change_record`。
- 更新类日志需要 `before_data`，应在采集写库前或写库阶段保留更新前快照，避免写库后无法准确还原。
- 字段变化判断应忽略系统字段，例如 `_id`、`_labels`、`model_id`、`organization`、`collect_task`、`collect_time`、`auto_collect`、`_display` 等。

## 健康度聚合

对每个纳入治理实例计算：

```text
is_complete = 所有关键属性已填写
is_fresh    = 所有时效字段未过期
is_healthy  = is_complete and is_fresh
```

聚合计数：

```text
total_count += 1
complete_count += is_complete
fresh_count += is_fresh
healthy_count += is_healthy
```

多组织实例计数：

- `global`：只计一次。
- `model`：只计一次。
- `organization`：每个组织各计一次。
- `model_organization`：每个组织 + 模型组合各计一次。

## 后台任务与手动触发

商业版新增每日 Celery 任务，建议任务名：

```text
cmdb-governance-health-snapshot
```

调度建议：

```text
每日 03:30
```

任务行为：

```text
calculate_governance_health_snapshot(snapshot_date=today)
```

手动触发使用 management command，不新增 HTTP 接口：

```bash
cd server
uv run python manage.py calculate_cmdb_governance_health --date 2026-06-11
```

不传 `--date` 时默认生成当天快照。

## 商业版代码拆分

建议目录：

```text
enterprise/server/apps/cmdb_enterprise/governance/
  constants.py
  models.py
  services.py
  tasks.py
```

职责：

- `constants.py`：维度枚举、时效窗口、日志场景、忽略字段。
- `models.py`：健康度聚合快照表。
- `services.py`：治理标记读取、实例扫描、操作日志解释、健康度计算、快照 upsert。
- `tasks.py`：Celery 周期任务入口。

management command 建议放在：

```text
enterprise/server/apps/cmdb_enterprise/management/commands/calculate_cmdb_governance_health.py
```

社区版不包含治理健康度计算、快照、周期任务与手动命令。采集实例级操作日志属于 CMDB 基础历史能力，放在社区版采集链路；商业版健康度计算复用这些日志。

## 测试设计

### 模型纳入治理

- 有关键属性字段的模型纳入统计。
- 有 `timely/occasional` 字段的模型纳入统计。
- 只有 `stable` 或无治理标记的模型不纳入统计。

### 完整性

- 关键属性全部填写时完整性达标。
- `null`、空字符串、空数组、空对象判为未填写。
- `0`、`false` 判为已填写。
- 没有关键属性但有时效字段时，完整性视为达标。

### 新鲜度

- 自动采集实例级 `COLLECT_AUTOMATION_CHANGE` 的 `CREATE_INST/UPDATE_INST` 刷新所有时效字段。
- 普通实例 `UPDATE_INST` 只刷新实际变化字段。
- 无核实记录的时效字段判为不达标。
- 超过 `timely=7天` 或 `occasional=90天` 判为不达标。
- 没有时效字段但有关键属性时，新鲜度视为达标。

### 自动采集操作日志

- 采集新增成功写实例级 `ChangeRecord`。
- 采集更新有变化写实例级 `ChangeRecord`。
- 采集更新无变化也写实例级 `ChangeRecord`，message 明确“字段无变化”。
- `PARTIAL_SUCCESS` 中成功行写日志，失败行不写。

### 聚合快照

- 生成 `global/model/organization/model_organization` 四类快照。
- 多组织实例在组织维度分别计数，在全局/模型维度只计一次。
- `total_count = 0` 时 score 为 `null`。
- 重复执行同一天任务会 upsert，不产生重复快照。

### 手动触发

- management command 可按指定日期生成快照。
- 不传日期时默认生成当天快照。

## 验证命令

最终验证：

```bash
cd server && make test
```

实现过程中可先跑聚焦测试：

```bash
cd server && uv run pytest enterprise/server/apps/cmdb_enterprise/tests -q
cd server && uv run pytest server/apps/cmdb/tests -q
```

## 后续扩展

- 自定义上报方向补齐实例级 `CUSTOM_REPORTING_CHANGE` 日志后，新鲜度计算可将其纳入全字段核实日志。
- 数据治理页上线后，“确认仍有效”应落实例级操作日志，再纳入同一套新鲜度计算。
- 若后续需要问题清单与修复闭环，可新增实例级治理明细或按需实时计算问题字段。
