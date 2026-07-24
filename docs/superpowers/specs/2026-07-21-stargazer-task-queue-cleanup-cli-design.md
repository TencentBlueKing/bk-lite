# Stargazer 任务队列清理 CLI 设计

- 日期：2026-07-21
- 状态：待书面评审
- 适用模块：`agents/stargazer`
- 运维入口：Stargazer 容器内 CLI

## 1. 背景与目标

Stargazer 通过 ARQ 将 `TaskQueue.enqueue_collect_task` 生成的采集任务写入 Redis。应用层另以 `task:running:<task_id>` 和 `task:dedupe:<dedupe_key>` 保存 job ID；只要该 job 仍位于 `arq:queue` 或存在 `arq:in-progress:<job_id>`，相同任务再次下发就会返回 `status=skipped`。当 Worker 异常退出、队列长期积压或状态未正常收敛时，这些状态会阻止新任务入队。

当前项目没有受支持的队列清理 API 或 CLI，README 中提到的历史清理脚本也不存在。临时使用 `redis-cli` 容易只删队列而遗漏应用标记，或误用 `FLUSHDB` 删除同库的 callback、凭据状态及其他运行数据。

本需求新增一个随 Stargazer 镜像发布的长期运维 CLI，使运维人员可进入容器后先 dry-run，再显式执行精准清理。目标是：

1. 默认只识别并清理阻塞新任务的待执行 job 及关联标记。
2. 通过显式参数支持清理全部待执行 job。
3. 默认保护正在执行的 job；只有确认 Worker 已停止后才允许清理相关 in-progress 状态。
4. 每次正式删除前自动生成可恢复备份，并在状态漂移时 fail-closed。
5. 不开放高危 HTTP 接口，不提供 `FLUSHDB` 或无边界通配符删除能力。

## 2. 已确认决策

- 采用“核心清理服务 + 薄 CLI”，不把高危运维逻辑加入在线 `TaskQueue`。
- 默认模式只处理阻塞入队的目标；`--all-pending` 才处理 `arq:queue` 中全部待执行 job。
- 默认不处理 `arq:in-progress:*`；只有同时提供 `--include-in-progress`、`--worker-stopped` 和 `--apply` 才允许处理。
- `--worker-stopped` 是运维人员对外部状态的显式确认。CLI 不以容器内进程扫描推断分布式 Worker 是否全部停止。
- CLI 默认 dry-run；只有 `--apply` 可以修改 Redis。
- 正式操作前必须备份；备份、校验或 transaction 任一步失败都不得继续删除。
- CLI 直接复用 `core.redis_config.REDIS_CONFIG`，不新增独立 Redis 配置源，也不在输出中暴露密码。

## 3. 范围

### 3.1 包含

- 扫描并解释 `arq:queue`、`arq:job:<job_id>`、`arq:retry:<job_id>`、`arq:in-progress:<job_id>`、`task:running:*` 和 `task:dedupe:*`。
- 默认阻塞目标、全部待执行目标和显式 in-progress 目标三类计划生成。
- 人类可读输出、稳定 JSON 输出和明确退出码。
- 自动备份 Redis DUMP、PTTL、队列 score、执行参数和目标映射。
- 执行前状态复核和单个 Redis transaction 精准删除。
- 单元测试、CLI 合同测试和镜像路径合同测试。
- README 运维说明与容器执行示例。

### 3.2 不包含

- HTTP/NATS 清理接口。
- 自动暂停或重启 Supervisor、Docker、Kubernetes Worker。
- 清空 Redis DB、清理无关结果、callback 上下文或凭据状态。
- 自动判断业务任务是否应重试或重新下发。
- 常驻调度器、定期自动清理或死信队列改造。
- 跨 Redis 实例或跨 DB 批量操作。

## 4. 总体架构

新增以下边界：

```text
scripts/clear_task_queue.py
        │ 参数、输出、退出码、Redis 连接
        ▼
core/task_queue_cleanup.py
        │ 计划生成、备份、漂移校验、事务删除
        ▼
Redis（当前 Stargazer REDIS_CONFIG）
```

### 4.1 核心清理服务

`core/task_queue_cleanup.py` 不解析命令行，也不读取进程状态。它暴露可注入 Redis client 的同步接口：

```python
def build_cleanup_plan(
    redis_client,
    *,
    all_pending: bool,
    include_in_progress: bool,
) -> CleanupPlan: ...

def create_cleanup_backup(
    redis_client,
    plan: CleanupPlan,
    *,
    backup_dir: Path,
) -> Path: ...

def apply_cleanup_plan(redis_client, plan: CleanupPlan) -> CleanupResult: ...
```

`CleanupPlan` 是不可变值对象，保存目标 job ID、队列 score、目标键、marker→job 映射、模式和用于漂移校验的状态指纹。`CleanupResult` 保存实际删除数量和剩余队列数量。核心服务不记录 job payload，也不输出密码。

### 4.2 CLI

`scripts/clear_task_queue.py` 负责：

- 将 Stargazer 根目录加入 import path，支持固定命令 `python /app/scripts/clear_task_queue.py`。
- 读取参数并验证危险组合。
- 通过 `REDIS_CONFIG` 创建同步 Redis client 并执行 `PING`。
- 调用核心服务，格式化人类可读或 JSON 输出。
- 将已知失败映射为稳定退出码。

Dockerfile 已使用 `ADD . .`，新增脚本会自然进入 `/app/scripts/`，不修改镜像复制逻辑。

## 5. 目标选择规则

### 5.1 默认模式

1. 使用 `SCAN` 分页读取 `task:running:*` 和 `task:dedupe:*`，禁止 `KEYS`。
2. 读取 marker 值作为 job ID。
3. 仅当 job ID 是 `arq:queue` 成员，且不存在对应 `arq:in-progress:<job_id>` 时，将它加入待清理集合。
4. 收集所有指向目标 job 的 running/dedupe marker。
5. marker 只指向 in-progress job 时保留，不因默认清理制造重复执行。

默认模式解决 `enqueue_collect_task` 因旧 job 仍在队列而持续返回 `skipped` 的问题，同时不扩大到无关待执行任务。

### 5.2 `--all-pending`

- 选择 `arq:queue` 中全部 job ID。
- 若某个队列 job 同时存在 in-progress 锁，则默认排除并报告为 protected；只有开启受保护的 in-progress 模式才可选择。
- 收集所有指向已选 job 的 running/dedupe marker。
- 该参数清理的是 Stargazer 默认 ARQ 队列中的全部待执行 job，可能包含 host callback processing job；CLI 必须在 dry-run 摘要中明确提示这一点。

### 5.3 `--include-in-progress`

- 只处理由 running/dedupe marker 引用或已被 `--all-pending` 选中的相关 job，不扫描后删除所有无关 in-progress 锁。
- 参数校验要求同时存在 `--worker-stopped` 和 `--apply`。
- `--worker-stopped` 仅表示操作者已在外部停止全部 Stargazer Worker；CLI 不自行停止服务。

## 6. CLI 合同

### 6.1 参数

```text
--apply                 执行计划；缺省为 dry-run
--all-pending           选择全部待执行 job
--include-in-progress   包含相关执行中状态
--worker-stopped        确认全部 Worker 已在外部停止
--backup-dir PATH       备份目录，默认 /tmp/stargazer-task-queue-backups
--json                  输出稳定 JSON
```

不提供交互式 yes/no、`--force` 或跳过备份参数，避免自动化环境误确认或绕过安全门。

### 6.2 使用示例

```bash
# 预览默认阻塞目标
python /app/scripts/clear_task_queue.py

# 清理默认阻塞目标
python /app/scripts/clear_task_queue.py --apply

# 清理全部待执行 job
python /app/scripts/clear_task_queue.py --all-pending --apply

# Worker 已停止后，清理全部待执行及相关执行中状态
python /app/scripts/clear_task_queue.py \
  --all-pending \
  --include-in-progress \
  --worker-stopped \
  --apply
```

### 6.3 退出码

| 退出码 | 含义 |
|---:|---|
| `0` | dry-run 成功、清理成功或无目标 |
| `2` | 参数组合非法 |
| `3` | Redis 连接或只读扫描失败 |
| `4` | 备份失败 |
| `5` | 执行前状态漂移，要求重新 dry-run |
| `6` | Redis transaction 执行失败 |

JSON 输出至少包含 `mode`、`dry_run`、`redis_db`、`selected_jobs`、`protected_jobs`、`marker_keys`、`backup_path`、`deleted_jobs`、`remaining_queue_jobs`、`status` 和脱敏错误码。人类输出与 JSON 均不得包含 Redis 密码、任务参数或 DUMP 内容。

## 7. 备份与恢复边界

正式执行时，CLI 在任何删除前创建备份：

1. 默认目录 `/tmp/stargazer-task-queue-backups` 以 `0700` 权限创建。
2. 备份文件以独占方式创建并设置 `0600` 权限。
3. 文件记录时间、Redis host 脱敏标识、DB、CLI 模式、目标 job ID、队列 score、marker 映射、目标键的 Redis DUMP 与原始 PTTL。
4. DUMP 可能包含序列化任务参数和凭据，因此只以 base64 形式写入受限文件，不打印到日志；CLI 明确提示运维人员将备份安全复制出临时容器并按敏感制品管理。
5. 任意目标键 DUMP 读取失败、目录不可写或文件落盘失败时返回退出码 `4`，且零删除。

首期只保证备份信息足以人工恢复，不新增自动 restore 子命令。自动恢复会扩大高危写入面，可在真实运维需求出现后单独设计。

## 8. 状态漂移与事务执行

计划指纹包含：

- 目标 job 的队列成员关系和 score。
- 目标 marker 当前值。
- 目标 job/retry/in-progress 键的存在性和 Redis 类型。
- protected job 集合。

PTTL 会自然递减，不进入相等比较；它只在备份中保存。

`--apply` 的执行顺序为：

1. 构建计划并输出摘要。
2. 按计划目标生成备份。
3. 重新读取指纹；与计划不一致则返回退出码 `5`，零删除。
4. `WATCH` `arq:queue` 与全部目标键，在同一 pipeline 中再次复核指纹。
5. 指纹一致时进入 `MULTI/EXEC`，对目标执行 `ZREM arq:queue` 和精确 `DEL`；任何并发变化触发 `WatchError`，按状态漂移返回退出码 `5`。
6. 非竞态 transaction 失败返回退出码 `6`；不把部分成功表述为成功。
7. 成功后读取剩余队列数并输出结果。

transaction 只保证 Redis 命令批次原子提交，不替代外部停 Worker/停下发要求。使用 `--all-pending --apply` 前应暂停新任务下发；使用 `--include-in-progress` 前必须停止全部 Worker。

## 9. 错误处理与可观测性

- Redis key 类型与预期不符时 fail-closed，并输出键名与实际类型，不尝试强制删除。
- SCAN、GET、ZSCORE、DUMP、文件写入和 transaction 异常分别映射到稳定错误码。
- 没有目标是正常结果，退出码为 `0`。
- dry-run 输出 selected/protected/job marker 数量，便于操作者确认影响面。
- 正式执行输出备份路径、删除 job 数、删除 marker 数和剩余队列数。
- 日志不输出任务 payload、凭据、Redis 密码或备份内容。

## 10. 测试设计

实现严格遵循 TDD，每个行为先写失败测试并确认因缺失行为失败。

### 10.1 核心服务测试

- 默认模式只选择被 running/dedupe 引用、仍在 queue 且不在 in-progress 的 job。
- 默认模式保护只在 in-progress 的 job。
- `all_pending=True` 选择所有安全待执行 job并报告 protected job。
- in-progress 模式只加入相关 job，不扩大到无关锁。
- SCAN 分页而非 `KEYS`。
- 备份文件权限为 `0600`，目录权限为 `0700`，内容覆盖 DUMP/PTTL/score/marker。
- 备份失败时没有 Redis 写命令。
- 指纹漂移时没有 Redis 写命令。
- `WATCH/MULTI/EXEC` 在复核与提交之间检测并发漂移。
- transaction 只删除目标 queue member、job/retry/in-progress 键和关联 marker，无关键保持不变。

测试通过注入行为明确的 fake Redis client 验证命令与状态，不连接开发者或 CI 的真实 Redis。

### 10.2 CLI 测试

- 无参数为 dry-run 且不写 Redis。
- `--include-in-progress` 缺少 `--worker-stopped` 或 `--apply` 时返回 `2`。
- Redis 连接失败返回 `3`。
- 备份、漂移和 transaction 失败分别返回 `4`、`5`、`6`。
- `--json` schema 稳定且不含密码或 payload。
- 固定容器路径 `/app/scripts/clear_task_queue.py` 可直接执行并正确加载 `core`。

### 10.3 验收门禁

```bash
cd agents/stargazer
uv run pytest tests/test_task_queue_cleanup.py -q
uv run black --check core/task_queue_cleanup.py scripts/clear_task_queue.py tests/test_task_queue_cleanup.py
uv run isort --check-only core/task_queue_cleanup.py scripts/clear_task_queue.py tests/test_task_queue_cleanup.py
uv run flake8 core/task_queue_cleanup.py scripts/clear_task_queue.py tests/test_task_queue_cleanup.py
git diff --check
```

最终还需运行 Stargazer 与任务队列相关回归测试，至少覆盖 `test_collect_multicred.py` 和 `test_host_collector.py` 中的 running/dedupe 合同。

## 11. 文档与交付

- 在 `agents/stargazer/README.md` 增加“任务队列清理 CLI”章节，说明暂停下发、停止 Worker、dry-run、apply、备份复制与验证步骤。
- 给出 Docker 与 Kubernetes `exec` 示例，但不把具体集群名、namespace 或凭据写入仓库。
- 文档明确禁止 `FLUSHDB`，并说明 `--all-pending` 可能删除 callback processing 等同队列 job。
- 镜像无需额外 COPY；Dockerfile 的 `ADD . .` 会把 `scripts/` 放到 `/app/scripts/`。

## 12. 验收标准

1. 容器内可执行 `python /app/scripts/clear_task_queue.py`，默认零写入并输出准确计划。
2. 默认 apply 只解除由待执行 job 导致的入队阻塞，不删除无关键或 in-progress job。
3. `--all-pending` 明确选择全部安全待执行 job。
4. 未满足双重确认时无法删除 in-progress 状态。
5. 所有正式删除都有先于 transaction 生成的受限权限备份。
6. 状态漂移、备份失败或 Redis 异常均 fail-closed。
7. 测试覆盖核心选择、安全门、备份、漂移、精准删除、CLI 输出与退出码。
8. Stargazer 定向测试、格式门禁和 `git diff --check` 通过。
