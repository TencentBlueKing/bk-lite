# 监控实例物理删除设计

Status: accepted

## 1. 决定

用户删除监控实例时执行物理删除。停止产生新的 `is_deleted=True` 墓碑，不引入退役状态、退役操作表、Outbox 或专用 worker。

删除流程收口到一个深模块：

```python
MonitorInstanceRemovalService.remove(instance_ids)
```

模块通过数据库行锁、NodeMgmt 幂等删除和本地事务保证失败后可安全重试。历史软删除墓碑在创建相同 ID 的实例时按需回收；剩余墓碑只在最终移除 `is_deleted` 字段前批量清理。

## 2. 为什么物理删除

当前软删除不构成真正的恢复能力：

- 没有恢复入口、删除人、删除时间或删除原因；
- 删除时已经清理 NodeMgmt 配置、本地 `CollectConfig`、组织规则和策略来源；
- Flow 和普通接入中的恢复分支会隐式带回旧元数据，不符合用户对“删除”的理解；
- `MonitorInstance.id` 是全局主键，墓碑继续占用 ID，直接导致删除后重新创建出现 `monitor_monitorinstance_pkey` 冲突。

证据：

- `server/apps/monitor/models/monitor_object.py:52-59`
- `server/apps/monitor/views/monitor_instance.py:343-384`
- `server/apps/monitor/services/node_mgmt.py:499-505,596-603`
- `server/apps/monitor/services/flow_onboarding.py:22-105,218-256`

物理删除不会级联删除告警历史。`MonitorAlert`、`MonitorEvent` 和快照保存字符串实例 ID；真正指向 `MonitorInstance` 的强外键只有 `CollectConfig` 和 `MonitorInstanceOrganization`，两者均为 `CASCADE`。

## 3. 范围

本变更包括：

- 用户删除监控实例时物理删除；
- 删除流程的权限、锁、NodeMgmt 配置清理、本地引用清理和 Flow 刷新；
- 创建流程的全局 ID 查重、请求内去重和业务错误转换；
- 创建时按需回收历史软删除墓碑；
- 最终移除 `is_deleted` 的兼容路径。

本变更不包括：

- 删除 VictoriaMetrics 历史指标；
- 删除告警、事件和快照历史；
- 删除后恢复；
- 新增实例停用能力；
- 新增自动发现永久排除能力；
- 引入异步删除状态机或分布式事务。

## 4. 删除接口

```python
@dataclass(frozen=True)
class RemovalResult:
    removed_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    cleaned_policy_ids: tuple[int, ...]
    disabled_policy_ids: tuple[int, ...]


class MonitorInstanceRemovalService:
    @classmethod
    def remove(
        cls,
        instance_ids: Iterable[str],
    ) -> RemovalResult:
        ...
```

接口规则：

- 输入 ID 规范化、去重，批量数量设置显式上限；
- API 层必须在调用删除模块前校验所有现存目标的 `Operate` 权限，否则整批不执行；
- 缺失 ID 按幂等成功处理，不泄露其他组织信息；
- 原始 RPC、`IntegrityError` 和数据库约束名称不得返回 UI；
- 删除成功后 `MonitorInstance` 主表不再存在对应记录。

## 5. 删除执行顺序

删除模块执行以下步骤：

1. 规范化和去重实例 ID。
2. 按 ID 排序，以 `select_for_update()` 锁定实例。
3. 快照 child/base 配置 ID 和 Flow 云区域。
4. 调用 NodeMgmt 幂等删除 child/base 配置。
5. 在同一数据库事务内：
   - 从按实例选择的策略来源中移除实例，来源为空时禁用策略；
   - 删除 `MonitorObjectOrganizationRule`；
   - 物理删除 `MonitorInstance`。
6. 数据库提交后刷新受影响的 Flow 云区域。

`CollectConfig` 和 `MonitorInstanceOrganization` 依赖数据库级联删除。告警、事件和快照历史保留。

NodeMgmt 当前使用 `filter(id__in=...).delete()`，重复调用没有副作用：`server/apps/node_mgmt/nats/node.py:458-464`。

## 6. 失败处理

本设计不宣称数据库事务可以覆盖 NodeMgmt RPC，而是保证每种失败都可通过相同删除请求安全收敛：

- NodeMgmt 全部失败：数据库不删除，返回操作失败；重试。
- child 删除成功、base 删除失败：数据库不删除；重试时 child 删除为空操作，继续删除 base。
- NodeMgmt 成功、数据库事务失败：数据库实例仍存在且继续占用 ID；重试时远端删除为空操作，再完成本地删除。
- 进程在远端清理后崩溃：效果同上，用户再次删除即可完成。
- Flow 刷新失败：不回滚已经完成的删除；记录错误并允许后续刷新或对账修复。

为了避免长事务影响，删除批次必须有上限。该方案接受失败窗口内“实例仍显示但远端配置已不存在”的短暂不一致，不接受“数据库已删除但旧远端配置仍运行”或“旧配置未清理就释放实例 ID”。

## 7. 创建与历史墓碑回收

创建实例前必须按全局主键查询，不能附加 `monitor_object_id`：

```python
with transaction.atomic():
    existing = list(
        MonitorInstance.objects
        .select_for_update()
        .filter(id__in=instance_ids)
    )
```

处理规则：

- ID 不存在：创建新实例；
- ID 属于当前对象且有效：按现有配置规则复用；
- ID 属于其他对象且有效：返回明确的实例身份冲突；
- ID 对应 `is_deleted=True` 历史墓碑：先安全回收墓碑，再创建新实例；
- 同一请求生成重复 ID：写数据库前返回业务错误；
- 并发创建最终触发唯一约束：捕获 `IntegrityError` 并转换为业务冲突。

不存在的行无法被 `select_for_update()` 锁定，因此首次并发创建仍以数据库唯一约束为最终仲裁；查询、墓碑回收和创建必须处在同一外层事务中。

历史墓碑已经代表用户删除完成，不再是可操作业务资源。跨对象墓碑回收属于系统内部清理：不向创建者返回墓碑所属对象、组织或其他元数据；若清理失败，仅返回通用清理失败信息。

历史墓碑回收复用删除模块的内部清理步骤：

1. 锁定墓碑；
2. 幂等清理可能残留的 NodeMgmt 配置；
3. 清理策略当前态和规则；
4. 物理删除墓碑；
5. 在同一数据库事务中创建新实例。

新实例不得继承旧墓碑的对象、组织、Flow 协议或配置。

## 8. 自动发现

第一阶段不改变自动发现任务的既有行为。持续上报的自动实例被用户删除后仍可能再次被发现；若产品需要永久隐藏，应另行设计发现排除规则，不使用软删除墓碑表达。

## 9. 表结构与部署

第一阶段不修改表结构，不要求部署初始化：

- 新删除直接物理删除；
- `is_deleted` 暂时保留，只用于识别历史墓碑；
- 创建时按需回收命中的历史墓碑。

因此当前 Bug 的修复不依赖部署后先运行全量清理命令。

在最终删除 `is_deleted` 字段前，需要扫描并清理没有被按需回收的剩余墓碑。执行命令自身必须重复所有安全检查；`--dry-run` 是生产预览步骤，不是程序正确性的前提。

```bash
uv run python manage.py purge_deleted_monitor_instances --dry-run
uv run python manage.py purge_deleted_monitor_instances --execute --batch-size 500
```

墓碑清零并观察一个发布周期后，再通过独立 migration 删除 `is_deleted` 字段和索引，同时移除所有恢复分支和 `is_deleted=False` 查询。

## 10. 验证标准

- 用户删除后数据库中不存在实例记录；
- NodeMgmt 删除失败时数据库实例保留；
- NodeMgmt 部分成功后重复删除可完成；
- 数据库事务失败后重复删除可完成；
- CollectConfig 和组织关系级联删除；
- 策略来源和组织规则被正确处理；
- 告警、事件和快照历史保留；
- 删除后相同 ID 可重新创建；
- 其他对象的历史墓碑可按需回收后创建；
- 其他对象的有效实例返回业务冲突；
- 请求内重复 ID 和并发唯一键竞争不暴露数据库错误；
- 删除数量超过批量上限时在调用 NodeMgmt 前拒绝整批请求；
- Flow 只在数据库提交后刷新；
- 自动发现既有同步行为不受影响。
