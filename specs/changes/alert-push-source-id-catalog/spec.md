# 监控源目录与 IN 筛选

日期：2026-09-17。状态：已实施。

把实际上游推上来的监控源收成按组织可见的候选清单，供规则配置和列表筛选勾选；清单未识别到的值仍可手输。目录放在 Redis。Alert 侧读写都走现有 `push_source_ids` 快照。不加表、不加列、不做 schema migration。

## 不变的事实

- Event 与监控源一对一：`Event.push_source_id` 是单值字符串，接入时写入，缺省 `default`。空串不进入目录。
- `"001"` 与 `"1"` 是不同身份。
- Alert 与监控源是多对多快照：现有 `Alert.push_source_ids` 由关联流程去重维护，接口只读。本轮不改这列的写入或回填命令。
- 本轮不加表、不加列、不做 schema migration。`batch_init` 与启动期不重建目录。

## 目录

按组织切开的观测目录。成员来自 Alert 快照里出现过的 ID，不是现场扫 Event 表。

| 职责 | 行为 |
| --- | --- |
| 观察 | 快照被写入或刷新时（现有 `monitor_sources` 关联入口：聚合创建/追加、即时告警、恢复关联）收集本批非空 ID，按该 Alert 的 `team` 展开到各组织。无组织不写。快照事务不依赖这次 Redis 写入。 |
| 节流 | 进程内同一 `(team_id, push_source_id)` 约 60 秒内不重复刷 Redis。 |
| 存储 | Redis ZSET `alerts:push_source_ids:v1:{team_id}`，member 为原字符串，score 为 last-seen unix 时间。pipeline `ZADD`。 |
| 封顶 | 单组织 2000。已在集合中的 ID 仍更新 score；满员后拒绝新 ID，打有界汇总日志（组织、当前大小、拒绝次数），不打 ID 清单。 |
| 淘汰 | 90 天未刷新的 member 可按 score 从目录移除。库内快照与事件仍在；已保存规则值仍回显、仍匹配。 |
| 读缓存 | 可选 Django cache `alerts:push_source_ids:options:v1:{team_id}`，TTL 30–60 秒。 |

写入 Redis 失败只记有界日志，告警关联照常提交。尚未聚合成告警的 Event 不会进入目录，可接受延迟；通道 2 仍可手输。

## 冷启动

用 ready 标记区分「从未构建」和「构建过但确实为空」：`alerts:push_source_ids:ready:v1:{team_id}`。空结果也打标记。

| 现场 | 行为 |
| --- | --- |
| 应用滚动发布 | Redis 目录与 ready 仍在，不重建。进程内节流清空无害。 |
| Redis 清空、新集群、旧数据升到本版本 | 无 key。第一次打开该组织 options 时重建。 |

重建只在运行期、按组织发生，不进启动脚本：

- 窗口：Alert `last_event_time`（空则 `updated_at`）近 90 天。
- 组织过滤复用现有 JSON 成员查询（含「包含子组织」时对缺标记的 `team_id` 分别重建，读侧并集）。
- 在 Python 里展开 `push_source_ids` 去重，score 取该 ID 最近一次出现所在告警的窗口时间。不用 raw SQL unnest。
- 超过 2000 留最近活跃的 2000，`ZADD` **合并**进现有成员，不得覆盖重建期间新观测到的 ID。
- 短锁挡住 stampede。

快照仍为 `[]` 的历史告警不贡献目录成员；需要的话先跑既有 `backfill_alert_monitor_sources`。90 天以外的 ID 可以不在下拉里；通道 2 手输和已保存回显仍有效。全历史暖目录用可选管理命令（主键游标、可重跑、不触发分派/通知），不是发布门禁。

Redis 在读时不可用：本次请求直接返回该次重建结果，不让配置页失败。重建失败则返回已有成员（可能为空），前端可重试。

## 读接口与页面

`GET .../api/push_source_ids/options/`，权限对齐集成源 options（五个规则入口 + 告警查看）。按当前组织（及子组织并集）返回去重字符串列表，近到远。

五个规则入口的监控源取值改为两通道，写入同一条件的字符串数组，现有操作符与保存上限不变（最多 50 项、每项 256 字符）：

1. **已识别清单**：可搜索多选下拉，勾选当前组织目录。加载中显示 loading；空清单提示暂无已识别监控源，不挡住通道 2。
2. **自行输入**：回车添加。目录未识别、窗口外或新集群用。已保存但不在清单中的值走此通道回显。

通道 2 输入的值若已在清单中，归到通道 1 勾选，不生成重复项。通道 2 在目录重建完成前即可用。目录失败只影响通道 1，提供重试。

## 列表 IN（走 Alert 快照）

Alert 列表筛选是对快照做成员 IN（`any_of`），不是 JOIN Event，也不是把 JSON 当文本搜。

| 列表 | 参数 | 查询 |
| --- | --- | --- |
| Alert | `push_source_ids`，JSON 字符串数组 | 快照 `any_of`：`push_source_ids ∩ 名单 ≠ ∅`。实现复用现有监控源集合匹配（有界批次物化主键与快照），与分派规则同一套语义。 |
| Event | 同名同形状 | `push_source_id__in` 该名单（Event 仍是一对一单值，没有快照列） |

与集成源 `source_names` 相同：不用逗号拼接。单元素也发数组。现有 Event 的单值 `push_source_id` 精确过滤保留，互不影响。

一条告警快照里有多个监控源时，任一在名单中即入选。空名单或不传参数不筛选。空快照 / 空 `push_source_id` 不命中。未回填快照的历史告警在 Alert 列表上不命中，即使关联 Event 上已有单值。

规则入口的匹配仍用现有 `push_source_id` / `push_source_ids` 契约，本轮不改操作符。

告警列表页的监控源筛选用同一套两通道控件，查询走快照 IN。

集成源详情事件列表的监控源筛选用同一目录：Ant Design 可搜索多选下拉（含全部与自定义录入）。空选择不筛选；查询走 Event `push_source_ids` JSON IN。

详情页展示该集成源下各监控源的缓存事件数量。点击统计项即套用对应监控源筛选。数量按组织 + 集成源缓存在 Redis HASH，接入时递增，冷启动从近 90 天 Event 聚合；允许延迟，不每次 COUNT。

## 测试

- 观测：快照刷新后写入对应组织 ZSET、节流、满员拒新 ID、组织隔离、无组织不写、Redis 失败不影响关联提交。
- 冷启动：无 ready 时从 90 天 Alert 快照重建；空结果打标；锁；合并不覆盖；升级/Redis 清空后第一次 options 能看到窗口内快照 ID；不在 `batch_init` 中执行。
- 列表 IN：Alert 快照含多名单一员即中、快照为空或全不在名单则不中；不因关联 Event 有值而绕过空快照。Event 列表按单值 IN。
- 前端：两通道合并去重、清单项不进手输、缺失清单值回显、目录失败仍可手输保存。

不测 Event JOIN 筛选，不测新的 Postgres 目录表或新列。

验证命令（已跑通）：

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/alerts/tests/test_push_source_catalog_service.py \
  apps/alerts/tests/test_push_source_id_views.py \
  apps/alerts/tests/test_push_source_id_list_filter.py \
  apps/alerts/tests/test_monitor_sources_service.py \
  apps/alerts/tests/test_monitor_sources_chain.py \
  --nomigrations --create-db --no-cov
```

```bash
cd web && ./node_modules/.bin/vitest run --config vitest.config.ts \
  src/app/alarm/components/__tests__/push-source-select.test.tsx \
  src/app/alarm/components/__tests__/monitor-source-rules.test.tsx \
  src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx \
  src/app/alarm/components/__tests__/alarm-push-source-filter.test.tsx
```

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run python manage.py makemigrations alerts --check --dry-run
```

## 发布

只发代码。无需 migrate。Redis 无数据时第一次打开配置页会从快照重建，可接受延迟。未回填快照的环境先跑既有 `backfill_alert_monitor_sources`，再依赖目录与 Alert 列表 IN。前后端需同发。
