# CMDB 实例 UUID 切换 Runbook

本 Runbook 适用于已完成脱敏副本演练并批准维护窗口的环境。命令在 Server
容器内执行；凭据只由环境注入，不写入命令记录或报告。

> 与旧参考实现的差异（本分支事实）：  
> - 有 Django `0045_instance_uuid_transition`（**仅结构**；因上游占用 `0044_alter_*` 而顺延编号）  
> - 有维护命令 `migrate_cmdb_instance_uuid_refs` / `migrate_oa_cmdb_instance_uuid_refs`  
> - 有运行期 Celery 任务 `migrate_cmdb_instance_uuid_runtime`：`batch_init` 只注册并
>   `delay` 一次，Worker 起来后幂等 `--apply`，**不**同步挡启动  
> - **没有** `prepare_cmdb_instance_uuid_cutover`、**没有** 删列 cutover 迁移（后续另开，编号另定）  
> - 同步清洗 **不得** 进入 `batch_init` 硬门禁；**不得** 改 `migrate \|\| true` 语义来掩盖失败  
> 详见 `specs/changes/cmdb-instance-uuid/IMPLEMENTATION_PLAN.md` T5/T8。

## 1. 切换前门禁

- 协调备份 PostgreSQL、FalkorDB 与相关对象存储元数据，记录同一恢复点。  
  （本阶段 Neo4j 不在范围。）
- **默认路径（常规升级）**：部署后 `batch_init` 注册运行期任务；Celery Worker
  起来后自动幂等 `--apply`，失败下轮重试。多副本靠任务缓存锁互斥。  
  未完成前非法 UUID 详情仍会失败，但会自动愈合。
- **大流量 / 需验收证据的切换**：仍建议短暂停写，并人工执行下文 `--dry-run` /
  `--apply` / `--verify`，保存原始输出。
- 停止 Web 写流量、Celery worker/beat、NATS CMDB 消费者、Stargazer 配置任务
  及其他 CMDB 写入者（仅人工维护窗口路径需要）；确认旧消息与配置回调已排空或作废。
- 确认待部署的 Server、Worker、OpsPilot、operation_analysis、Stargazer 同版本。  
  **Web 须与后端同发**（见 FRONTEND_HANDOFF）：仅后端切 UUID 而前端仍传数字 ID
  时，资产详情/关系等会失败。
- 图库若存在业务自定义冲突的 `inst_uuid` 语义，停止并人工定责。
- 保存各命令 `--dry-run` / `--apply` / `--verify` 原始输出（人工窗口）。非法/重复 UUID、
  未知结构均为阻断项。

## 2. 副本演练

在隔离的 PostgreSQL + FalkorDB 副本：

```bash
# 1) 结构迁移（随普通 migrate 应用 0045_instance_uuid_transition）
uv run python manage.py migrate cmdb 0045_instance_uuid_transition

# 2) CMDB 图 + PG 活动引用清洗
uv run python manage.py migrate_cmdb_instance_uuid_refs --dry-run
uv run python manage.py migrate_cmdb_instance_uuid_refs --apply
uv run python manage.py migrate_cmdb_instance_uuid_refs --verify

# 3) OA 画布等引用（可与 2 并行于停写窗口）
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --dry-run
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --apply
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --verify

# 4) 再次 --apply / --verify，确认幂等（无新增待清洗项）
uv run python manage.py migrate_cmdb_instance_uuid_refs --apply
uv run python manage.py migrate_cmdb_instance_uuid_refs --verify
```

随后做 **FalkorDB 最小重建烟测**：

1. 记录若干实例的 `inst_uuid`、关联边、一条 PG 引用（如 ConfigFileVersion /
   ChangeRecord / 订阅 filter）。
2. 按运维规程导出/重建图，使节点图 `_id` 变化但保留节点 `inst_uuid` 与边
   `src_inst_uuid`/`dst_inst_uuid`（或清洗后等价恢复）。
3. 按 UUID 打开实例详情、关系、拓扑、配置文件、订阅；确认仍命中同一业务实例。

旧 MinIO `content_object_key` 不得因清洗移动或删除。

## 3. 生产切换

1. 关闭并确认旧写入者退出。  
2. 创建协调备份。  
3. 部署新 Server/Worker/Agent；**先不恢复业务写流量**。  
4. 普通 `migrate` 应用 `0045_instance_uuid_transition`（启动脚本既有顺序；**不要**在 `batch_init` 内同步跑清洗）。  
   `batch_init` 只会注册 Celery 周期任务并 `delay` 一次异步清洗。  
5. （可选，大流量窗口）在维护编排中执行 §2 清洗与 verify；保存原始输出。  
   常规升级可依赖 Worker 运行期自动收敛。  
6. 启动 NATS/Celery/Stargazer 等消费者；按发布节奏启动 Web。  
7. 冒烟：数字 URL/path 安全失败；UUID API/OpenAPI/配置回调成功；Telegraf 标签仍为
   `cmdb_{task_id}`；运行期任务日志出现 apply 完成或已完成跳过。

禁止：把同步 `--apply` 塞进 `batch_init`；用 `sleep`/吞异常掩盖启动依赖；旧 Worker 与新版本并行写。

## 4. 验收证据

- dry-run / apply / verify 输出与耗时；迁移前后计数与孤儿清单。  
- 实例 `inst_uuid` 合法且全局唯一；边无 `src_inst_id`/`dst_inst_id`。  
- PG 活动引用具备 UUID 字段（过渡期部分 JSON 仍可双写旧数字键，以命令实现为准）。  
  运行期还会清洗：订阅 `snapshot_data`、采集 `instances/params`、采集结果快照、
  Operation `request/result_snapshot` 与未成功 Outbox `payload`。无法映射的孤儿只计数、不阻断 verify。  
  变更历史 `before_data/after_data` 与系统操作日志本阶段不迁。  
- 图重建烟测记录。  
- 自动化证据见 `specs/changes/cmdb-instance-uuid/ACCEPTANCE.md`。

## 5. 失败处理

- **恢复流量前**：保持停写；可修复则幂等 `--apply` 后 `--verify`。放弃切换则用协调备份
  **同时**恢复 PG 与图库。  
- **恢复流量后**：不回退到「对外数字 ID」版本；停相关写流量并前向修复。  
- 禁止只恢复 PG 或只恢复图库。

## 6. 后续可选 cutover（本分支未交付）

删除过渡数字列 / 强制 NOT NULL、或启动期 `prepare_*` 编排，需单独变更与迁移编号
（早期计划曾占用 `0045`；现结构迁移已用该编号，删列 cutover 需另开新号）。在那之前，ConfigFileVersion 等保持 **双列**（`instance_id` +
`instance_uuid`），运行期新写入以 UUID 协议为准。
