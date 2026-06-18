# CMDB/Alert 富日志经 NATS 镜像到平台操作日志 — 设计

- 日期：2026-06-17
- 分支：feature_windyzhao
- 状态：已评审选型，待写实现计划
- **取代**：`docs/superpowers/specs/2026-06-15-cmdb-alert-audit-log-integration-design.md`(装饰器方案，因日志内容过于扁平、丢失 target/before-after 等信息被否决并已回滚)

## 1. 背景与问题

平台「系统管理 → 审计日志 → 操作日志」由 `system_mgmt.OperationLog` 承载，字段扁平:`username / source_ip / app / action_type / summary(纯文本) / domain / created_at`。

CMDB 与 Alert 各自已有**远比它丰富**的日志:
- CMDB `ChangeRecord`(`apps/cmdb/models/change_record.py`):`inst_id`、`model_id`、`type`、`before_data`/`after_data`(JSON 全量前后快照)、`scenario`、`message`、`operator`。
- Alert `OperatorLog`(`apps/alerts/models/operator_log.py`):`operator`、`action`、`target_type`、`target_id`、`operator_object`、`overview`。

被否决的装饰器方案只把这些压成一句模板 `summary`,丢失了 target 身份、前后差异、场景分类。**目标**:让平台操作日志携带与源日志同等的结构化信息。

## 2. 硬约束(需求方指定)

- 推送必须经 **NATS RPC `apps.system_mgmt.nats_api.save_operation_log`**(可扩展其签名,但必须是这个方法)。
- 不使用 Django 信号(见 §4 理由)。

## 3. 选型结论(方案 A:富内容自包含镜像)

源 app 照常写自己的 `ChangeRecord`/`OperatorLog`;在**写入的中央入口**处,经 NATS 把一条**结构化富内容**镜像进 `OperationLog`。平台操作日志成为自包含、可独立查看的统一审计视图;源 app 的读取页与逻辑不变。

候选对比(均用 NATS):A 信号镜像(否决,见 §4)、B 显式调用、**最终=在中央写入 helper 内推送(B 的中央化形态)**。

## 4. 为什么不用信号(关键)

`post_save` 信号**不会**由 `bulk_create` 触发。而两侧都有 bulk 写入:
- CMDB `batch_create_change_record`(`apps/cmdb/utils/change_record.py:26`,`bulk_create`)。
- Alert `common/assignment.py:189`、`common/auto_close.py:260`(`bulk_create`)。

信号方案会**静默漏掉**这些 bulk 日志。而在中央写入 helper 内推送可覆盖单条与 bulk。故弃用信号。

## 5. 触发点(改写中央写入入口,无信号)

### 5.1 CMDB — 已天然中央化(零重构)

经核实,**所有** `ChangeRecord` 创建都在一个文件 `apps/cmdb/utils/change_record.py` 的三个函数内,无任何旁路 `ChangeRecord.objects.create`:
- `create_change_record(inst_id, model_id, label, _type, before_data=None, after_data=None, operator="", message="", ..., scenario=...)` — 单条。
- `batch_create_change_record(label, _type, change_records, operator="", scenario=ORDINARY_ATTRIBUTE_CHANGE)` — bulk。
- `create_change_record_by_asso(label, _type, data, operator="", message="", scenario=RELATION_CHANGE)` — 关联边,bulk。

在这三个函数**写库成功后**追加镜像推送(按 §7 scenario 过滤)。

### 5.2 Alert — 不中央化,需引入 helper + 重构

`OperatorLog` 写入散落 ~15 处(`views/incident.py`×5、`views/assignment_shield.py`×6、`views/strategy.py`×3、`views/incident_update.py`×3、`views/system_setting.py`×2、`service/incident_operator.py`、`service/alter_operator.py`)+ 2 处 `bulk_create`(`common/assignment.py`、`common/auto_close.py`)。

新增 `apps/alerts/utils/operator_log.py`:
```python
def record_operator_log(**log_data):
    """写一条 OperatorLog 并镜像到平台操作日志。替代散落的 OperatorLog.objects.create(**log_data)。"""
    obj = OperatorLog.objects.create(**log_data)
    _mirror_operator_log_to_operation_log([obj])   # 失败安全
    return obj

def record_operator_logs_bulk(items):
    """items: List[OperatorLog 实例 或 log_data dict]。bulk_create + 镜像。"""
    objs = OperatorLog.objects.bulk_create([_as_obj(i) for i in items])
    _mirror_operator_log_to_operation_log(objs)
    return objs
```
把上述 ~15 处单写改调 `record_operator_log(**log_data)`,2 处 bulk 改调 `record_operator_logs_bulk(...)`。

## 6. 传输:扩展 `save_operation_log` 签名

`apps/system_mgmt/nats_api.py::save_operation_log` 与 RPC 包装 `apps/rpc/system_mgmt.py::SystemMgmt.save_operation_log` 同步扩展(新参全部可选,`log_operation` 与现有调用方不受影响):
```python
def save_operation_log(username, source_ip, app, action_type,
                       summary="", domain="domain.com",
                       target_type="", target_id="", detail=None):
```
`detail` 接收 dict,落入 `OperationLog.detail`(JSON)。`nats_api` 侧仍校验 `action_type ∈ {create,update,delete,execute}`。

调用方(两侧 helper)经 `SystemMgmt().save_operation_log(...)` **同步**调用,整体包 `try/except`,**任何异常都不得影响源日志写入**(记 logger.warning 后吞掉)。

## 7. 映射与范围

### 7.1 CMDB(在 change_record helper 内)
- `app = "cmdb"`,`username = operator`,`source_ip` 见 §8,`domain` 见 §8。
- `action_type` 映射(源 `ChangeRecord.type`):`create_entity→create`、`update_entity→update`、`delete_entity→delete`、`create_edge→create`、`delete_edge→delete`、`execute→execute`。
- `target_type = model_object or model_id`,`target_id = str(inst_id)`。
- `summary = message`(空则按 `type + model_object` 兜底拼一句)。
- `detail = {"before_data":..., "after_data":..., "scenario":..., "label":..., "model_object":..., "source":"change_record"}`。
- **scenario 过滤(范围)**:仅当 `scenario ∈ {model_management_change, collect_automation_change, custom_reporting_change, relation_change}` 才推送;`ordinary_attribute_change`、`device_lifecycle`(高频实例数据变更)**不推送**(由 change_record 自身承载,且控量、使同步推送可行)。
  - 注:`batch_create_change_record` 默认 `scenario=ORDINARY_ATTRIBUTE_CHANGE`,故 `instance.py` 的高频实例 bulk 写自动被过滤掉。

### 7.2 Alert(在 operator_log helper 内)
- `app = "alarm"`(canonical App.name;**非** `"alerts"`),`username = operator`。
- `action_type` 映射(源 `OperatorLog.action`):`add→create`、`modify→update`、`delete→delete`、`execute→execute`。
- `target_type = OperatorLog.target_type`(event/alert/incident/system),`target_id = OperatorLog.target_id`。
- `summary = overview`。
- `detail = {"operator_object":..., "target_type":..., "source":"operator_log"}`。
- **范围**:全量镜像(Alert 日志是操作语义、量小,无需过滤)。

## 8. Schema 扩展(`OperationLog`)

`apps/system_mgmt/models/operation_log.py` 新增(additive migration,全部可空/有默认):
- `target_type = CharField(max_length=50, blank=True, default="", db_index=True)`
- `target_id = CharField(max_length=100, blank=True, default="", db_index=True)`
- `detail = JSONField(default=dict, blank=True)`

`source_ip`:镜像行的源 IP **尽力获取**——helper 接收可选 `source_ip`,有 request 上下文的调用方可传真实 IP;后台/bulk 无 request 时缺省 `"internal"`。不引入 thread-local 中间件(本期范围外)。
`domain`:源行无 domain,缺省 `"domain.com"`(后续可由 operator 反查,本期不做)。

序列化器 `OperationLogSerializer`(`fields="__all__"`)自动暴露新字段。

## 9. 前端

`web/src/app/system-manager/components/security/operationLogs.tsx`:表格列保持不变;新增「详情」入口(抽屉/弹窗)渲染 `detail`:
- target(`target_type` + `target_id`);
- CMDB:`before_data`/`after_data` 前后对比(可复用 cmdb changeRecords 的 diff 呈现思路);
- `scenario` / `operator_object` 标签。
`detail` 为空的历史/其它 app 记录,详情入口不展示或显示「无」。

## 10. 错误处理

- 镜像推送整体 `try/except`,失败仅 `logger.warning`,**绝不**冒泡影响 `ChangeRecord`/`OperatorLog` 的写入或业务响应。
- `nats_api.save_operation_log` 已对非法 `action_type` 返回 `{result:False}`;helper 侧映射保证只传合法值。

## 11. 测试策略(TDD,遵循 server/docs/testing-guide.md)

- **RPC 扩展**(`_service`):`save_operation_log` 传 `target_type/target_id/detail` → 断言 `OperationLog` 行落库且 `detail` 完整;旧签名(不传新参)仍工作。
- **CMDB helper**(`_service`,mock `SystemMgmt.save_operation_log`):
  - 管理类 scenario → 推送一次,payload 的 app/action_type/target/detail 正确;
  - `ordinary_attribute_change`/`device_lifecycle` → **不推送**;
  - `batch_create_change_record`/`create_change_record_by_asso` 的 bulk 路径 → 每条按过滤后推送;
  - 推送抛错 → `ChangeRecord` 仍成功写入(失败安全)。
- **Alert helper**(`_service`,mock RPC):`record_operator_log` 写 `OperatorLog` 且镜像一次(app="alarm"、action 映射、target 透传);`record_operator_logs_bulk` 覆盖 bulk;失败安全。
- **重构回归**:Alert 既有针对这些视图的测试仍通过(改调 helper 后 `OperatorLog` 行为不变)。
- **端到端**:跑通一次管理类 change_record 与一次 operator_log,断言出现对应 `OperationLog` 镜像行(含 target+detail)。

## 12. 已知限制 / 取舍

- **数据重复**:管理类操作在源表与 `OperationLog` 各存一份;已用 scenario 过滤把高频实例变更挡在外面,重复量可控。
- **同步推送延迟**:每条镜像一次 NATS 同步往返;因高频 scenario 已过滤,管理类/Alert 操作量小,可接受。若未来量上来可改异步(Celery,沿用错误日志范式)。
- **source_ip 不全**:后台/bulk 镜像行为 `internal`;如需全量真实 IP,后续加 thread-local 中间件。
- **历史数据不回填**:仅镜像新写入的日志。

## 13. 实现顺序建议

1. Schema:`OperationLog` 加 `target_type/target_id/detail` + migration(TDD)。
2. RPC:扩展 `save_operation_log` 签名 + `SystemMgmt` 包装(TDD,旧签名兼容)。
3. CMDB:在 `change_record.py` 三函数内加映射+scenario 过滤+失败安全推送(TDD)。
4. Alert:新增 `operator_log.py` helper(单条/bulk)+ 映射推送(TDD);重构 ~15 处 + 2 处 bulk 改调 helper(回归)。
5. 前端:`detail` 详情抽屉。
6. 端到端回归。
