# Historical Superpowers change: 2026-06-17-cmdb-operation-log-coverage-gaps

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-17-cmdb-operation-log-coverage-gaps.md

- 日期：2026-06-17
- 状态：**仅盘点记录,未实施**。后续有空再做。
- 关联：`docs/superpowers/specs/2026-06-17-cmdb-alert-audit-log-nats-mirror-design.md`(已实现的 NATS 镜像方案)

## 背景

平台「系统管理 → 操作日志」(`system_mgmt.OperationLog`)接收 CMDB 条目的**唯一途径**是 `apps/cmdb/utils/change_record.py` 里的镜像:`create_change_record` / `batch_create_change_record` / `create_change_record_by_asso` 仅当 `scenario ∈ {MODEL_MANAGEMENT_CHANGE, COLLECT_AUTOMATION_CHANGE, CUSTOM_REPORTING_CHANGE, RELATION_CHANGE}` 时镜像;`ordinary_attribute_change` / `device_lifecycle` 不镜像(实例数据变更,有意排除)。

→ 因此 CMDB 写操作只有在(经服务层)写了**管理类 scenario 的 ChangeRecord** 时才会出现在操作日志里。很多管理类视图根本不写 ChangeRecord,故操作日志里看不到。

## 已记录(✅ 写管理类 ChangeRecord → 已镜像)

| 视图/动作 | scenario | 证据 |
|---|---|---|
| `ModelViewSet.create`(create_model) | MODEL_MANAGEMENT_CHANGE | `services/model.py:546` |
| `ModelViewSet.model_copy`(copy_model) | MODEL_MANAGEMENT_CHANGE | `services/model.py:762` |
| `ModelViewSet.model_attr_create` | MODEL_MANAGEMENT_CHANGE | `services/model.py:940` |
| `ModelViewSet.model_attr_update` | MODEL_MANAGEMENT_CHANGE | `services/model.py:1061` |
| `ModelViewSet.model_attr_delete` | MODEL_MANAGEMENT_CHANGE | `services/model.py:1218` |
| `CollectModelViewSet` create/update/destroy | COLLECT_AUTOMATION_CHANGE | `services/collect_service.py` |
| 实例关联 create/delete | RELATION_CHANGE | `services/instance.py`(create_change_record_by_asso) |

> 注:此处已修正初次盘点的错误——初稿误称「model update/delete 记了、attr/copy 没记」,实际**相反**:`services/model.py` 仅 5 处 `create_change_record`,分别在 create_model / copy_model / create_model_attr / update_model_attr / delete_model_attr;`update_model`(`services/model.py:792`)与 `delete_model`(`:784`)**不写任何 ChangeRecord**。

## 按设计排除(⚪ 实例数据,走 change_record 但不镜像)

实例 create / update / delete / batch_delete / batch_update / import —— 全部 `ordinary_attribute_change`,有意不进平台操作日志(由 change_record 自身承载)。

## 未记录(❌ 操作日志看不到)—— 待补充候选

### ① 模型结构管理（含明显缺口）
- `ModelViewSet`: **update**(改模型)、**destroy**(删模型) ← ❗create 记了但改/删没记,最明显的不一致
- `model_association_create` / `model_association_delete` / `model_association_batch_delete`(模型级关联)
- `model_unique_rules` / `model_unique_rule_detail`(唯一规则)
- `model_auto_association_rules` / `model_auto_association_rule_detail`(自动关联规则)
- `save_layout`(模型/分类布局)
- `import_model_config`(导入模型配置)
证据:`apps/cmdb/views/model.py` 对应方法的服务调用均无 `create_change_record*`。

### ② 模型元数据管理
- `ClassificationViewSet` create/update/destroy（`services/classification.py` 无日志）
- `FieldGroupViewSet` create/update/destroy/move/batch_update_attrs/update_attr_group/reorder_group_attrs
- `PublicEnumLibraryViewSet` create/update/destroy

### ③ 订阅
- `SubscriptionViewSet` create/update/partial_update/destroy/toggle（纯 ORM,无日志）

### ④ 采集与同步
- `CollectToolViewSet.execute`（调试执行,仅写临时 debug 态）
- `NodeMgmtSyncViewSet` task(PUT) / run_sync / run_collect
- `OidModelViewSet` create/update/destroy
- `ConfigFileVersionViewSet.create_manual` / `destroy`

### ⑤ 自定义上报（⚠️ 社区版 no-op）
- `CustomReportingTaskViewSet` create/update/destroy/issue_credential/rotate_credential/revoke_credential/approve_review/reject_review
- `CustomReportingIngestViewSet.create`
说明:社区版视图委托给空实现扩展(`apps/cmdb/custom_reporting/extensions.py`),实际不执行操作。**社区壳记日志=记空操作**;有意义的是商业版扩展里真正创建任务/凭证之处。补日志应放在商业版扩展,或在确有真实操作的路径上。

### ⑥ 建议跳过：UI偏好 / setup
- `ShowFieldViewSet`(显示字段设置)、`UserPersonalConfigViewSet`(个人配置)、`K8sSetupViewSet`(install_token/command/verify/render)
理由:UI 偏好 / 个人配置 / 安装令牌,审计价值低、噪音大。

### ⑦ 建议跳过：机器 ingest / 实例文件
- `ConfigFileVersionViewSet.receive_result`、`CustomReportingIngestViewSet.create`(token 鉴权,无 `request.user`)
- 实例 `upload_file` / `delete_file`(属实例数据范畴)

## 实施时的关键设计点（留给将来）

1. **机制选择**:①–④ 大多**不是实例变更**,塞进 `ChangeRecord`(`inst_id`/`model_id` 实例导向)并不自然。更合适的是在视图/服务层**直接调 `save_operation_log(...)`**(类似 Alert `apps/alerts/utils/operator_log.py` 的 helper 做法),`app="cmdb"`,带 `target_type/target_id/detail`。这会引入 CMDB 第二条日志路径(ChangeRecord 镜像 + 直接调用),需权衡统一性——或考虑统一封装一个 cmdb 侧 helper。
2. **最该先修**:① 里的 `update_model` / `delete_model` 不记日志,而 `create_model` 记了——create-vs-改/删 的不对称是最清晰的缺口,即便其它先不做,这个值得优先补。
3. **source_ip**:直接调用路径若在请求上下文中,可传真实 IP;否则按既定约定填 `127.0.0.1`(`GenericIPAddressField` 不接受 "internal" 等非法值)。
4. **action_type 映射**:create/update/delete/execute 四类;execute 适用于 run_sync/run_collect/CollectTool.execute 等。

## 决策记录

用户(2026-06-17):本期**先都不做**,仅记录此清单,后续有空再实施。
