# Historical Superpowers change: 2026-06-15-ops-analysis-governance-health

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-15-ops-analysis-governance-health.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add commercial-only CMDB governance health data sources and query APIs for operation analysis dashboards.

**Architecture:** Implement the health query contract inside `apps.cmdb_enterprise.governance`, expose it as NATS `rest_api` functions only when the enterprise app is loaded, and register operation-analysis data sources via an enterprise management command. Operation analysis remains a read-only consumer through its existing data source proxy.

**Tech Stack:** Django 4.2, pytest, NATS function registration, operation_analysis `DataSourceAPIModel`.

---

### Task 1: Governance Health Query Service

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/health_query.py`

- [ ] **Step 1: Write failing tests**

Create tests covering admin/global overview, normal user model-in-current-organization overview, forbidden organization access, trend date range, ranking by model/organization, and problem ranking.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py -q`

Expected: FAIL because `apps.cmdb_enterprise.governance.health_query` does not exist.

- [ ] **Step 3: Implement minimal query service**

Implement:
- `get_governance_health_overview`
- `get_governance_health_trend`
- `get_governance_health_rank`
- `get_governance_health_problem_top`

The service must infer snapshot dimension from `user_info`, `model_id`, and `organization_id`, deny normal-user global/model queries, and return only fields defined in the design doc.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py -q`

Expected: PASS.

### Task 2: Enterprise NATS Registration

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/nats.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/registry_hooks.py`

- [ ] **Step 1: Write failing tests**

Create tests asserting NATS wrapper functions return `{result: True, data: ...}` for valid queries and `{result: False, code: 403, message: ...}` for permission failures.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: FAIL because the NATS module does not exist.

- [ ] **Step 3: Implement minimal NATS wrappers**

Create `governance/nats.py` with four `@nats_client.register` functions matching the registered `rest_api` paths. Import the module from `registry_hooks.py` so the handlers are registered only in enterprise edition.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: PASS.

### Task 3: REST API Usage Documentation

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/governance/docs/ops_analysis_rest_api.md`

- [ ] **Step 1: Write usage documentation**

Document the four `cmdb_enterprise/*` `rest_api` endpoints, supported params, returned fields, and permission behavior for manual configuration in the operation-analysis data source page.

- [ ] **Step 2: Verify no built-in data source registration remains**

Run: `rg -n "init_cmdb_governance_operation_analysis_sources|GOVERNANCE_OPERATION_ANALYSIS_SOURCES|GOVERNANCE_HEALTH_FIELD_SCHEMA" enterprise/server/apps/cmdb_enterprise server/apps`

Expected: no matches.

### Task 4: Final Verification

**Files:**
- All files changed by Tasks 1-3.

- [ ] **Step 1: Run targeted enterprise tests**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: PASS.

- [ ] **Step 2: Check worktree**

Run: `git status --short`

Expected: Only intended files are changed, plus any pre-existing user changes.

## specs: 2026-06-15-ops-analysis-governance-health-design.md

日期：2026-06-15

## 背景

CMDB 商业版已产出数据治理健康度快照，包含全局、模型、组织、模型与组织交叉四类聚合维度。运营分析需要把治理健康度作为看板展示内容接入，让用户在运营分析中看到整体健康度、趋势、排行和问题对象，并可以跳转到 CMDB 数据治理页继续处理。

本设计只定义运营分析侧如何消费商业版 CMDB 暴露的治理健康度 `rest_api` 数据源，以及商业版查询接口的最小契约。健康度口径、快照生成、快照读取和权限过滤均属于商业版 CMDB 职责，不在运营分析侧实现。

## 目标

- 在运营分析中展示数据治理健康度。
- 复用运营分析现有数据源、组件、看板配置、筛选、导入导出能力。
- 商业版 CMDB 提供治理健康度相关 `rest_api` 查询能力，运营分析数据源实例由页面配置。
- 社区版不注册这些数据源，也没有对应商业版查询接口。
- 普通用户只能查看组织维度和模型组织维度数据。
- 超管账号可以查看全局维度和模型维度数据。
- 接口参数和返回字段保持最小化，不设计万能查询接口。

## 非目标

- 不在运营分析侧计算健康度。
- 不在运营分析侧定义治理口径。
- 不在运营分析侧直接读取 `CmdbGovernanceHealthSnapshot`。
- 不在运营分析侧提供治理口径配置。
- 不在运营分析侧执行数据修复。
- 不为社区版暴露商业版治理健康度数据源或接口。

## 职责边界

| 模块 | 职责 |
|---|---|
| 商业版 CMDB | 定义治理口径、生成健康度快照、提供 `cmdb_enterprise/*` 查询接口、执行组织权限过滤 |
| 运营分析 | 在页面配置并调用商业版 `rest_api` 数据源，负责看板展示、组件配置、筛选联动和跳转配置 |
| 社区版 | 不注册治理健康度数据源，不提供 `cmdb_enterprise/*` 查询能力 |

数据流如下：

```text
运营分析 Widget
  -> operation_analysis 数据源代理
  -> 已注册 rest_api: cmdb_enterprise/*
  -> 商业版 CMDB governance 查询接口
  -> CMDB 治理健康度快照与权限过滤
```

## 健康度快照维度

| 快照维度 | 统计对象 | 分组口径 | 使用账号 |
|---|---|---|---|
| `global` | 所有纳入治理的资产 | 不区分模型、不区分组织，整体汇总 | 仅超管 |
| `model` | 某个模型下的资产 | 按 `model_id` 分组 | 仅超管 |
| `organization` | 某个组织下的资产 | 按 `organization_id` 分组，跨模型汇总 | 普通用户、超管 |
| `model_organization` | 某组织下某模型的资产 | 按 `model_id + organization_id` 组合分组 | 普通用户、超管 |

普通用户不直接查询 `global` 和 `model` 维度。超管账号可以查询全部四类维度。

## 健康度指标口径

| 指标 | 含义 | 计算公式 |
|---|---|---|
| `total_count` | 纳入治理资产数 | 配置了治理标记并参与统计的资产总数 |
| `fully_healthy_count` | 完全健康资产数 | 同时满足完整性健康和新鲜度健康的资产数 |
| `total_health_score` | 整体健康度 / 完全健康资产占比 | `fully_healthy_count / total_count * 100%` |
| `completeness_score` | 完整性健康度 | 完整性健康资产数 / `total_count * 100%` |
| `freshness_score` | 新鲜度健康度 | 新鲜度健康资产数 / `total_count * 100%` |

补充规则：

| 规则 | 说明 |
|---|---|
| 关键属性 | 被标记为关键属性的字段，必须有值才算完整性健康 |
| 时效性字段 | 被标记为需要时效校验的字段，用于计算新鲜度健康 |
| 及时更新 | 7 天内更新算新鲜 |
| 不频繁更新 | 90 天内更新算新鲜 |
| 基本不变 | 不参与新鲜度判定 |
| 多组织资产 | 如果资产属于多个组织，会分别计入对应组织维度，因此组织维度不能简单相加等同于全局 |

## 数据源清单

商业版 CMDB 提供 4 个可供运营分析数据源页面配置的 `rest_api`。后端不内置创建 `DataSourceAPIModel`，数据源名称、图表类型、字段 schema 和组件展示字段由运营分析页面配置。

| 数据源名称 | `rest_api` | 支持图表类型 | 说明 |
|---|---|---|---|
| 数据治理健康度概览 | `cmdb/get_governance_health_overview` | `single`, `gauge` | 展示当前口径下整体、完整性、新鲜度健康度 |
| 数据治理健康度趋势 | `cmdb/get_governance_health_trend` | `line` | 展示时间范围内健康度变化 |
| 数据治理健康度排行 | `cmdb/get_governance_health_rank` | `topN`, `table` | 按模型或组织对比健康度 |
| 数据治理问题对象排行 | `cmdb/get_governance_health_problem_top` | `table`, `topN` | 展示健康度最低或问题最多的对象 |

这些 `rest_api` 只在商业版 `cmdb_enterprise` 中可用，不写入社区版 `server/apps/operation_analysis/support-files/source_api.json`，也不通过后端初始化命令自动创建数据源。

## 入参设计

### 通用筛选参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `model_id` | string | 否 | 模型 ID，用于收窄到某模型 |
| `organization_id` | string | 否 | 组织 ID，用于收窄到某组织 |

`model_id` 和 `organization_id` 只表示筛选条件，不表示权限范围。最终查询维度由后端根据当前用户身份和参数组合推导。

### 各数据源入参

| 数据源 | 入参 |
|---|---|
| 数据治理健康度概览 | `model_id?`, `organization_id?` |
| 数据治理健康度趋势 | `time`, `model_id?`, `organization_id?` |
| 数据治理健康度排行 | `dimension`, `limit?` |
| 数据治理问题对象排行 | `dimension`, `limit?` |

### 参数说明

| 参数 | 类型 | 适用数据源 | 说明 |
|---|---|---|---|
| `time` | `timeRange` | 数据治理健康度趋势 | 快照日期范围，复用运营分析现有 `timeRange` 参数类型 |
| `dimension` | `model` / `organization` | 数据治理健康度排行、数据治理问题对象排行 | 决定排行对象是模型还是组织 |
| `limit` | number | 数据治理健康度排行、数据治理问题对象排行 | 返回条数，默认 10 |
`dimension` 不是快照表里的四个维度名，只允许传 `model` 或 `organization`。真实快照维度由后端结合用户身份和筛选条件推导。

## 查询维度推导

| 入参情况 | 普通用户查询维度 | 超管查询维度 |
|---|---|---|
| 无 `model_id`，无 `organization_id` | 当前组织 `organization` | 全局 `global` |
| 只有 `model_id` | 当前组织下该模型 `model_organization` | 全局模型 `model` |
| 只有 `organization_id` | 指定组织 `organization`，需有权限 | 指定组织 `organization` |
| 同时有 `model_id + organization_id` | 指定组织下该模型 `model_organization`，需有权限 | 指定组织下该模型 `model_organization` |

权限规则：

- 普通用户不能直接查询 `global` 和 `model` 快照。
- 普通用户查询组织相关数据时，`organization_id` 必须在当前用户可访问组织范围内。
- 普通用户未传 `organization_id` 时，默认使用当前组织 `current_team`。
- 普通用户传入无权限组织时返回 `403`。
- 超管无筛选时查询全局，只有传入组织筛选时才查询组织维度。

## 返回字段设计

### 数据治理健康度概览

返回对象：

```json
{
  "snapshot_date": "2026-06-07",
  "total_count": 120,
  "fully_healthy_count": 94,
  "total_health_score": 78.33,
  "completeness_score": 84.12,
  "freshness_score": 72.45
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `snapshot_date` | string | 使用的最新快照日期 |
| `total_count` | number | 纳入治理资产数 |
| `fully_healthy_count` | number | 完全健康资产数 |
| `total_health_score` | number | 整体健康度 |
| `completeness_score` | number | 完整性健康度 |
| `freshness_score` | number | 新鲜度健康度 |

### 数据治理健康度趋势

返回折线图多序列对象：

```json
{
  "整体健康度": [["2026-05-09", 75.2]],
  "完整性健康度": [["2026-05-09", 82.1]],
  "新鲜度健康度": [["2026-05-09", 70.4]]
}
```

字段说明：

| 序列名 | 数据格式 | 说明 |
|---|---|---|
| `整体健康度` | `[日期, 分值][]` | 完全健康资产占比趋势 |
| `完整性健康度` | `[日期, 分值][]` | 完整性达标趋势 |
| `新鲜度健康度` | `[日期, 分值][]` | 新鲜度达标趋势 |

### 数据治理健康度排行

返回数组：

```json
[
  {
    "id": "host",
    "name": "服务器",
    "total_health_score": 82.3
  }
]
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 模型 ID 或组织 ID |
| `name` | string | 模型名称或组织名称 |
| `total_health_score` | number | 整体健康度 |

### 数据治理问题对象排行

返回数组：

```json
[
  {
    "id": "network_device",
    "name": "网络设备",
    "total_health_score": 67.2,
    "problem_count": 18,
    "main_problem": "缺少：厂商、型号、序列号"
  }
]
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 模型 ID 或组织 ID |
| `name` | string | 模型名称或组织名称 |
| `total_health_score` | number | 整体健康度 |
| `problem_count` | number | 问题数量 |
| `main_problem` | string | 主要问题摘要 |

接口不返回跳转 URL。跳转由运营分析表格操作列或组件配置完成，避免接口字段承载前端路由语义。

## 字段 Schema 建议

数据源注册时通过 `field_schema` 声明可配置字段，便于 TopN、表格和单值组件选择展示字段。

### 概览字段

| key | title | value_type |
|---|---|---|
| `snapshot_date` | 快照日期 | string |
| `total_count` | 纳入治理资产数 | number |
| `fully_healthy_count` | 完全健康资产数 | number |
| `total_health_score` | 整体健康度 | number |
| `completeness_score` | 完整性健康度 | number |
| `freshness_score` | 新鲜度健康度 | number |

### 趋势字段

| key | title | value_type |
|---|---|---|
| `整体健康度` | 整体健康度 | number |
| `完整性健康度` | 完整性健康度 | number |
| `新鲜度健康度` | 新鲜度健康度 | number |

### 排行字段

| key | title | value_type |
|---|---|---|
| `id` | 对象 ID | string |
| `name` | 对象名称 | string |
| `total_health_score` | 整体健康度 | number |

### 问题对象排行字段

| key | title | value_type |
|---|---|---|
| `id` | 对象 ID | string |
| `name` | 对象名称 | string |
| `total_health_score` | 整体健康度 | number |
| `problem_count` | 问题数量 | number |
| `main_problem` | 主要问题 | string |

## 看板展示建议

| 展示内容 | 数据源 | 组件类型 | 展示字段 |
|---|---|---|---|
| 整体健康度 | 数据治理健康度概览 | `single` 或 `gauge` | `total_health_score` |
| 完整性健康度 | 数据治理健康度概览 | `single` 或 `gauge` | `completeness_score` |
| 新鲜度健康度 | 数据治理健康度概览 | `single` 或 `gauge` | `freshness_score` |
| 健康度趋势 | 数据治理健康度趋势 | `line` | `total_health_score`, `completeness_score`, `freshness_score` |
| 健康度排行 | 数据治理健康度排行 | `topN` | `name`, `total_health_score` |
| 问题对象排行 | 数据治理问题对象排行 | `table` | `name`, `total_health_score`, `problem_count`, `main_problem` |

运营分析可以通过现有组件参数配置模型和组织筛选。商业版专用展示文案需要补充运营分析 i18n key，不在商业版前端代码中裸写中文业务文案。

## 跳转设计

问题对象排行支持通过表格操作列跳转到 CMDB 数据治理页对应筛选视图。

跳转参数建议由看板配置映射，不由接口返回 URL。

| 排行维度 | 跳转参数 |
|---|---|
| `dimension = model` | `model_id = id` |
| `dimension = organization` | `organization_id = id` |

如果组件配置中已有 `model_id` 或 `organization_id`，跳转时可以同时带上现有筛选条件，形成“看 -> 修”的闭环。

## 商业版隔离

### 后端隔离

- 查询 handler 放在 `enterprise/server/apps/cmdb_enterprise`。
- NATS 注册只在商业版 app 加载时生效。
- 社区版没有 `cmdb_enterprise/*` handler。
- 健康度数据源注册放商业版初始化逻辑。
- 社区版 `source_api.json` 不出现商业版治理健康度数据源。

### 前端隔离

- 尽量复用社区版运营分析看板和通用组件。
- 如果新增商业版专属看板模板或静态版本信息，放在 `enterprise/web/src/app/ops-analysis`。
- 社区版不直接 import `enterprise/web` 路径。
- 商业版专用文案需补充 `web/src/app/ops-analysis/locales/zh.json` 和 `web/src/app/ops-analysis/locales/en.json`。

## 错误处理

| 场景 | 处理 |
|---|---|
| 普通用户请求无权限组织 | 返回 `403` |
| 普通用户试图查询超出权限的数据 | 返回 `403` |
| 查询不到快照 | 返回空对象或空数组，由组件显示空态 |
| `dimension` 非 `model` / `organization` | 返回参数错误 |
| `time` 格式非法 | 返回参数错误 |
| `limit` 非正整数 | 返回参数错误 |

## 测试建议

### 后端

- 普通用户无筛选时查询当前组织 `organization`。
- 普通用户只传 `model_id` 时查询当前组织下该模型 `model_organization`。
- 普通用户只传有权限 `organization_id` 时查询指定组织 `organization`。
- 普通用户传无权限 `organization_id` 时返回 `403`。
- 超管无筛选时查询 `global`。
- 超管只传 `model_id` 时查询 `model`。
- 超管传 `model_id + organization_id` 时查询 `model_organization`。
- 趋势接口按 `time` 过滤快照日期。
- 排行接口只接受 `dimension = model / organization`。

### 前端与数据源

- 商业版数据源可以在运营分析中选择。
- 社区版不出现治理健康度数据源。
- 单值、折线、TopN、表格均能使用对应字段展示。
- 问题对象排行可以通过表格操作列跳转 CMDB 数据治理页。
- 中英文 locale key 覆盖商业版新增展示文案。

## 验收标准

- 运营分析可展示来自商业版 CMDB `rest_api` 的治理健康度数据。
- 普通用户只能查看组织维度和模型组织维度数据。
- 超管可以查看全局维度和模型维度数据。
- 可展示整体健康度、完整性健康度、新鲜度健康度、健康度趋势、健康度排行和问题对象排行。
- 问题对象排行可跳转到 CMDB 数据治理页对应筛选视图。
- 运营分析侧不计算健康度、不定义治理口径、不直接读取治理快照表。
- 社区版无法访问商业版治理健康度接口和数据源。
