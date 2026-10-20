# CMDB → 监控同步任务 Implementation Plan

> **For agentic workers:** 按任务顺序实现。本会话内联执行。不要提交，除非用户要求。规格未改为 `ready` 前不要开工。

**Goal:** 列表「同步到监控」收成可回来的跨模块任务：先无凭据自动关联；对不上的按监控对象生成接入草稿；用草稿 ID 跳监控接入页预填身份。任务本身独立于 CMDB / 监控核心；对端未装或无许可时入口不出现；任务记录延时回收。

**Architecture:** 新建胶水 app `apps.module_link` + 前端 `web/src/app/module-link/`。胶水模块始终装入；入口按 CMDB / 监控许可 fail-closed。第一段仍调用现有 `CmdbToMonitorPushService.push_instance`（limit 100）。任务页、草稿、回收、读草稿 HTTP 都在本模块。CMDB 资产页只留薄按钮；监控接入页只消费 `cmdb_draft`。

**Tech Stack:** Django / DRF / Celery Beat、Next.js、Ant Design。本期同步执行建任务，不上异步队列。

规格：`specs/changes/cmdb-monitor-link-task/spec.md`  
交互稿：`docs/design/product-decisions/cmdb-monitor-link-task.html`

---

## 请确认后再实现

1. **独立胶水模块，不是新的可售卖应用。** 后端 `apps.module_link`，前端路由 `/module-link/cmdb-monitor/tasks/[id]`。不进顶栏应用列表，不单独许可。
2. **对端不可见则入口不出现（fail-closed）。** `clientData` 加载中、为空、或不含 `monitor` 时，CMDB 列表/详情的同步按钮都不渲染。监控侧将来的反向入口同理看 `cmdb`。现网 `isMonitorSold` 空列表当 true，本入口不再沿用。
3. **服务端始终装入胶水模块。** `module_link` 与 `system_mgmt` / `console_mgmt` 一样 always-on；入口只按 CMDB、监控许可控制。许可闸对 `/api/v1/module_link/` 继承 cmdb+monitor 授权，不把胶水当成可售卖应用。EE `LicenseAppGuard` 按 URL 第一段当 SKU，OSS 把该前缀写入 `LICENSE_EXEMPT_PREFIXES`，再由 `ModuleLinkLicenseInheritMiddleware` 要求 cmdb+monitor 都已授权。
4. **CMDB / 监控只留薄适配。** 详情手绑、单条 `push_to_monitor`、ingest 身份规则仍留在各自核心。任务表、任务页、草稿、回收、读草稿接口搬出 CMDB。
5. **100 条同步跑完。** 与现网 `BATCH_PUSH_LIMIT` 相同，不上 Celery 执行第一段。
6. **草稿一组一个监控对象，但接入前先选模板。** 「去配置」跳到该对象的监控接入列表（带着 `cmdb_draft`），人选内置插件或 DIY 模板后再进配置页。任务不默认同名内置插件。
7. **无内置映射的自定义模型：任务内指定对象，不改常量映射表。** 进「待指定对象」桶；人选监控对象后才生成草稿，并可把 `model_id → object_name` 记在胶水模块。自动关联只用已有 ID + 该对象下唯一实例名；仅当选中的对象本身已有内置身份规则才套 IP 等规则。K8s / 云 / vCenter 仍 skipped，不走指定对象。
8. **延时回收 7 天。** 从任务创建起算；每日 Beat 删除到期的任务、行、草稿。不拆 CI / 监控实例上已写的关联 ID。过期草稿读取失败。
9. **反向后置。** 同一模块以后可接监控 → CMDB，本期不做。

---

## 模块边界

```text
CMDB 资产页  --薄按钮-->  module_link 任务页/API
                              |  第一段：调 cmdb push_instance
                              |  草稿：本模块存与读
监控接入页  --cmdb_draft-->  module_link GET 草稿
                              |
                              +-- Beat 7 天后删任务记录
```

- **装入条件：** `module_link` 始终装入（always-on）。显式 `INSTALL_APPS` 不必手写它。
- **许可：** 前端信源是已授权应用列表，CMDB 与监控都可见才出入口。后端许可闸同样要求两边都已授权。
- **不是** 顶栏 Client，不进 `license_mgmt` 模块清单。
- 日志：`apps.core.logger` 增加 `module_link_logger`。

---

## 数据与协议

### 模型（`apps.module_link`）

`MonitorLinkTask`：`id`(UUID)、`operator`、`team`、`status`（`waiting_access` / `completed` / `cancelled`）、`summary` JSON、`retain_until`、时间戳。

第一段同步完成后：有待接入行 → `waiting_access`；否则 `completed`。取消不改已写关联。

`MonitorLinkTaskItem`：`task`、`inst_uuid`、`model_id`、`object_name`、`status`、`monitor_id`。

`MonitorAccessDraft`：`id`(即 `cmdb_draft`)、`task`、`object_name`、`rows`(无凭据)、`expires_at`（与 `retain_until` 对齐）。

草稿行：`inst_uuid`（`cmdb_id`）、`inst_name`、`ip`、`organization` / `group_ids`、`cloud_region_id`、`model_id`。内置映射的 `not_found`，以及人指定对象之后的行。

`ModuleLinkModelMap`：`team` + `model_id` → `object_name`。只给自定义/表外模型记默认对象，不覆盖内置常量。

`retain_until` = 创建时刻 + 7 天。常量一处定义，回收与草稿过期共用。

### 回收

- Beat：每日（建议 03:30，避开现网凌晨其它清理亦可）。
- `retain_until <= now` 的任务 CASCADE 删 Item / Draft。
- 有界批次（如每次 500），INFO 只打删除条数。
- 断言：被删任务对应 CI 的 `monitor_id` 仍在。
- 人打开过期任务 URL → 404；过期草稿 → 404。

### HTTP（`/api/v1/module_link/`，非 OpenAPI）

权限沿用 `asset_info-Edit` 做写；读任务用同一资产权限或任务创建人+组织（与现网 batch 逐条授权一致：无权行 `failed`，不整批 403）。对端 app 未装入则本路由不存在。

- `POST /api/v1/module_link/cmdb_monitor_tasks/` `{ inst_uuids }`
- `GET /api/v1/module_link/cmdb_monitor_tasks/{id}/`（刷新：`not_found` 且 CI 已有 `monitor_id` 则升为 `ok`）
- `POST /api/v1/module_link/cmdb_monitor_tasks/{id}/cancel/`
- `GET /api/v1/module_link/access_drafts/{id}/`（监控接入页直拉；校验组织；无凭据）

旧 `POST /cmdb/api/instance/batch_push_to_monitor/` 保留内部/兼容，UI 不再当终态。编排实现迁到 `module_link`，可内部调用现有 `MonitorLinkService.batch_push` 或把 batch 函数挪过来、cmdb 薄封装。

### 跳转与接入

1. CMDB 按钮 → 建任务 → `/module-link/cmdb-monitor/tasks/{id}`
2. 已有映射的「去配置」→ `/monitor/integration/list?name=Host&cmdb_draft=<uuid>`（侧栏落到该对象，卡片含内置和 DIY）。点某一模板后，现有 `buildIntegrationConfigureUrl` 再加上 `cmdb_draft` 进配置页。
3. 无映射行：任务页先选监控对象（可勾选「以后这个模型都对到它」写入胶水表），再走第 2 步。
4. 接入页拉草稿预填身份；表格列以所选模板为准，草稿没有的列留空给人补。
5. 提交走现有 `updateNodeChildConfig`；`cmdb_id` 写入 `MonitorInstance`，再回写 CI `monitor_id`。
6. 回任务页刷新即见已关联。

### 无映射怎么同步（不改内置常量）

`CMDB_MODEL_TO_MONITOR_OBJECT` 仍然只表示产品已承认的一对一关系（host→Host 等）。自定义模型、以及 weblogic 这类表外模型：

- 不进自动类型身份认领（ingest 对无 `object_name` 本来就 skip 类型身份）。
- 任务 Item 状态 `needs_object`（或沿用 `skipped_model` 再拆一桶）。任务页展示「无对象映射」。
- 人指定 `object_name` 后：同对象下按已有 `cmdb_id` / 唯一实例名再认领一轮；仍没有则生成该对象草稿。
- 可选持久化 `ModuleLinkModelMap(team, model_id, object_name)`，下次默填。
- 列表入口：监控可用时自定义模型也可以出同步按钮（不再只靠 `canSyncMonitor` 白名单）。平台树模型（k8s_*、云账号、vCenter）继续隐藏或同步后记 skipped，文案写清不是一对一。

---

## 文件

| 文件 | 职责 |
|---|---|
| `server/config/components/app.py` | `module_link` 作为 always-on 始终装入 |
| `server/apps/core/logger.py` | `module_link_logger` |
| `server/apps/module_link/` | app、models、migration、views、urls、services、celery recycle、`config.py` Beat |
| `server/apps/cmdb/services/monitor_link.py` | 第一段认领可被胶水调用；列表批量 UI 不再当终态 |
| `server/apps/monitor/services/node_mgmt.py`（或创建后钩子） | 带 `cmdb_id` 创建后回写 CI |
| `web/src/app/module-link/` | 任务页、API client、locale |
| `web/src/app/cmdb/(pages)/assetData/page.tsx` 等 | 入口：CMDB 与监控都有许可且非 loading |
| `web/src/app/monitor/.../configure/` | 读 `cmdb_draft`，向 module_link 拉行并预填 |
| 测试见下 | 装入闸、回收、入口隐藏、任务分桶 |

不改：扫描、映射表、详情手绑语义、对外 OpenAPI、顶栏 Client 清单。

---

### Task 1: 胶水 app 装入闸 + 空壳

- 新 Django app、`apps.py`、urls 占位。
- `app.py`：`module_link` 加入 always-on，始终装入。
- 测试：只装 cmdb / 只装 monitor / 显式 INSTALL_APPS 未写出时都仍装入。

### Task 2: 任务模型 + 第一段落库 + 回收

- 表、`retain_until`、CASCADE。
- `create`：调现有 batch/push_instance，写 Item / Draft / summary。
- `recycle_expired(now)`：删到期任务；不碰关联字段。
- Beat 注册。
- 测试：分桶、已关联不进草稿、冲突不进草稿、超 100 拒绝、取消后草稿 404、回收删记录且 `monitor_id` 仍在、未到期不删。

### Task 3: HTTP

- 建 / 查 / 取消 / 读草稿。
- 逐条鉴权与现网 batch 同等。
- 模块未挂载时无路由（装入测即可）。
- 测试：无权行 failed、过期 404、草稿响应无密码。

### Task 4: 接入预填与 `cmdb_id` 回写

- configure 读草稿、解析插件、预填表格。
- 无 `cmdb_draft` 的普通接入不变。
- 创建带回写 CI。

### Task 5: 独立任务页 + 选模板 + 入口闸

- `/module-link/cmdb-monitor/tasks/[id]`：摘要、分桶、待指定对象、去配置、冲突手绑。
- 「去配置」进监控接入列表并带上 `cmdb_draft`；点模板卡片再进 configure。接入列表需把 query 里的草稿 ID 传进 `buildIntegrationConfigureUrl`。
- 待指定对象：选监控对象、可选记住映射、再生成草稿。
- CMDB 列表确认后跳任务页。监控可用且非平台树模型即可出按钮（含自定义模型）；加载中 / 空列表 / 无 monitor 不显示。
- 不往 `cmdb/constants/menu.json` 加菜单项。
- locale；`pnpm type-check`。

### Task 6: 收口

- spec → implemented；产品记忆去掉拟决议。
- 不实现反向任务。

---

## 验证

```bash
cd server && uv run pytest \
  apps/core/tests/test_enterprise_footprint.py \
  apps/cmdb/tests/test_monitor_link_batch.py \
  apps/cmdb/tests/test_monitor_link_bind.py \
  apps/cmdb/tests/test_monitor_link_views.py \
  apps/module_link/tests/ \
  apps/monitor/tests/test_module_ingest.py \
  --no-cov
```

（文件名以新增为准。cmdb 关联测若 sqlite 迁移失败，沿用 postgres `--reuse-db`。）

```bash
cd web && pnpm type-check
```

浏览器：无 monitor 时按钮不出现；已映射模型 → 任务页 → 选 DIY 模板 → 预填接入；自定义模型 → 指定对象 → 再选模板。实现时用可用的浏览器工具走这三条。

---

## 明确不做

- 新的可售卖 / 顶栏应用
- 监控 → CMDB 任务
- Celery 执行第一段 / 突破 100
- 无凭据暗建、CMDB 发明采集配置
- K8s / 云 / vCenter 子对象草稿
- 扫描工作队列、对外 OpenAPI
- 回收时解除身份关联
