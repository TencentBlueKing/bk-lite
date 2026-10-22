# 监控 → CMDB 同步任务 Implementation Plan

> **For agentic workers:** 按任务顺序实现。本会话内联执行。不要提交，除非用户要求。规格未改为 `ready` 前不要开工。

**Goal:** 监控资产列表「同步到 CMDB」收成可回来的胶水任务：先只关联身份；CMDB 没有的经确认后新建 CI。已关联不改台账。无映射 / 无许可则入口不出现。

**Architecture:** 仍在 `apps.module_link`。新建反向任务表与 HTTP，不复用 `waiting_access`。第一段指针绑定；第二段确认后走 CMDB 创建（ingest 的 create，禁止 upsert 已有字段）。监控列表只留薄按钮；任务页在 `/module-link/monitor-cmdb/tasks/[id]`。

**Tech Stack:** Django / DRF / 现有 Beat、Next.js、Ant Design。第一段与确认新建均同步执行，不上队列。

规格：`specs/changes/monitor-cmdb-link-task/spec.md`  
对照稿：`docs/design/product-decisions/cmdb-monitor-link-task.html`（反向「同步数据」屏本期不实现）

---

## 已确认（开工按此执行）

1. **同一胶水模块。** 许可继承已有；不新开 SKU。
2. **第一期不做字段覆盖。** 已关联进桶即可，无「同步数据 / 保持 CMDB」。
3. **待新建必须确认。** 未点确认不建 CI。
4. **禁止默认 host。** 反向映射只倒 `CMDB_MODEL_TO_MONITOR_OBJECT`。
5. **禁止列表直调 `push_to_cmdb`。** 那条 API 会 ingest upsert。
6. **100 条、7 天回收、冲突手绑、平台树跳过。** 与正向一致。
7. **无映射对象第一期不指定模型。** 入口不出现；误传入则 `skipped_model`。

---

## 模块边界

```text
监控资产列表  --薄按钮-->  module_link 反向任务页/API
                              |  第一段：指针关联（不改 CI 字段）
                              |  第二段：确认后新建缺失 CI
正向任务 / 接入草稿 / 主机创建钩子  不动
```

- 入口：当前监控对象名能倒到 CMDB `model_id`，且 cmdb+monitor 许可都在，且非平台树。
- 写确认：监控实例可操作 + CMDB `asset_info-Edit`。无权行 `failed`。

---

## 数据与协议

### 模型

`MonitorCmdbTask`：`id`、`operator`、`team`、`object_name`、`status`（`waiting_create` / `completed` / `cancelled`）、`summary` JSON、`retain_until`。

`MonitorCmdbTaskItem`：`task`、`monitor_id`、`object_name`、`model_id`、`inst_name`、`ip`、`organization`、`cloud_region_id`、`status`、`cmdb_id`。

第一段结束后：存在 `not_found` → `waiting_create`；否则 `completed`。确认新建把对应行改为 `ok` 并填 `cmdb_id`；不再有 `not_found` 则 `completed`。

`retain_until` 与正向共用 7 天常量。现有 Beat 回收函数同时删两类过期任务。

### HTTP（`/api/v1/module_link/`，非 OpenAPI）

- `POST /api/v1/module_link/monitor_cmdb_tasks/` `{ monitor_ids, object_name }`
- `GET /api/v1/module_link/monitor_cmdb_tasks/{id}/`
- `POST .../{id}/cancel/`
- `POST .../{id}/create_missing/` `{ item_ids }`
- 冲突手绑：复用现有监控/CMDB bind 接口，不新开 OpenAPI。

### 第一段关联（不得 upsert）

顺序：成对 ID 仍有效 → already_linked；否则按模型身份唯一命中则只写指针 → ok；多命中 → conflict；零命中 → not_found。

实现上复用 bind（`cmdb_id` ↔ `monitor_id`），不要走 `MonitorToCmdbPushService.push_instance` / CMDB ingest upsert。

### 确认新建

只接受本任务 `not_found` 且仍无 `cmdb_id` 的行。创建字段：名称、IP、云区域、组织、`monitor_id`。成功后回写监控 `cmdb_id`。失败逐行 `failed`，并把可上屏的原因写入该行 `message`。不带凭据。

---

## 文件

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/constants/monitor_link.py` | 增加倒映射函数；未知对象返回空，不默认 host |
| `server/apps/module_link/models.py` 与 migration | 反向任务表 |
| `server/apps/module_link/constants.py` | 反向状态、与正向共用 BATCH/RETAIN |
| `server/apps/module_link/services/monitor_cmdb.py` | 建任务、关联、确认新建、序列化 |
| `server/apps/module_link/views.py` / `urls.py` | 反向 ViewSet |
| `server/apps/module_link/tasks.py` | 回收覆盖新表 |
| `web/src/app/cmdb/utils/systemLinkage.ts` | `canOpenCmdbLink` |
| `web/src/app/monitor/(pages)/integration/asset/page.tsx` | 薄按钮 |
| `web/src/app/module-link/api.ts` | 反向 client |
| `web/src/app/module-link/monitor-cmdb/tasks/[id]/page.tsx` | 任务页：分桶、确认新建、冲突手绑 |
| locale | 中英 |

不改：正向任务、接入草稿、扫描、`push_to_cmdb` 内部语义、主机创建钩子、对外 OpenAPI。

---

### Task 1: 倒映射 + 入口闸纯函数

- 倒 `CMDB_MODEL_TO_MONITOR_OBJECT`；`builtin_model_id("Host") == "host"`；`"Weblogic"` / 空 → `None`。
- `canOpenCmdbLink(clientData, loading, objectName)`：两边许可、非 loading、能倒出 model、非平台树。
- 测试：映射与 fail-closed。勿改 ingest 默认 host 行为（那是钩子路径）。

### Task 2: 任务表 + 第一段关联

- 模型、migration、`MonitorCmdbTaskService.create(monitor_ids, object_name, request)`。
- 超 100 / 空列表 / 对象无映射 → 400 或行 skipped。
- 断言：命中已有 CI 时名称等字段与调用前相同；只多了成对指针。
- 日志：任务完成 INFO 汇总；行失败 DEBUG/WARNING 带 `monitor_id`、`failed_stage`、`error_type`，无 payload。

### Task 3: HTTP + 确认新建

- ViewSet 与路由。
- `create_missing`：校验 item 属于本任务且 `not_found`；调用创建；刷新 summary。
- 未确认时 CMDB 无新 CI。
- 权限：监控操作权建任务；确认新建叠加 `asset_info-Edit`。
- 取消：状态 cancelled，指针保留。

### Task 4: 任务页 + 监控列表入口

- 按钮：许可闸 + 当前对象可映射。
- 建任务后跳 `/module-link/monitor-cmdb/tasks/{id}`。
- 分桶：待新建 / 冲突 / 本次关联 / 已关联 / 失败 / 跳过。
- 待新建：「写入所选 CI」，确认框写清会按监控名称和 IP 新建。
- 冲突：打开现有手绑。
- 无「同步数据」。

### Task 5: 回收 + 收口

- Beat 同时删过期正向/反向任务。
- 过期 GET 404；指针仍在。
- 更新本 spec 为 implemented；产品记忆改「当前规格」与后置项。
- 验证命令见下。

---

## 验证

```bash
cd server && uv run pytest \
  apps/cmdb/tests/test_monitor_link_catalog.py \
  apps/module_link/tests/ \
  apps/monitor/tests/test_push_to_cmdb.py \
  --no-cov
```

```bash
cd web && pnpm type-check
```

浏览器：无 CMDB 许可时监控列表无按钮；Host 勾选未关联 → 任务页待新建 → 确认后 CMDB 有 CI 且双方 ID 成对；已关联勾选进已关联桶且 CI 字段不变。

---

## 后置（本计划不做）

- 字段覆盖白名单与「同步数据」屏
- 未关联队列
- 无映射对象手指定 CMDB 模型
