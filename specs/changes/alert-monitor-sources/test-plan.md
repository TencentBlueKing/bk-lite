# 监控源完整性与链路测试

## 测试边界

延续已确认的公开入口：策略保存、事件接入、聚合/即时建警、恢复关联、自动分派/屏蔽、详情与关联查询、前端条件编辑与展示。数据库使用真实 Django ORM 测试库，普通聚合使用真实 DuckDB 内存引擎，outbox 投递执行真实任务和分派逻辑。

仅隔离外部边界：权限服务返回组织 1 的授权；异步即时建警用模拟 Broker 接收真实 JSON 载荷，再执行真实 worker 任务；前端模拟 API 与登录/元数据上下文，使用真实表单、条件编辑器和提交逻辑。没有以 mock 替换建警、匹配器或分派实现。

## 覆盖矩阵

| 场景 | 可观察结果 | 测试文件 |
|---|---|---|
| 策略 API → 接入 → 屏蔽 → 即时建警 → outbox → 分派 → 详情/事件接口 | 被屏蔽来源不建警；命中来源分派到目标人员；未命中保持未分派；重复上报和重复投递不改变来源和责任人 | `server/apps/alerts/tests/test_monitor_sources_chain.py` |
| 接入 → DuckDB 聚合 → 追加来源 → 待分派兜底任务 | 同一告警保留旧来源、合并新增来源；新来源命中后分派；已分派者保持原责任人 | 同上 |
| 51 条事件触发异步建警 | JSON 任务载荷经过真实 worker；任务重放不重复建警；Broker 失败同步兜底；`001` 与 `1` 分别匹配 | 同上 |
| 恢复/关闭接入 | 主关联键匹配与唯一回退关联均维护来源；恢复和关闭事件重复上报不重复关联 | 同上 |
| 历史回填 → 待分派重试 → API PATCH | 历史空列表回填后参与匹配，API 不能伪造来源 | 同上 |
| 列表、详情、事件分页、Incident 告警、关联告警 | 告警来源集合不受事件分页截断；组织 2 的来源不能由组织 1 读取 | 同上 |
| 策略 API 非法更新 | 错字段、非法操作符、非字符串、空白、超长和非法正则返回 400，原规则保持不变 | 同上 |
| 五种操作符、AND/OR、跨 200 条候选分批 | 列表成员匹配、否定和空列表语义正确，候选集之外不受影响，错误条件不扩大命中 | `test_monitor_source_rules_service.py`、`test_monitor_sources_service.py` |
| 标识符边界 | 256 字符、中文、引号/反斜杠、`default`、前导零原值往返；事件空值不命中否定规则 | `test_monitor_source_rules_service.py` |
| 聚合/恢复关联事务回滚后重试 | 事件关联与监控源同时回滚；同进程重试能够重新关联、补齐来源 | `test_monitor_sources_service.py` |
| 回填空库、参数、预览、分批、重复执行 | 预览不落库，参数越界拒绝，不改变状态和更新时间，不产生 outbox | `test_monitor_sources_backfill_service.py` |
| 回填中断与数据变化 | 已完成批次保留，`after_id` 续跑；跨页删除不漏后续记录；无事件记录清空陈旧值；启动后的新增记录留待下一轮 | 同上 |
| 真实 0031 正反向迁移 | 独立测试表中的旧记录默认 `[]`，新记录默认值正确，JSON List 可持久化，反向迁移保留其他字段 | `test_monitor_sources_migration.py` |
| 前端分派/屏蔽真实配置页 | 从下拉框选择监控源和操作符，新增/编辑请求分别提交复数/单数字段；`001` 保持字符串；空白阻止提交、修正可提交 | `web/src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx` |
| 前端详情与规则编辑器 | 两种详情、展开/收起/复制、旧响应占位、编辑回显、默认规则入口隔离 | 同目录 `monitor-sources.test.tsx`、`monitor-source-rules.test.tsx` |

## 本次发现与修复

回滚测试先复现聚合重试遗漏：数据库事务已回滚，但 `AlertBuilder` 的类级事件关联缓存保留了未提交的事件 ID，再次聚合将其视为已关联。现改为在既有 Alert 行锁内查询本批 ID 的真实关系后追加。修复前只有聚合回滚重试失败，修复后聚合和恢复两条回滚重试均通过。

## 验证结果（2026-09-09）

- 本轮新增后端 48 项、前端 6 项；监控源专项后端共 75 项。
- 扩展到 21 个相关后端测试文件，共 282 项通过；四个相关运行模块总覆盖率 95%。
- 前端 4 个文件共 20 项通过；新增测试通过 ESLint，后端改动通过 Flake8。
- 未对业务数据库执行迁移或回填。

## 复现命令

在 `server/` 执行专项测试：

```bash
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
uv run pytest \
  apps/alerts/tests/test_monitor_sources_chain.py \
  apps/alerts/tests/test_monitor_sources_migration.py \
  apps/alerts/tests/test_monitor_sources_service.py \
  apps/alerts/tests/test_monitor_source_rules_service.py \
  apps/alerts/tests/test_monitor_sources_backfill_service.py \
  --nomigrations -o addopts='' -o log_cli=false -q
```

在 `web/` 使用仓库要求的 Node 24 执行：

```bash
pnpm exec vitest run \
  src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx \
  src/app/alarm/components/__tests__/monitor-source-rules.test.tsx \
  src/app/alarm/components/__tests__/monitor-sources.test.tsx \
  src/app/alarm/components/__tests__/monitor-object-snapshot.test.tsx
```

## 验证范围限制

这是服务内链路集成测试与前端组件集成测试，不包含真实 Broker/网络传输、浏览器登录到后端的部署级 E2E，也未验证 PostgreSQL 多连接锁竞争。
SQLite 的既有 0009 迁移问题仍在，因此行为测试使用 `--nomigrations`；0031 由独立测试表执行真实 schema migration，不能据此宣称整条历史迁移链已通过。
跨组织详情 CRUD 沿用已有 `HTTP 200 + result=false` 的拒绝响应，关联事件/关联告警入口返回 404；测试同时检查响应没有监控源泄露。
