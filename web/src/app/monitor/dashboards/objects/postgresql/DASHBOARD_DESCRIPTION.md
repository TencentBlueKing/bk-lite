# PostgreSQL 监控仪表盘

## 基本信息

- **监控对象**: PostgreSQL
- **对象标识**: Postgres (instance_type='postgres')
- **采集类型**: database
- **数据来源**: Postgres (Telegraf)
- **采集状态查询**: `count({instance_type='postgres', collect_type='database', __$labels__}) by (instance_id)`

## 指标清单

### Connection

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_numbackends | 活跃数据库连接数 | counts | `postgresql_numbackends{__$labels__}` | 监控活跃数据库会话以评估并发负载和连接池使用情况 |
| postgresql_xact_commit_rate | 事务提交速率 | cps | `rate(postgresql_xact_commit{__$labels__}[5m])` | 已提交事务的频率，反映业务活跃度 |
| postgresql_xact_rollback_rate | 事务回滚速率 | cps | `rate(postgresql_xact_rollback{__$labels__}[5m])` | 因失败或冲突导致的回滚频率 |

### Query

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_tup_returned_rate | 查询返回行速率 | cps | `rate(postgresql_tup_returned{__$labels__}[5m])` | 查询结果集中返回的行数 |
| postgresql_tup_fetched_rate | 查询提取行速率 | cps | `rate(postgresql_tup_fetched{__$labels__}[5m])` | 查询期间从存储中提取的行数 |

### DataOperation

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_tup_inserted_rate | 行插入速率 | cps | `rate(postgresql_tup_inserted{__$labels__}[5m])` | 行插入频率 |
| postgresql_tup_updated_rate | 行更新速率 | cps | `rate(postgresql_tup_updated{__$labels__}[5m])` | 反映数据修改活动 |
| postgresql_tup_deleted_rate | 行删除速率 | cps | `rate(postgresql_tup_deleted{__$labels__}[5m])` | 监控数据删除活动 |

### Cache

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_blks_hit_rate | 缓冲区缓存命中速率 | cps | `rate(postgresql_blks_hit{__$labels__}[5m])` | 反映共享缓冲区缓存效率 |
| postgresql_blks_read_rate | 磁盘块读取速率 | cps | `rate(postgresql_blks_read{__$labels__}[5m])` | 评估磁盘 I/O 负载和缓存未命中情况 |

### Concurrency

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_deadlocks_rate | 死锁速率 | cps | `rate(postgresql_deadlocks{__$labels__}[5m])` | 检测事务死锁频率 |
| postgresql_conflicts_rate | 并发冲突速率 | cps | `rate(postgresql_conflicts{__$labels__}[5m])` | 跟踪并发操作引起的冲突 |

### TempFiles

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_temp_files_rate | 临时文件创建速率 | cps | `rate(postgresql_temp_files{__$labels__}[5m])` | 反映复杂查询使用临时文件的情况 |
| postgresql_temp_bytes_rate | 临时文件写入吞吐 | byteps | `rate(postgresql_temp_bytes{__$labels__}[5m])` | 衡量临时文件的磁盘使用量 |

### Checkpoint

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_checkpoints_timed_rate | 定时检查点速率 | cps | `rate(postgresql_checkpoints_timed{__$labels__}[5m])` | 监控系统触发的检查点 |
| postgresql_checkpoints_req_rate | 请求检查点速率 | cps | `rate(postgresql_checkpoints_req{__$labels__}[5m])` | 反映 WAL 压力和检查点调优状况 |

### Buffer

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_buffers_alloc_rate | 缓冲区分配速率 | cps | `rate(postgresql_buffers_alloc{__$labels__}[5m])` | 跟踪共享缓冲区分配 |
| postgresql_buffers_backend_rate | 后端缓冲区写入速率 | cps | `rate(postgresql_buffers_backend{__$labels__}[5m])` | 后端驱动的写入 |
| postgresql_buffers_checkpoint_rate | 检查点缓冲区写入速率 | cps | `rate(postgresql_buffers_checkpoint{__$labels__}[5m])` | 反映检查点 I/O 影响 |

### WriteActivity

| 指标名 | 显示名 | 单位 | 查询表达式 | 说明 |
|--------|--------|------|-----------|------|
| postgresql_maxwritten_clean_rate | 后台清理页写入速率 | cps | `rate(postgresql_maxwritten_clean{__$labels__}[5m])` | 表示写入压力较高 |

## 仪表盘布局建议

### 汇总卡片 (StatCard)

| 标题 | 指标 | 单位 | 图标 | 颜色 | 同环比 | footer | guide |
|------|------|------|------|------|--------|--------|-------|
| 活跃连接数 | postgresql_numbackends | counts | node | #2f6bff | true | 当前活跃数据库会话 | 接近连接池上限需扩容 |
| 事务提交速率 | postgresql_xact_commit_rate | cps | thunder | #27c274 | true | 每秒提交事务数 | 反映业务活跃程度 |
| 事务回滚速率 | postgresql_xact_rollback_rate | cps | thunder | #ff4d4f | true | 每秒回滚事务数 | 非零需关注事务失败原因 |
| 磁盘块读取速率 | postgresql_blks_read_rate | cps | database | #ff8a1f | true | 每秒磁盘块读取次数 | 高值表示缓存未命中 |
| 死锁速率 | postgresql_deadlocks_rate | cps | api | #ff4d4f | true | 每秒死锁次数 | 非零需优化事务设计 |
| 临时文件创建速率 | postgresql_temp_files_rate | cps | thunder | #faad14 | true | 每秒临时文件创建数 | 高值需优化查询或增加 work_mem |

### 趋势图 (TrendChartPanel)

#### 事务提交与回滚
- **副标题**: 事务提交与回滚速率对比
- **系列**:
  | 指标 | 图例标签 | 颜色 | 是否主要 | 虚线 |
  |------|---------|------|---------|------|
  | postgresql_xact_commit_rate | 提交速率 | #27c274 | true | false |
  | postgresql_xact_rollback_rate | 回滚速率 | #ff4d4f | false | false |
- **guide**: [{label: "提交", detail: "成功提交的事务速率"}, {label: "回滚", detail: "因失败或冲突回滚的事务速率"}]

#### 数据操作（读写）
- **副标题**: 行级插入、更新、删除操作速率
- **系列**:
  | 指标 | 图例标签 | 颜色 | 是否主要 | 虚线 |
  |------|---------|------|---------|------|
  | postgresql_tup_inserted_rate | 插入 | #2f6bff | true | false |
  | postgresql_tup_updated_rate | 更新 | #ff8a1f | false | false |
  | postgresql_tup_deleted_rate | 删除 | #ff4d4f | false | false |
- **guide**: [{label: "插入", detail: "行插入速率"}, {label: "更新", detail: "行更新速率"}, {label: "删除", detail: "行删除速率"}]

#### 缓存命中与磁盘读
- **副标题**: 共享缓冲区缓存命中与磁盘读取速率对比
- **系列**:
  | 指标 | 图例标签 | 颜色 | 是否主要 | 虚线 |
  |------|---------|------|---------|------|
  | postgresql_blks_hit_rate | 缓存命中 | #27c274 | true | false |
  | postgresql_blks_read_rate | 磁盘读取 | #ff8a1f | false | false |
- **guide**: [{label: "缓存命中", detail: "由共享缓冲区缓存满足的请求"}, {label: "磁盘读取", detail: "需从磁盘读取的块数，高值表示缓存不足"}]

#### 缓冲区写入活动
- **副标题**: 检查点、后端与后台清理页写入
- **系列**:
  | 指标 | 图例标签 | 颜色 | 是否主要 | 虚线 |
  |------|---------|------|---------|------|
  | postgresql_buffers_checkpoint_rate | 检查点写入 | #2f6bff | true | false |
  | postgresql_buffers_backend_rate | 后端写入 | #ff8a1f | false | false |
  | postgresql_maxwritten_clean_rate | 后台清理 | #8a5cff | false | false |
- **guide**: [{label: "检查点", detail: "检查点期间写出的缓冲区"}, {label: "后端", detail: "后端进程直接写出的缓冲区，高值不正常"}, {label: "后台清理", detail: "后台清理写出的缓冲区"}]

### 详情面板 (DetailPanel)

#### 连接与事务详情
- **副标题**: 连接使用与事务统计
- **字段**:
  | 标签 | 指标 | 单位 |
  |------|------|------|
  | 活跃连接数 | postgresql_numbackends | counts |
  | 事务提交速率 | postgresql_xact_commit_rate | cps |
  | 事务回滚速率 | postgresql_xact_rollback_rate | cps |
  | 死锁速率 | postgresql_deadlocks_rate | cps |
  | 并发冲突速率 | postgresql_conflicts_rate | cps |

#### 检查点与临时文件详情
- **副标题**: 检查点频率与临时文件使用
- **字段**:
  | 标签 | 指标 | 单位 |
  |------|------|------|
  | 定时检查点速率 | postgresql_checkpoints_timed_rate | cps |
  | 请求检查点速率 | postgresql_checkpoints_req_rate | cps |
  | 临时文件创建速率 | postgresql_temp_files_rate | cps |
  | 临时文件写入吞吐 | postgresql_temp_bytes_rate | byteps |
  | 缓冲区分配速率 | postgresql_buffers_alloc_rate | cps |

## 注意事项

- **单位映射**: metrics.json 中 `postgresql_numbackends` 的 unit 为 `short`，不在合法 unit_id 列表中，已映射为 `counts`
- **维度字段**: 多数指标包含 `dbname` 维度，表示数据库名称，查询时可能需按数据库维度聚合
- **无运行时长指标**: PostgreSQL 的 metrics.json 中未包含 uptime 类指标，无法直接展示运行时长
- **缓存命中率需计算**: 如需展示缓存命中率百分比，需通过派生公式计算：`100 * blks_hit / (blks_hit + blks_read)`
- **检查点指标无维度**: `Checkpoint`、`Buffer`、`WriteActivity` 组的指标无 `dbname` 维度，是实例级别的指标
