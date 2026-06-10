# CMDB 自定义上报后端实现设计（cmdb_enterprise）

- 日期：2026-06-10
- 状态：已确认设计，待写实施计划
- 范围：把已存在的前端（`web/src/app/cmdb/(pages)/assetManage/customReporting/`）对接起来；全部业务逻辑落在 `apps.cmdb_enterprise`，社区侧（`apps.cmdb`）只留薄壳委托。

## 背景与现状（实测，2026-06-10）

> 注意：`server/apps/cmdb/context.md` 已过时且会误导（它描述的 `apps.cmdb.enterprise` overlay、`0024_custom_reporting` migration、各 service 在磁盘上都不存在）。以本文为准。

已存在、本期复用 / 不重做：

- **企业 app 已建**：`server/apps/cmdb_enterprise/`，`apps.py:ready()` → `registry_hooks.py` 注册 `model_ops`/`instance_ops`/`collect`。`instance_ops`（附件/图片字段）是完整的参考实现范式（provider/service/storage/tasks）。
- **自定义上报模型已落库**：`cmdb_enterprise/custom_reporting/models.py` + migration `0002_...`，含
  `CustomReportingTask`（`sync_scopes`）、`CustomReportingTaskScope`、`CustomReportingCredential`（令牌 issue/rotate/revoke/hash/`matches_token`/`mark_used` 全生命周期，已测）、`CustomReportingBatch`、`CustomReportingPendingRelation`、`CustomReportingCleanupReview`。
- **社区契约 + 委托已就位**：`apps/cmdb/custom_reporting/extensions.py`（`CustomReportingExtension` 默认 no-op）、`apps/cmdb/extensions/registry.py`（IoC 注册表）、`ModelManage` 已有 7 个委托方法（`register_custom_reporting_model_fields`/`validate_custom_reporting_instance_fields`/`_get_custom_reporting_declared_attr_ids`/`validate_custom_reporting_relation_fields`/`normalize_custom_reporting_identity_keys`/`bootstrap_custom_reporting_model`/`sync_custom_reporting_model_group`）。
- **变更场景已就位**：`CUSTOM_REPORTING_CHANGE = "custom_reporting_change"`，migration `0024_alter_changerecord_scenario` 已落地；`utils/change_record.py:create_custom_reporting_change_record` 可用。
- **复用引擎**：合并 `collection/common.py:Management`（old/new diff + 清理策略）；身份查询 `services/instance.py:query_entity_by_identity`（~1083，当前按 Python 值类型选 `int=`/`str=`，即 P0 幂等隐患点）；关系 `services/instance.py:instance_association_create`；建模 `services/model.py:create_model`/`create_model_attr`；权限 `views/mixins.py:CmdbPermissionMixin` + `utils/base.py:get_current_team_from_request`；URL 自动发现 `server/urls.py`（每 app 挂 `api/v1/<app_name>/`）。

前端（已完整，本期不动）：`page.tsx` + `taskTable/taskDetail/taskWizard/batchReviewDrawer`、API client `api/customReporting.ts`（base `/cmdb/api/custom_reporting/tasks`）、`types/customReporting.ts`、menu 入口。`batchReviewDrawer` 只读展示，不含 approve/reject 按钮；管理前端不调 ingest 接口。

## 已定决策

1. **实现位置**：业务逻辑全部在 `apps.cmdb_enterprise`；社区只薄壳委托，社区代码从不 import 企业模块，只 `registry.get("custom_reporting", ...)`。
2. **HTTP 接线**：薄壳 `CustomReportingTaskViewSet` 落在 `apps.cmdb`（路由必须挂 `api/v1/cmdb/` 前缀才能对上前端 `/cmdb/api/custom_reporting/...`），每个 action 仅委托到注册表扩展。沿用 `instance_ops` 既有范式。
3. **快照清理**：超删除比例阈值 → 建 `CleanupReview(pending)` 不直接删；后端提供 approve/reject 接口，approve 才执行删除。
4. **expire 清理机制**（已确认可接受）：合并时给覆盖到的实例打 `cr_last_reported_at` 属性；celery beat 定时删除该任务模型下超期未覆盖实例。不引入覆盖时间侧表。
5. **清理删除范围**（已确认）：按 task 的 `model_id` + `team/org` 限定；snapshot 主要面向任务自有快速模型（与任务 1:1，安全）。

## 架构与接线

```
前端 /cmdb/api/custom_reporting/tasks/...
  → next proxy → 后端 api/v1/cmdb/api/custom_reporting/tasks/...
    → 薄壳 CustomReportingTaskViewSet (apps.cmdb, 仅委托)
      → get_custom_reporting_extension()  (registry 槽位 "custom_reporting")
        → cmdb_enterprise/custom_reporting/provider.py + services/*
```

新增文件：

社区 `apps/cmdb`：
- `views/custom_reporting.py` — 薄 ViewSet（session 型 action 委托；ingest 为 AllowAny + Bearer 校验）。
- `serializers/custom_reporting.py` — DRF 序列化器，字段对齐 `types/customReporting.ts`。
- `custom_reporting/extensions.py` — **扩充** HTTP 契约方法（见下）；默认实现：写操作抛 `BaseAppException("自定义上报为商业版能力，未启用")`，list 返回空分页。
- `urls.py` — `router.register(r"api/custom_reporting/tasks", CustomReportingTaskViewSet, ...)`，并为 ingest 注册独立路由。

企业 `cmdb_enterprise/custom_reporting`：
- `provider.py` — `class CustomReportingProvider(CustomReportingExtension)` 实现全部契约；`get_custom_reporting_extension()` 返回单例。
- `services/task_service.py` / `credential_service.py` / `ingest_service.py` / `merge_service.py` / `relation_service.py` / `cleanup_service.py` / `document_service.py` / `model_service.py`。
- `tasks.py` — expire 清理 celery 任务；`config.py` 追加 beat 条目。
- `registry_hooks.py` — 追加 `registry.register("custom_reporting", get_custom_reporting_extension())`。

## HTTP 契约（对齐前端）

会话型（session 鉴权）：

| 方法 | 路由 | 契约方法 | 说明 |
|---|---|---|---|
| GET | `/tasks/` | `list_tasks(request, params)` | 分页，按 team/org 过滤 |
| POST | `/tasks/` | `create_task(request, payload)` | 含内联快速模型 bootstrap + 自动签发凭据 |
| GET | `/tasks/{id}/` | `get_task(request, id)` | 详情（含 last_reported_at/recent_batches/review_status_summary） |
| PUT | `/tasks/{id}/` | `update_task(request, id, payload)` | 同名同组织唯一 |
| DELETE | `/tasks/{id}/` | `delete_task(request, id)` | |
| GET | `/tasks/{id}/batch_activity/` | `get_batch_activity(request, id)` | batches + cleanup_reviews + review_status_summary |
| GET | `/tasks/{id}/onboarding_document/` | `get_onboarding_document(request, id)` | endpoint/auth_header/identity_keys/example_payload |
| POST | `/tasks/{id}/issue_credential/` | `issue_credential(request, id, params)` | 返回明文 token（仅此一次） |
| POST | `/tasks/{id}/rotate_credential/` | `rotate_credential(request, id, credential_id)` | |
| POST | `/tasks/{id}/revoke_credential/` | `revoke_credential(request, id, credential_id)` | 作废后立即拒收，不影响他任务 |
| POST | `/tasks/{id}/reviews/{review_id}/approve/` | `approve_cleanup_review(...)` | approve 才执行删除 |
| POST | `/tasks/{id}/reviews/{review_id}/reject/` | `reject_cleanup_review(...)` | |

机器型（Bearer token 鉴权，AllowAny + 手动校验）：

| 方法 | 路由 | 契约方法 | 说明 |
|---|---|---|---|
| POST | `/ingest/` | `ingest(request, token, payload)` | 校验 `Authorization: Bearer <token>` → `Credential.matches_token` |

ingest 请求体：`{ instances: [...], relations: [...], batch_metadata: {...} }`。

## Ingest / 合并流水线

1. Bearer token → 命中 credential → task；`credential.mark_used()`；task 未启用或凭据作废 → 拒收（401/403）。
2. 建 `CustomReportingBatch(status=running)`。
3. 解析目标模型：完整模型用既有 `model_id`；快速模型新字段经 `register_model_fields` 自动登记为未定型字符串。
4. **P0 身份归一化**：按模型属性元数据类型把 identity 值 coerce（int/str），再 `query_entity_by_identity`，保证 `123` 与 `"123"` 命中同一实例（幂等）。覆盖非法类型的拒绝/规范化路径。
5. 按清理策略 upsert（复用 `Management`）：
   - **none**：只增改，不删。
   - **expire**：增改 + 给覆盖实例打 `cr_last_reported_at`；celery 定时删除该任务模型下超期未覆盖实例。
   - **snapshot**：本批为全量真相，算待删集合；删除比例 ≤ 阈值直接删，> 阈值建 `CleanupReview(pending)` 不删。
6. 关系上报三情形：本批互引 / 引用已存在实例 → `instance_association_create`；引用未落地目标 → `CustomReportingPendingRelation`，后续目标落地回填。关系类型仅正式模型定义，经 `validate_relation_fields` 校验；快速模型实例可作为关系目标被引用，但自身不声明关系类型。
7. 每次合并写 `scenario=CUSTOM_REPORTING_CHANGE` 变更记录。
8. `batch.summary` 落 `instances_received/relations_received/created/updated/deleted/errors/pending_relations`；状态 success/failed；最后刷新 `task.last_reported_at`（放在全部必需持久化之后）。

## 测试策略（严格 TDD）

- 分层沿用仓库约定：`_pure`（无 DB）/ `_service`（mock 图）/ `_views`（DRF `api_client`），落 `cmdb_enterprise/tests/`。
- 现成锚点：`tests/test_custom_reporting_model_behavior.py` 的 3 个 skip 测试，provider 注册 bootstrap/sync 后激活并精确锁定行为。
- 新增覆盖：薄壳委托、契约 no-op（未启用）、序列化器、task CRUD、凭据签发/轮换/作废、ingest（token 鉴权 + `123`/`"123"` 幂等）、关系三情形 + 回填、三档清理 + 阈值→待审核、approve/reject 执行删除、接入文档、变更场景可独立检索。
- 一条 BDD feature（中文 Gherkin）串验收主流程。

## 实施切片（供 writing-plans）

1. provider 骨架 + 注册 + 契约扩充 + 薄壳 ViewSet + 序列化器 + task CRUD（激活 model-behavior skip 测试）
2. 凭据三接口
3. 接入文档
4. ingest + 实例 upsert + P0 归一化 + 批次（none 策略）
5. 关系（互引 / 现有 / pending 回填）
6. 清理策略 expire + snapshot + 阈值→审核
7. 审核 approve/reject + 执行删除
8. 变更场景集成 + batch_activity/detail 聚合
9. 端到端验证 + 验收 BDD

## 不做（Out of Scope）

- 不调度 / 不感知客户脚本生命周期（调度、重试、失败处理归客户侧）。
- 不为自定义上报单独做拓扑 / 可视化（沿用现有资产查询与拓扑）。
- 快速模型不进模型管理导入导出。
- 自动关联规则仅在目标为正式模型时生效，快速模型上不生效。
- 不做「快速模型转正式模型」升级通路。
- 不做客户脚本模板库 / 脚本托管。

## 验收标准（对齐原始需求）

1. 不开发插件、不改平台代码，靠自有脚本即可把任意对象数据持续上报进 CMDB。
2. CMDB 内可独立完成任务新建/编辑/删除/列表/详情。
3. 任务可绑完整模型，也可创建时内联快速模型；快速模型模型名 / 身份键 / 清理策略三项必填。
4. 上报合并结果、关系建立、自动关联规则触发与自动发现一致。
5. 关系三情形均支持，第三种目标落地后自动补齐。
6. 三档清理均按定义生效；快照超阈值进待审核而非直接删。
7. 每批留可追溯批次记录（时间 / 计数明细 / 整体状态）。
8. 每任务可获取接入文档（端点 / 凭证用法 / 数据格式 / 字段含义）。
9. 自定义上报合并均归入 `custom_reporting_change` 场景，可独立检索。
10. 凭证可独立轮换 / 作废，作废后立即拒收且不影响其他任务。
