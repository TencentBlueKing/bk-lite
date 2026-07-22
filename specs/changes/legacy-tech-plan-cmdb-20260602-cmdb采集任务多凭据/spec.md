# CMDB 采集任务多凭据 - Tech Plan

Status: cancelled

> Migrated from `spec/tech_plan/CMDB/20260602.CMDB采集任务多凭据.md` as historical change evidence.

日期：2026-06-02

## 技术目标与非目标

### 技术目标

- 在不新增采集任务主表、不改插件契约的前提下，将 `CollectModels.credential` 从“单凭据对象”升级为“有序凭据池”。
- 在 CMDB 平台侧新增“目标识别 → 凭据选择 → 命中状态回写”调度层，覆盖首期范围：`JOB`、`SNMP`、`PROTOCOL` 三类采集链路。
- 命中状态独立存储，不写入 `collect_data`、`collect_digest`、`format_data`，不跨任务共享。
- 前端仅改造采集任务创建/编辑页，支持最多 3 个凭据的卡片式录入、编辑、删除、排序。
- 发布后老任务继续按单凭据兼容运行；回滚时可将多凭据任务压平为首个凭据，保证旧代码可读。

### 非目标

- 不引入“凭据分组（凭据 + 目标范围）”。
- 不做跨任务命中共享。
- 不新增命中状态展示页、任务级/对象级重置入口。
- 不改 Stargazer / 插件侧“单凭据 + 一批目标”的执行契约。
- 不将 `CLOUD`、`K8S`、`VM` 纳入首期范围。
- 不将冷却策略配置化。

## 影响范围与改动点

- **Server / CMDB**
  - 任务模型读写兼容。
  - 多凭据派发服务。
  - 命中状态模型、迁移、回写规则。
  - `sync_collect_task` 执行链路接入。
    - NATS 接收 Stargazer 推送结果并落库。
  - 回滚辅助命令。
- **Agents / Stargazer**
    - 多凭据结果事件写入 Redis 事件流。
    - 15 分钟周期推送任务将批量结果发往统一 CMDB subject。
    - 不再暴露 CMDB 主动拉取结果的 handler。
- **Web / CMDB**
  - 创建/编辑页凭据池表单。
  - 任务详情回填逻辑。
  - 类型定义与请求入参格式化。
- **外部边界**
  - 复用现有 `CollectModelViewSet` 创建/更新/详情接口，不新增公开 API。
  - 对 Stargazer 仍下发单凭据单批次任务，不改协议。

### 当前未提交实现摘要

- Server / CMDB：`collect_model.py`、`collect_service.py`、`collect_dispatch_service.py`、`collect_serializer.py`、`node_configs/*`、`nats/nats.py`、`tasks/celery_tasks.py` 已接入多凭据保存、派发、命中状态回写与 NATS 接收日志。
- Agents / Stargazer：`api/collect.py`、`tasks/handlers/plugin_handler.py`、`tasks/utils/nats_helper.py`、`service/collect_credential_result_push_service.py`、`service/collect_credential_result_push_task.py`、`server.py` 已形成“结果写 Redis 事件流 -> 15 分钟批量推送到 CMDB”的闭环。
- Web / CMDB：任务创建/编辑页相关表单、类型与样式文件已改为凭据池输入模型，支持多凭据录入与回填。
- 交互收敛：CMDB 侧旧的主动拉取任务 `sync_collect_credential_results_task` 保留函数名但已改为 no-op skipped；Stargazer 侧旧的 `list_collect_credential_results` pull handler 已移除，运行主链路统一为 push。

---

## 1) 文件与目录结构 (File Tree)

```text
server/
└─ apps/cmdb/
   ├─ models/
   │  ├─ collect_model.py                              (M) credential 字段读写兼容为凭据池
   │  ├─ collect_task_credential_hit.py                (A) 任务内对象-凭据命中状态模型
   │  └─ __init__.py                                   (M) 导出新模型
   ├─ migrations/
   │  └─ 00xx_collect_task_credential_hit.py           (A) 新表迁移
   ├─ serializers/
   │  └─ collect_serializer.py                         (M) create/update/detail 兼容凭据池结构
   ├─ services/
   │  ├─ collect_service.py                            (M) 创建/更新任务时处理凭据池 diff 与失效
   │  ├─ collect_credential_pool_service.py            (A) 凭据池 normalize / diff / rollback flatten
   │  ├─ collect_target_service.py                     (A) 目标归一化与 object_key 构建
   │  ├─ collect_hit_state_service.py                  (A) 命中状态查询、回写、冷却计算
   │  └─ collect_dispatch_service.py                   (A) 平台侧多凭据派发与结果聚合
    ├─ nats/
    │  └─ nats.py                                       (M) 接收 Stargazer 推送的单条/批量凭据结果并记录摘要日志
   ├─ collection/
   │  └─ collect_tasks/
   │     ├─ job_collect.py                             (M) JOB 链路接入多凭据派发
   │     ├─ protocol_collect.py                        (M) PROTOCOL / SNMP 链路接入多凭据派发
   │     └─ base.py                                    (M) 为多目标结果聚合补充共用辅助方法
   ├─ tasks/
    │  └─ celery_tasks.py                               (M) sync_collect_task 接入 dispatch service；legacy 凭据拉取任务改为 skipped no-op
   ├─ node_configs/
   │  └─ base.py                                       (M) 推送节点配置时默认读取首个凭据，保持旧链路兼容
   ├─ management/
   │  └─ commands/
   │     └─ flatten_collect_credential_pool.py         (A) 回滚前将多凭据任务压平为首个凭据
   └─ tests/
      ├─ test_collect_model_credential_pool.py         (A) 模型与序列化兼容测试
      ├─ test_collect_hit_state_service.py             (A) 命中状态、冷却、失效规则测试
      ├─ test_collect_dispatch_service.py              (A) 派发顺序与结果回写测试
        ├─ test_collect_credential_event_nats.py         (M) 验证接收推送、日志摘要、legacy pull task skipped
      └─ test_flatten_collect_credential_pool_cmd.py   (A) 回滚命令测试

agents/stargazer/
└─
    ├─ server.py                                        (M) 启动时显式注册凭据结果推送循环
    ├─ service/
    │  ├─ collect_credential_result_push_service.py     (A) 批量读取 Redis 事件流、推进推送游标、发布到 CMDB
    │  ├─ collect_credential_result_push_task.py        (A) 15 分钟一次的推送循环与可观测日志
    │  └─ nats_server.py                                (M) 仅保留业务 handler，不再承载周期任务与 pull handler
    └─ tests/
        └─ test_collect_credential_push.py               (A) 验证推送循环注册、push_once 发布、日志输出

web/
└─ src/app/cmdb/
   ├─ api/
   │  └─ collect.ts                                    (M) 复用现有接口，补充凭据池类型入参
   ├─ types/
   │  └─ autoDiscovery.ts                              (M) 新增 CredentialPoolItem / form types
   └─ (pages)/assetManage/autoDiscovery/collection/profess/
      ├─ hooks/
      │  ├─ formatTaskValues.ts                        (M) 表单值转凭据池 payload
      │  └─ useTaskForm.ts                             (M) 编辑态/复制态凭据池回填
      ├─ components/
      │  ├─ credentialPoolEditor.tsx                   (A) 通用凭据池卡片编辑器
      │  ├─ hostTask.tsx                               (M) HOST / MIDDLEWARE 任务接入凭据池
      │  ├─ sqlTask.tsx                                (M) DB / PROTOCOL 任务接入凭据池
      │  ├─ configFileTask.tsx                         (M) CONFIG_FILE 任务接入凭据池
      │  └─ snmpTask.tsx                               (M) SNMP 任务接入凭据池
      └─ constants/
         └─ professCollection.ts                       (M) 最大凭据数、提示文案常量
```

---

## 2) 核心数据结构 / Schema 定义

### 2.1 凭据池 JSON 口径

`CollectModels.credential` 持久化统一为有序数组；老数据 `dict` 在读路径 normalize 成长度为 1 的数组。

```python
# persisted JSON in CollectModels.credential
[
    {
        "credential_id": "cred_001",
        "username": "admin",
        "password": "enc:xxxxx",
        "port": 22,
    },
    {
        "credential_id": "cred_002",
        "username": "ops",
        "password": "enc:yyyyy",
        "port": 22,
    },
]
```

约束：

- 首期仅允许 `1..3` 个凭据。
- 同一任务内所有凭据字段集合必须完全一致。
- `credential_id` 为服务端生成的稳定标识；仅新增凭据时新建，不随排序变化。

### 2.2 运行时核心 Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

HitStatus = Literal["untested", "success", "known_failed"]
CollectExecutor = Literal["job", "snmp", "protocol"]


@dataclass(frozen=True)
class CredentialPoolItem:
    """任务内单个凭据配置。"""
    credential_id: str
    fields: dict[str, Any]
    order: int


@dataclass(frozen=True)
class CanonicalCollectTarget:
    """任务内可连接目标的标准表示，用于命中判断与 object_key 生成。"""
    task_id: int
    task_type: str
    executor: CollectExecutor
    model_id: str
    host: str
    port: int | None = None
    endpoint: str | None = None
    cloud_region_id: str | None = None
    instance_id: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class CredentialHitState:
    """对象-凭据的任务内运行态。"""
    task_id: int
    object_key: str
    credential_id: str
    status: HitStatus
    consecutive_failures: int
    cooldown_level: int
    next_retry_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str = ""
    object_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchAttemptResult:
    """单次凭据尝试后的归一化结果。"""
    object_key: str
    credential_id: str
    success: bool
    failure_kind: Literal["credential", "task", "unknown"]
    error_message: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
```

### 2.3 新增 Django 持久化模型

```python
# server/apps/cmdb/models/collect_task_credential_hit.py

class CollectTaskCredentialHit(models.Model):
    """
    任务内对象-凭据命中状态。
    只服务于派发决策，不参与 collect_data / collect_digest / format_data。
    """
    task = models.ForeignKey("cmdb.CollectModels", on_delete=models.CASCADE, related_name="credential_hits")
    object_key = models.CharField(max_length=255)
    credential_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=[("untested", "未探测"), ("success", "成功"), ("known_failed", "已知失败")])
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    cooldown_level = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    object_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("task", "object_key", "credential_id")
        indexes = [
            models.Index(fields=["task", "object_key"]),
            models.Index(fields=["task", "status", "next_retry_at"]),
        ]
```

### 2.4 前端表单类型

```typescript
export interface CredentialPoolItem {
  credential_id?: string;
  username?: string;
  user?: string;
  password?: string;
  port?: number;
  community?: string;
  authkey?: string;
  privkey?: string;
  version?: string;
  level?: string;
  integrity?: string;
  privacy?: string;
  [key: string]: unknown;
}

export interface CredentialPoolFormValue {
  credentials: CredentialPoolItem[];
}
```

---

## 3) 核心函数 / 接口签名 (API & Signatures)

### 3.1 凭据池兼容与 diff

```python
# server/apps/cmdb/services/collect_credential_pool_service.py

from typing import Any


class CollectCredentialPoolService:
    """负责凭据池 normalize、同构校验、diff 和回滚压平。"""

    @staticmethod
    def normalize_pool(raw_credential: Any) -> list[CredentialPoolItem]:
        """将 dict | list[dict] 统一为有序 CredentialPoolItem 列表。"""

    @staticmethod
    def validate_pool_shape(pool: list[CredentialPoolItem]) -> None:
        """校验 1..3 个凭据、字段结构一致、首期支持范围内字段合法。"""

    @staticmethod
    def encrypt_pool(model_id: str, driver_type: str, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按模型密码字段规则加密凭据池中的敏感字段。"""

    @staticmethod
    def decrypt_pool(model_id: str, driver_type: str, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按模型密码字段规则解密凭据池中的敏感字段。"""

    @staticmethod
    def diff_pool(
        old_pool: list[CredentialPoolItem],
        new_pool: list[CredentialPoolItem],
    ) -> tuple[list[str], list[str], list[str]]:
        """
        返回 (added_ids, removed_ids, edited_ids)。
        排序变化不算编辑。
        """

    @staticmethod
    def flatten_pool_to_primary(raw_credential: Any) -> dict[str, Any]:
        """回滚到旧代码前，将凭据池压平为首个凭据对象。"""
```

### 3.2 目标归一化与 object_key 计算

```python
# server/apps/cmdb/services/collect_target_service.py


class CollectTargetService:
    """负责把任务快照转为任务内标准目标集合。"""

    @staticmethod
    def build_targets(task: CollectModels) -> list[CanonicalCollectTarget]:
        """从 task.instances / task.ip_range 构建标准目标列表。"""

    @staticmethod
    def build_object_key(target: CanonicalCollectTarget) -> str:
        """
        生成稳定 object_key：
        - JOB(HOST/MIDDLEWARE): task_id + host + cloud_region_id
        - JOB(DB/CONFIG_FILE): task_id + host + cloud_region_id + endpoint_or_port
        - SNMP: task_id + host + snmp_port + cloud_region_id
        - PROTOCOL: task_id + host + port_or_endpoint
        """

    @staticmethod
    def build_target_snapshot(target: CanonicalCollectTarget) -> dict[str, Any]:
        """返回用于 object_snapshot 存储和日志输出的最小快照。"""
```

### 3.3 命中状态服务

```python
# server/apps/cmdb/services/collect_hit_state_service.py


class CollectHitStateService:
    """负责查询、冷却判断、成功/失败回写。"""

    @staticmethod
    def list_states(task_id: int) -> dict[tuple[str, str], CredentialHitState]:
        """按 (object_key, credential_id) 返回命中状态映射。"""

    @staticmethod
    def cooldown_hours_for(level: int) -> int:
        """返回 1h -> 4h -> 24h 封顶的冷却时长。"""

    @staticmethod
    def is_retryable(state: CredentialHitState, now: datetime) -> bool:
        """判断 known_failed 是否已过冷却期，可重新视为 untested。"""

    @staticmethod
    def mark_success(task_id: int, object_key: str, credential_id: str, snapshot: dict[str, Any], now: datetime) -> None:
        """写入成功状态，并清理同对象其他 credential_id 的 success。"""

    @staticmethod
    def mark_failure(
        task_id: int,
        object_key: str,
        credential_id: str,
        snapshot: dict[str, Any],
        failure_kind: str,
        error_message: str,
        now: datetime,
    ) -> None:
        """仅凭据失败推进 consecutive_failures / cooldown_level。"""

    @staticmethod
    def clear_by_credential_ids(task_id: int, credential_ids: list[str]) -> int:
        """清理被编辑/删除凭据关联的命中状态。"""
```

### 3.4 多凭据派发服务

```python
# server/apps/cmdb/services/collect_dispatch_service.py


class CollectDispatchService:
    """负责目标分组、凭据选择、批量调用现有采集链路、聚合结果。"""

    @staticmethod
    def execute_task(task: CollectModels) -> tuple[dict[str, Any], dict[str, Any]]:
        """返回 (collect_data, format_data)，供 sync_collect_task 继续写摘要。"""

    @staticmethod
    def plan_dispatch(
        task: CollectModels,
        targets: list[CanonicalCollectTarget],
        pool: list[CredentialPoolItem],
        states: dict[tuple[str, str], CredentialHitState],
    ) -> dict[str, list[CanonicalCollectTarget]]:
        """按 credential_id 聚合本轮需尝试的目标列表。"""

    @staticmethod
    def run_job_batch(task: CollectModels, credential: CredentialPoolItem, targets: list[CanonicalCollectTarget]) -> list[DispatchAttemptResult]:
        """调用现有 JOB 采集链路执行单凭据批次。"""

    @staticmethod
    def run_protocol_batch(task: CollectModels, credential: CredentialPoolItem, targets: list[CanonicalCollectTarget]) -> list[DispatchAttemptResult]:
        """调用现有 SNMP / PROTOCOL 采集链路执行单凭据批次。"""

    @staticmethod
    def merge_attempt_results(task: CollectModels, attempts: list[DispatchAttemptResult]) -> tuple[dict[str, Any], dict[str, Any]]:
        """把多轮多凭据结果合并为现有 sync_collect_task 可消费的统一输出。"""
```

### 3.5 Stargazer 推送结果任务

```python
# agents/stargazer/service/collect_credential_result_push_service.py

class CollectCredentialResultPushService:
    @staticmethod
    async def list_results(since: str = "", limit: int = 500) -> dict:
        """从 Redis 事件流读取批量结果，返回 {results, next_since}。"""

    @staticmethod
    async def push_once() -> dict:
        """按本地 push_cursor 读取结果并发布到 `bklite.receive_collect_credential_result`。"""
```

```python
# agents/stargazer/service/collect_credential_result_push_task.py

async def push_collect_credential_results_once() -> dict:
    """执行单次推送并输出无数据/成功摘要日志。"""

def register_collect_credential_result_push_loop(app) -> None:
    """在 Sanic 生命周期中注册 15 分钟周期推送循环。"""
```

### 3.6 CMDB NATS 接收入口

```python
# server/apps/cmdb/nats/nats.py

@nats_client.register
def receive_collect_credential_result(data: dict):
    """接收 Stargazer 推送的单条或批量结果，记录摘要日志后调用 process_batch 落库。"""
```

### 3.5 任务创建 / 更新 / 回滚命令

```python
# server/apps/cmdb/services/collect_service.py

class CollectModelService:
    @classmethod
    def create(cls, request, view_self) -> int:
        """创建任务；保存前 normalize / encrypt 凭据池。"""

    @classmethod
    def update(cls, request, view_self) -> int:
        """更新任务；识别 added / removed / edited credential_id 并清理命中状态。"""
```

```python
# server/apps/cmdb/management/commands/flatten_collect_credential_pool.py

class Command(BaseCommand):
    help = "Collapse multi-credential collect tasks to the first credential for rollback."

    def add_arguments(self, parser) -> None:
        """支持 --task-id、--all、--dry-run。"""

    def handle(self, *args, **options) -> None:
        """将多凭据任务压平为首个凭据对象，并输出受影响任务数。"""
```

### 3.6 前端接口与组件

```typescript
// web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx

export interface CredentialPoolEditorProps {
  value?: CredentialPoolItem[];
  maxCount?: number;
  credentialShape: "ssh" | "sql" | "snmp" | "config_file";
  onChange?: (value: CredentialPoolItem[]) => void;
}

export default function CredentialPoolEditor(props: CredentialPoolEditorProps): JSX.Element;
```

```typescript
// web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/hooks/formatTaskValues.ts

export function buildCredentialPool(
  rawItems: CredentialPoolItem[],
  normalizeItem: (item: CredentialPoolItem, index: number) => CredentialPoolItem
): CredentialPoolItem[];
```

---

## 4) 核心逻辑伪代码 (Step-by-Step Logic)

### 4.1 保存任务时的凭据池兼容与失效处理

1. 接收表单 `credential` 字段。
2. `normalize_pool(raw_credential)`：
   - 如果是 `dict`，包装成单元素列表。
   - 如果是 `list`，按现有顺序保留。
   - 如果为空、超过 3 个、字段结构不一致，直接报错。
3. 对新凭据补 `credential_id`，保留旧 `credential_id`。
4. `validate_pool_shape(pool)` 校验首期范围字段。
5. `encrypt_pool(...)` 加密密码类字段。
6. `diff_pool(old_pool, new_pool)` 得到 `added / removed / edited`。
7. 保存任务。
8. 对 `removed + edited` 的 `credential_id` 调 `clear_by_credential_ids(task_id, ids)`。
9. 仅排序变化时，不清理命中状态。

### 4.2 派发阶段的多凭据选择

1. `sync_collect_task(instance_id)` 读取任务。
2. `normalize_pool(task.credential)` 得到有序凭据池。
3. `build_targets(task)` 生成本轮目标集合。
4. `list_states(task.id)` 读取现有命中状态。
5. 对每个 target：
   - 计算 `object_key`。
   - 先找该对象的 `success` 记录，若存在则只尝试该凭据。
   - 否则从凭据池顺序遍历：
     - `known_failed` 且未过 `next_retry_at`：跳过。
     - `known_failed` 且已过冷却：视作 `untested` 重新参与。
     - 命中第一个可尝试凭据后，加入对应 `credential_id` 批次。
6. 形成 `credential_id -> targets[]` 的批次计划。
7. 逐批次调用现有 JOB / SNMP / PROTOCOL 链路，保证每次下发仍是“单凭据 + 一批目标”。
8. 每个对象一旦成功，本轮终止该对象后续尝试。

### 4.3 结果回写与渐进冷却

1. 对每个 `DispatchAttemptResult`：
   - `success = true`：
     - `mark_success(...)`
     - 将该对象其他 `success` 记录撤销为 `untested`
     - `consecutive_failures = 0`
     - `cooldown_level = 0`
   - `success = false and failure_kind == "credential"`：
     - `consecutive_failures += 1`
     - 若 `< 2`：保持 `untested`
     - 若 `>= 2`：
       - `cooldown_level += 1`
       - `status = known_failed`
       - `next_retry_at = now + cooldown_hours_for(cooldown_level)`
   - `failure_kind in {"task", "unknown"}`：
     - 不修改对象级连续失败次数
     - 只记日志，不污染命中状态
2. 将全部 attempt 合并回现有 `collect_data / format_data` 输出。
3. 继续沿用 `sync_collect_task` 现有摘要统计逻辑。

### 4.4 Stargazer -> CMDB 推送链路

1. Stargazer 执行多凭据任务后，将执行结果事件写入本地 Redis zset 事件流。
2. `register_collect_credential_result_push_loop(app)` 在 Stargazer 启动时注册周期任务。
3. 周期任务默认每 900 秒执行一次 `push_collect_credential_results_once()`。
4. `push_once()` 读取本地 `collect:credential:push_cursor` 之后的新事件，聚合为：
    - `events`
    - `next_since`
5. Stargazer 将批量 payload 发布到统一的 `bklite.receive_collect_credential_result` subject。
6. CMDB 的 `receive_collect_credential_result()` 记录“收到批量/单条结果”摘要日志后，调用 `CollectCredentialResultService.process_batch(...)` 入库。
7. CMDB 不再按 Stargazer 实例 ID 主动拉取；旧的 `sync_collect_credential_results_task()` 仅保留 no-op skipped 返回，防止误用。

### 4.5 回滚步骤

1. 发布回滚前执行：
   - `cd server && uv run python manage.py flatten_collect_credential_pool --all`
2. 将所有多凭据任务压平为首个凭据对象。
3. 保留 `collect_task_credential_hit` 表数据不删表，仅让旧代码不再读取到数组结构。
4. 回滚应用代码到旧版本。

---

## 5) 第三方依赖与环境要求 (Dependencies)

**无新增依赖。**

沿用现有：

- Python 3.12
- Django 4.2
- `uv` 管理 Python 依赖
- `pnpm` 管理 Web 依赖

---

## 6) 注释与关键日志要求

### 注释要求

- `collect_credential_pool_service.py`、`collect_target_service.py`、`collect_hit_state_service.py`、`collect_dispatch_service.py` 中所有非简单函数必须补充 docstring，明确：
  - 函数职责
  - 输入输出
  - 是否修改命中状态
  - 是否允许抛异常
- `collect_model.py` 中与凭据池兼容相关的方法需要行内注释，说明“为什么仍兼容 dict”。
- `flatten_collect_credential_pool.py` 需要在命令类与 `handle()` 上标明用途：**仅服务于回滚，不参与日常业务逻辑**。

### 关键日志要求

必须使用现有 `cmdb_logger`，至少补以下日志：

```text
[CollectCredentialPool] normalize pool task_id=<id> size=<n>
[CollectCredentialPool] clear hit states task_id=<id> credential_ids=<ids> reason=<edited|removed>
[CollectTarget] build object key task_id=<id> object_key=<key> model_id=<model>
[CollectDispatch] start dispatch task_id=<id> executor=<job|snmp|protocol> targets=<n> credentials=<n>
[CollectDispatch] batch start task_id=<id> credential_id=<id> batch_size=<n>
[CollectDispatch] attempt result task_id=<id> object_key=<key> credential_id=<id> success=<bool> failure_kind=<kind>
[CollectHitState] mark success task_id=<id> object_key=<key> credential_id=<id>
[CollectHitState] mark failure task_id=<id> object_key=<key> credential_id=<id> consecutive_failures=<n> cooldown_level=<n> next_retry_at=<ts>
[CollectCredentialResultNATS] received batch count=<n> next_since=<ts>
[CollectCredentialResultNATS] processed batch processed=<n> failed=<n> next_since=<ts>
[CollectRollback] flatten pool task_id=<id> dry_run=<bool> changed=<bool>
```

Stargazer 侧推送任务至少补以下日志：

```text
[CollectCredentialPush] loop started interval_seconds=<n>
[CollectCredentialPush] waiting next cycle interval_seconds=<n>
[CollectCredentialPush] no results next_since=<ts>
[CollectCredentialPush] pushed count=<n> next_since=<ts>
[CollectCredentialPush] loop stopped
```

禁止记录明文密码、community、authkey、privkey。

---

## 7) 测试方案

### 后端测试

- `test_collect_model_credential_pool.py`
  - dict → list 兼容读取
  - 1..3 个凭据限制
  - 字段结构不一致拒绝保存
  - 排序变化不清命中状态
  - 编辑 / 删除凭据清命中状态

- `test_collect_hit_state_service.py`
  - 第一次凭据失败不进入冷却
  - 第二次凭据失败进入 `known_failed`
  - 冷却按 `1h -> 4h -> 24h` 递增
  - 成功后 `consecutive_failures` 与 `cooldown_level` 归零
  - 任务级失败不污染对象级状态

- `test_collect_dispatch_service.py`
  - 已命中对象优先复用成功凭据
  - 未命中对象按凭据顺序试探
  - 冷却中凭据跳过
  - 同一对象同轮命中即停
  - JOB / SNMP / PROTOCOL 三类入口都走 dispatch service

- `test_collect_credential_event_nats.py`
    - 批量推送结果可通过 `receive_collect_credential_result` 正确落库
    - 接收端输出 batch/event 摘要日志
    - legacy `sync_collect_credential_results_task` 返回 skipped，不再主动拉取 Stargazer

- `agents/stargazer/tests/test_collect_credential_push.py`
    - `server.py` 启动时注册独立推送循环
    - `push_once()` 将批量结果发布到 `bklite.receive_collect_credential_result`
    - 无数据 / 成功推送两类日志都可观测

- `test_flatten_collect_credential_pool_cmd.py`
  - `--dry-run` 不改数据
  - `--all` 压平所有多凭据任务
  - 压平后旧结构为单个 dict

### 前端校验

- 创建任务时可录入 1..3 个凭据。
- 编辑任务时能正确回填 `credential_id` 与密码占位。
- 删除、排序、新增后提交 payload 正确。
- 不同任务类型只显示本链路允许的字段。

### 验证命令

```bash
cd server && uv run pytest apps/cmdb/tests/test_collect_model_credential_pool.py apps/cmdb/tests/test_collect_hit_state_service.py apps/cmdb/tests/test_collect_dispatch_service.py apps/cmdb/tests/test_flatten_collect_credential_pool_cmd.py -v
cd server && uv run pytest apps/cmdb/tests/test_collect_credential_event_nats.py::test_receive_collect_credential_result_processes_pushed_event_batch apps/cmdb/tests/test_collect_credential_event_nats.py::test_receive_collect_credential_result_logs_batch_summary apps/cmdb/tests/test_collect_credential_event_nats.py::test_sync_collect_credential_results_task_is_disabled_in_push_mode -v
cd agents/stargazer && uv run pytest tests/test_collect_credential_push.py -v
cd web && pnpm lint && pnpm type-check
```

---

## 8) 发布与回滚策略

### 发布步骤

1. 发布后端代码与迁移。
2. 执行数据库迁移，创建 `collect_task_credential_hit` 表。
3. 发布 Stargazer 代码，确保各云区域实例都注册周期推送循环。
4. 发布前端任务配置页。
5. 先验证老任务单凭据运行，再验证多凭据新任务。
6. 观察 Stargazer 推送日志与 CMDB 接收日志，确认批量结果已落库。

### 回滚策略

1. 停止新建/编辑多凭据任务入口。
2. 执行：

```bash
cd server
uv run python manage.py flatten_collect_credential_pool --all
```

3. 确认所有 `CollectModels.credential` 已压平为单个 dict。
4. 回滚后端/前端代码。
5. 保留 `collect_task_credential_hit` 表，不做删表；旧版本忽略该表即可。

### 回滚判定

- 若 JOB / SNMP / PROTOCOL 任一链路出现大面积异常，优先走“压平凭据池 + 回滚代码”。
- 若仅命中状态回写异常但采集仍可用，可先热修服务层，不立即回滚。
