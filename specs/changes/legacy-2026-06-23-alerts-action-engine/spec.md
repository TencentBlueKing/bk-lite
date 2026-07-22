# Historical Superpowers change: 2026-06-23-alerts-action-engine

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-23-alerts-action-engine-design.md

日期：2026-06-23
状态：已与需求方确认（待最终评审）
范围：本期实现 L1（动作引擎 + 规则配置 + 作业动作 + 执行记录/回写 + 自动/手动触发）+ L1.5 全部前端界面（前后端双端一次性交付）。

## 1. 背景与目标

告警经丰富/收敛后，目前下游只有"通知人"一条路。本期补上"动作"维度：让告警在通知之外能**触发动作**。第一类动作落地"触发 job_mgmt 中已存在的作业/脚本"，并建成**通用可插拔引擎**——后续接 ITSM / Webhook 只是"加一类动作"，不重写。

核心约束：
- 声明式规则驱动，可启停、按团队隔离。
- 自动触发（告警创建 + 状态流转，触发事件在规则上**显式声明**）+ 手动触发（详情页对单条告警执行/重跑）。
- **幂等防风暴**：自动下 `(规则,告警,触发事件)` 只一次；手动不限。
- **不阻塞告警主流程**：动作异步执行，任何失败/超时/外部不可用绝不阻塞或失败告警本身。
- 执行可观测：每次触发落一条执行记录，结果回写到告警时间线。

## 2. 关键决策（已澄清）

| # | 决策 | 选择 |
|---|---|---|
| Q1 | "选择作业" 如何喂给 `job_script_execute` | **引用 + 运行时读取**：规则只存 `script_id`，触发时经 NATS 读取实时 Script 的 `content/script_type/params/timeout`，内联调用 `job_script_execute`。已存在的作业是唯一事实源。 |
| Q2 | 触发事件粒度 | **语义事件**：`created` + 具名状态事件（`assigned/acknowledged/reassigned/resolved/closed`）。规则声明监听哪些；幂等键含具名事件。UI 以友好勾选呈现，底层映射具名事件。 |
| Q3 | 结果回写机制 | **仅回调（L1）**：传 `callback_url` 给 job_mgmt，作业完成后它 HMAC-SHA256 签名 POST 回来；不做轮询/对账（L1 限制：回调彻底失败则记录停留 running，靠手动重跑兜底）。 |
| Q4 | 目标/参数解析 | **node_mgmt 运行时匹配**：目标主机从告警字段取（如 `labels.ip`），经 NATS `node_list` 匹配**节点管理**中已纳管的主机（用户须先把 agent 装到该主机），以 `target_source="node_mgmt"` 执行。**告警无主机信息 / 未纳管 / 不唯一 → 记 `config_error`，不调用 NATS**。参数绑定 = 字段路径 \| 常量，缺失回退脚本 `default`。前置约束：自愈只能触达已纳管到节点管理的主机（无需 SSH 凭据，agent 执行）。 |
| Q5 | 本期交付范围 | **A**：前后端设计 + 同时实现后端 L1 + 前端三个界面（规则列表/编辑抽屉、执行记录列表、详情页处理动作时间线+手动触发）。 |
| Q6 | 手动触发语义 | **A**：运行某条已配置规则的动作（同团队、action_type=job），**跳过匹配评估 + 跳过幂等**；重跑 = 对同一规则+告警再建一条执行。 |
| 架构 | 引擎接入方式 | **方法1**：与丰富引擎同构的 `action/` 包；生命周期 5 个 hook 点显式调用 `dispatch_async`（`on_commit`+Celery）；幂等用 DB 唯一约束。 |

本期不做（YAGNI）：ITSM/Webhook 具体实现（仅预留）、incident 级触发、多动作编排、失败自动重试/冷却、在告警中心内新建/编辑作业脚本、回调对账轮询。

## 3. 后端数据模型

新包 `server/apps/alerts/action/`（与 `enrichment/` 同构）；模型置于 `apps/alerts/models/action.py`。

### 3.1 `ActionRule`（声明式规则）
| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | CharField(100) | 规则名 |
| `is_active` | Bool | 启停 |
| `team` | JSONField(list) | 团队隔离，同 `EnrichmentRule.team` |
| `match_rules` | JSONField(list) | **复用丰富引擎 OR-of-AND** 结构与 matcher |
| `trigger_events` | JSONField(list) | 语义事件，如 `["created","resolved"]` |
| `scope` | CharField(16) | `"alert"`（本期）；`"incident"` 预留 |
| `action_type` | CharField(32) | `"job"`（本期）；`itsm/webhook` 后续——驱动 handler 注册表 |
| `action_config` | JSONField(dict) | 类型相关配置（见下） |
| `created_by/at`,`updated_by/at` | — | `MaintainerInfo`+`TimeInfo` mixins |

`action_config`（job handler）：
```jsonc
{
  "script_id": 42,
  "target_binding": { "source": "node_mgmt", "match_by": "ip", "host_field": "labels.ip" },
  "param_bindings": [
    { "name": "service", "from": "field", "value": "labels.service" },
    { "name": "timeout", "from": "const", "value": "600" }
  ]
}
```
`target_binding.source="node_mgmt"`：从告警 `host_field` 取主机标识（默认按 `ip` 匹配，可选 `name`），经 NATS `node_list` 解析到节点管理中的 node。handler 可插拔，未来 SSH/manual 模式只是新增一个 `source`。

### 3.2 `ActionExecution`（每次触发一条记录）
| 字段 | 类型 | 说明 |
|---|---|---|
| `rule` | FK→ActionRule, null | 可空，规则删除后历史记录存活 |
| `alert` | FK→Alert | 目标告警 |
| `trigger_event` | CharField(32) | 具名事件，或 `"manual"` |
| `trigger_type` | CharField(16) | `"auto"` / `"manual"` |
| `idempotency_key` | CharField, **unique, null** | 自动：`f"{rule_id}:{alert_id}:{event}"`；手动：**NULL**（多 NULL 不冲突） |
| `status` | CharField(16) | `pending→running→success/failed`，外加 `skipped`(幂等重复) / `config_error`(缺失关键信息) |
| `action_type` | CharField(32) | 规则类型快照 |
| `job_task_id` | Int, null | `JobExecution.id` |
| `job_detail_url` | CharField, null | 跳转作业执行详情链接 |
| `result` | JSONField | 回调汇总 `{total,success,failed,finished_at}` 或错误信息 |
| `operator` | CharField, null | 手动触发人 |
| `created_at/updated_at` | — | 时间线排序 |

**幂等是结构性的**：`idempotency_key` 上的 DB `unique` 约束使重复自动触发的插入失败 → 捕获 → 记为 `skipped`，绝不二次执行。手动行 `idempotency_key=NULL` → 永远允许。

**时间线数据源**：详情页"处理动作"tab 读 `ActionExecution.objects.filter(alert=...)` 按 `created_at` 排序。每条执行额外写一条 `OperatorLog` 用于全局审计，与本 app 其余逻辑一致。

## 4. 后端引擎、生命周期 hook 与执行流

### 4.1 包结构（与 `enrichment/` 同构）
```
apps/alerts/action/
  engine.py            # ActionEngine —— 编排
  matcher.py           # 复用 enrichment.matcher (event_matches)
  resolver.py          # 字段路径解析：alert + binding → target_list & params
  handlers/
    base.py            # ActionHandler ABC: execute(rule, alert, execution) -> task_id
    registry.py        # get_handler(action_type)，可插拔（job 现有；itsm/webhook 后续）
    job.py             # JobActionHandler：读 Script(NATS) → 内联 → job_script_execute
```

### 4.2 自动触发流（不阻塞）
1. **生命周期 hook**——在每个站点状态提交后：
   - `AlertBuilder.create_alert()` → 事件 `created`
   - 每个 `AlertOperator._*` 状态流转 → 其具名事件（`assigned/acknowledged/reassigned/resolved/closed`）
   - hook 在 `transaction.on_commit(...)` 内调用 `ActionEngine.dispatch_async(alert_id, event_name)`。**告警路径上唯一同步成本是入队一个 Celery 任务。** 入队本身异常被吞掉+记日志（丰富引擎已采用此 best-effort 模式），告警流程绝不失败。
2. **Celery 任务** `process_alert_actions(alert_id, event_name)`（`@shared_task`）：
   - 加载 `event_name in trigger_events`、团队与告警重叠、`is_active` 的规则。
   - 逐规则 `event_matches(alert_payload, rule.match_rules)`，不匹配跳过。
   - **幂等插入**：try-create `ActionExecution(idempotency_key=...)`；`IntegrityError` → 已跑过 → 记 `skipped`，继续。
   - 交给 `get_handler(rule.action_type).execute(rule, alert, execution)`。
3. **JobActionHandler.execute**：
   - 经 NATS 读 `action_config.script_id` 对应的实时 Script → 拿 `content/script_type/params/timeout`。
   - `resolver` 解析目标主机（node_mgmt 运行时匹配，见 4.2.1）。**主机字段缺失/未纳管/不唯一 → 记 `config_error`，return，不调 NATS。**
   - `resolver` 构造 `params`（字段路径 \| 常量，缺失回退 default）。
   - 调 `nats_client.job_script_execute({target_source:"node_mgmt", target_list:[…], … callback_url …})`。存 `task_id` + 构造 `job_detail_url`；状态置 `running`。
   - 任何异常 → 执行 `failed` + 信息。**逐执行隔离**——某规则失败绝不波及告警或其他规则。
   - 边界：Script 已删 → `config_error`「作业不存在」；agent 离线 → job_mgmt 回报 `failed`（L1 不预检在线，见 Q4-A）。

#### 4.2.1 目标主机解析（node_mgmt 运行时匹配）
```
alert ─(target_binding.host_field, 默认 labels.ip)─► host 值
  └─ NATS node_list({ip: host, organization_ids: rule.team, skip_permission: true})
       ├─ 对返回列表做【精确 IP 相等】过滤（node_list 的 ip 是 icontains 模糊匹配，须自行收窄）
       ├─ 恰好 1 个 → 构造 {node_id: node.id, name, ip, os: operating_system, cloud_region_id: cloud_region}
       ├─ 0 个 → config_error「主机未纳管到节点管理」
       └─ >1 个（团队过滤后仍多）→ config_error「目标主机不唯一」
```
团队消歧 = 传 `organization_ids = rule.team` 收窄；精确匹配是正确性要求（防 `10.0.0.5` 命中 `10.0.0.50`）。本期不预检 node 在线状态。

### 4.3 手动触发流（Q6-A）
- API `POST /api/v1/alerts/api/action_execution/manual_trigger/`，body `{alert_id, rule_id}`（重跑亦走此）。
- 同一 handler，但：**跳过匹配评估、跳过幂等**（`idempotency_key=NULL`，`trigger_type="manual"`，记 `operator`）。重跑 = 对同一规则+告警新建执行。

### 4.4 结果回写（Q3-A 仅回调）
- `job_script_execute` 带 `callback_url` → `POST /api/v1/alerts/api/action_callback/`。
- 端点**校验 job_mgmt 的 HMAC-SHA256 签名**（复用其签名 helper），按 `task_id` 匹配 `ActionExecution`，据汇总置 `success/failed`，写 `result`，追加时间线/审计。对重复回调幂等。

### 4.5 不阻塞保证（硬性要求）
- 触发 = `on_commit` + Celery（脱离请求/聚合线程）。
- hook 入队 best-effort 吞异常；handler 异常逐执行隔离。
- 告警任一生命周期方法内**无同步 NATS/HTTP**。

## 5. 前端设计

web 告警模块在 `web/src/app/alarm/`；以 **`alertAssign`（分派规则）** 为模板克隆（已具备 列表+抽屉+OR-of-AND `MatchRule` 构建器+启停 Switch+权限门）。

### 5.1 三个界面
**(1) 规则列表 + 编辑抽屉** —— 新页 `web/src/app/alarm/(pages)/settings/actionRules/`
- `page.tsx`：克隆 `alertAssign/page.tsx`（`CustomTable` + `useSettingsTable` + `Introduction`）。列：规则名称 / 触发事件(tags) / 匹配条件摘要 / 动作类型(tag) / 状态(`Switch`) / 最近执行 / 操作(编辑·执行记录·删除)。
- `components/operateModal.tsx`：克隆 `alertAssign/operateModal.tsx`，四段：
  - ① 基本信息：规则名称、所属团队、状态
  - ② 触发时机：勾选框（友好标签 → 语义事件）；提示"未勾选的生命周期事件不会触发本规则"
  - ③ 匹配条件：**复用 `<MatchRule levelType="alert">`**
  - ④ 动作配置：动作类型 Select（本期 job；`itsm`/`webhook` disabled+tooltip 体现可扩展）→ 选择作业（异步搜索 Select，源自 job_mgmt Script 列表）→ 字段绑定 table（作业参数 ← 来自告警字段 \| 常量，由所选 Script 的 `params` 驱动）。

**(2) 执行记录列表** —— 新页 `settings/actionRecords/`。列：规则名 / 告警 / 触发方式(auto/manual) / 触发事件 / 状态 / 作业(链接→job 详情) / 时间。可按规则/状态过滤。

**(3) 告警详情"处理动作"tab + 手动触发** —— 改 `alarms/components/alarmDetail.tsx`
- `tabList` 加 `actionRecords` tab → `<ActionTimeline alertId>`（竖向时间线：状态图标、自动/手动触发·事件、时间、作业链接、失败卡片含错误+重跑按钮）。
- 扩展 `alarmAction.tsx`：加"执行动作 ▾"下拉，列适用规则（同团队、action_type=job）；选中调 `manual_trigger`。失败卡片"重跑"再调一次。

### 5.2 接线
- **API**：扩展 `web/src/app/alarm/api/settings.ts`(`useSettingApi`)：`getActionRuleList/get/create/update/delete/patch` → `/alerts/api/action_rule/`；`getActionExecutions`、`manualTriggerAction`；作业脚本查询（列表 + 取单脚本 params 供绑定表）。
- **Types**：`types/settings.ts` 增 `ActionRuleListItem`、`ActionExecutionItem`、`ActionConfig`。
- **菜单**：`constants/menu.json`（zh+en）增 `{title:"告警处理", url:"/alarm/settings/actionRules", name:"action_rules"}`（及可选执行记录）。按现有 `settings`/配置 分组嵌套（非 mockup 的顶层导航）。
- **i18n**：`locales/zh.json`+`en.json` 增 `settings.action*` keys。
- **权限**：`<PermissionWrapper>` 门控，权限位 `action_rule-Add/Edit/Delete`、`action_exec-Manual`。

### 5.3 后端 REST 面（支撑前端）
- `ActionRuleViewSet` → `/api/v1/alerts/api/action_rule/`（CRUD + PATCH is_active），团队隔离。
- `ActionExecutionViewSet`（只读 list/detail）→ `/api/v1/alerts/api/action_execution/`，按 alert/rule/status 过滤；含 `manual_trigger` action。
- `action_callback` 端点（HMAC 校验，无会话鉴权）。
- 作业脚本选择器 + params 的小读取代理（经 NATS 或现有 REST）。

## 6. 测试策略

后端按 `server/docs/testing-guide.md` + 仓库 conda recipe：
`DJANGO_SETTINGS_MODULE=settings ~/opt/anaconda3/envs/weops/bin/python -m unittest apps.alerts.tests...`（alarmcenter env，见记忆 weops-test-running-recipe）。

| 层 | 文件(后缀) | 覆盖 |
|---|---|---|
| pure | `test_action_matcher_pure.py` | OR-of-AND 对告警载荷匹配；操作符 |
| pure | `test_action_resolver_pure.py` | 字段路径解析、常量 vs 字段、**缺主机→config_error**、default 回退 |
| service(mock NATS) | `test_action_target_resolve_service.py` | node_list 匹配：**精确 IP 收窄**（`10.0.0.5` 不命中 `10.0.0.50`）；0 个→未纳管；团队过滤后 >1→不唯一；恰好 1→正确 node target |
| service(mock NATS) | `test_action_engine_service.py` | 匹配→幂等插入→分派；**重复(rule,alert,event)→skipped**；团队过滤；事件不在 trigger_events→no-op |
| service(mock NATS) | `test_job_handler_service.py` | 读 Script、解析 node target、构造 `target_source="node_mgmt"` payload、存 task_id/url；NATS 失败→failed 且告警无损 |
| service | `test_action_callback_service.py` | HMAC 校验(好/坏)、task_id 匹配、状态翻转、重复回调幂等 |
| views | `test_action_rule_views.py` | CRUD+PATCH、团队隔离、权限门 |
| views | `test_manual_trigger_views.py` | 手动绕过匹配+幂等；重跑新建执行；记 operator |
| bdd | `tests/bdd/action_engine.feature` + `test_action_engine_bdd.py` | 中文 Gherkin：创建命中→触发作业→回写成功时间线；手动重跑失败动作 |

前端门：`pnpm type-check` + `pnpm lint`。

## 7. 显式处理的边界

- **告警流绝不阻塞/失败**：hook=on_commit+Celery、入队 best-effort 吞异常、逐执行 try/except。
- **幂等竞态**：并发触发 → DB 唯一约束 → 一 `success` 一 `skipped`，非两次作业。
- **手动不限**：`idempotency_key=NULL` → 无冲突。
- **缺主机信息 / 未纳管 / 不唯一**：`config_error`，不调 NATS（自愈仅触达已纳管到节点管理的主机）。
- **agent 离线**：不预检，job_mgmt 回报 `failed`，可手动重跑。
- **配置与运行间脚本被删/改**：运行时读取——删则 `config_error`「作业不存在」。
- **回调丢失**：执行停留 `running`（L1 接受），手动重跑兜底。
- **规则删除后**：`rule` FK 可空 → 历史记录存活。

## 8. 可扩展性证明（本期定形，后续只加动作类型）

加 ITSM/Webhook = (1) 新 `handlers/itsm.py` 实现 `ActionHandler.execute`，(2) `registry.py` 注册，(3) 前端动作类型 Select 启用该项。**不改动** `ActionRule`/`ActionExecution`/engine/matcher/触发 hook/回调。`scope="incident"` 字段已为 L2 预留。
