# 告警规则多值匹配验证记录

日期：2026-09-09。本地 SQLite；Celery broker/backend 使用内存实现，不依赖本机 Redis。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| Alerts 全模块回归 | 1729 passed / 1 skipped（SQLite 不支持行锁） |
| 共享规则语义/目录/监控源适配覆盖率 | 95%（全量运行，200 statements）；多值语义模块 94% |
| 五个正式页面与真实编辑组件测试 | 35 passed（3 个测试文件） |
| Web `pnpm type-check` | 通过 |
| 本次 Web 文件定向 ESLint / 新增 Python 测试定向 Flake8 | 通过 |
| 字段目录生成检查 / `git diff --check` | 通过 |
| 浏览器视觉核验 | Storybook 使用正式共享组件，已检查分派、屏蔽、丰富；完整操作符、标签换行、说明行均正常 |
| 全仓 `pnpm lint` | 未通过：38 errors / 94 warnings，错误位于本次未改动的 APM、Log、Monitor 等文件 |

后端范围涵盖 `test_multivalue*`、`test_monitor_source*`、`test_monitor_sources*`、`test_enrichment*`、`test_source_adapter*`、`test_assignment*`、`test_shield*`、`test_strategy_matcher*`、`test_instant*`、`test_action_engine*`、`test_action_payload*`、`test_auto_assignment*`、`test_aggregation_processor*`、`test_setting_strategy*`、`test_action_rule*`。

## 关键行为覆盖

- 五场景合法候选数组写入，空数组、空白、布尔值、超数量/超长度、不适用操作符拒绝保存。
- 标量与列表任意/全部/排除，文本任意/全部/排除关键词，空值不命中；ORM 与内存结果一致。
- 标准字段及 `description` / `level_id` 别名；服务/位置只对事件场景开放。
- 告警源多关联事件任意/排除、去重及候选集合边界；监控源旧规则的批次/AND/OR 兼容。
- 历史中文条件、级别数组、丰富默认等于，以及处理阶段监控源单值操作逐项匹配。
- 即时与周期各一条完整链路：认证接入 → 丰富 Provider → 屏蔽 → 建警 → 分派 outbox → ActionExecution；外部 Provider/动作执行边界 mock，内部编排实际运行。
- 链路反例：屏蔽事件不建警，范围外事件不丰富/建警；仅两条命中事件生成告警并分派；动作重复触发保持幂等。
- 缺失检测仅由匹配多候选监听范围的心跳激活，范围外事件不激活。
- 五个正式页面编辑多值后到实际 API 请求参数；空数组阻止提交；旧监控源新增/编辑契约仍通过。兼容操作符切换保留标签，切换单值操作符清空多项值；完整标题中的逗号不拆分。

## 可复现命令

在 `server` 目录运行完整 Alerts 模块（包含新增完整性、API 和链路测试）：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// \
.venv/bin/python -m pytest apps/alerts/tests --nomigrations -o addopts= \
--cov=apps.alerts.utils.multivalue_rules --cov=apps.alerts.utils.rule_catalog \
--cov=apps.alerts.utils.monitor_source_rules --cov-report=term-missing
```

在 `web` 目录：

```sh
pnpm exec vitest run --fileParallelism=false \
src/app/alarm/components/__tests__/multivalue-rule-editor.test.tsx \
src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx \
src/app/alarm/components/__tests__/monitor-source-rules.test.tsx
pnpm type-check
node scripts/generate-alarm-rule-fields.mjs --check
```

完整本地输出保存于 `/tmp/multi-complete-alerts-final.log`、`/tmp/multi-complete-ui.log`、`/tmp/multi-complete-typecheck.log`、`/tmp/multi-complete-repo-lint.log`。前端测试按文件串行执行，保留原有断言。

## 尚未验证的环境边界

未连接生产 PostgreSQL、真实消息中间件、外部 CMDB Provider 或作业执行服务；链路测试不等于已在部署环境联调。生产上线前应补 PostgreSQL 查询语义与 API/Worker 同版本的预发布冒烟。本轮未启动数据库迁移、提交代码或部署。

## 本次完整性与功能补测

- 新增 `test_multivalue_completeness_service.py`：独立于代码目录列出产品字段矩阵，13 个字段 / 57 组字段操作组合，每组验证合法场景的写入校验、ORM、即时判断、丰富字典与处理字典结果一致。另覆盖 20/21 组、100/101 条、空组、未知字段；数值 0、001/1、重复候选值，以及 203 个组织内候选跨批次 AND/OR 与另一组织的隔离，限制查询次数。
- 五类真实 API 覆盖 create → retrieve → PATCH → retrieve；非法 PATCH 返回 400，随后 GET 仍返回原条件，防止失败写入改变匹配范围。
- 完整接入链路改为通过真实策略 API 更新相关性规则、创建丰富/分派/屏蔽/处理规则；仅 mock 外部 Provider、作业执行和认证目录边界。
- 聚合追加生命周期同时验证旧 eq 与新 all_of：首个来源不满足规则而不分派；来源凑齐后兜底分派生效；来源去重；已分派告警不因后续来源追加而重新分派。
- 五个正式前端入口覆盖新增和编辑的多值 API 参数、非法空数组阻止提交；丰富新增测试从空表单填写并切换筛选范围。
- 修复补测发现的真实交互问题：分派开启历史级别多选时，监控源切回单值操作符会残留数组。现在只对实际级别字段保留历史多选行为，其他字段按单值契约清空多项候选；两种配置均有回归。

## 全量回归夹具修正说明

首次全量运行有 8 个失败，已单独复现并保留 `/tmp/multi-complete-alerts.log` 与 `/tmp/multi-baseline-isolated.log`。未为这些失败修改生产通知、升级或权限逻辑：

- 升级调度已按 `next_escalation_at` 扫描；旧夹具只修改 `layer_started_at`，实际截止时间仍在未来。三个测试同步推进到期时间，保持原升级、认领停用和空组织等待断言。
- 已确认的通知契约支持 `append_receivers`，更新 RPC fake 和参数断言，并覆盖 true/false；日志敏感信息与返回值断言保留。
- SQLite 的 JSON 成员查询走兼容路径，会先读取主键。查询预算按数据库能力区分，数据可见性和 GROUP BY 断言保留，原生 JSON 数据库仍执行原预算。
- 安装令牌并发测试依赖 `select_for_update` 行锁；SQLite 不具备此能力，增加数据库能力条件。该测试在 PostgreSQL 等支持行锁的环境执行，当前跳过，不计为通过。未捕获或掩盖数据库锁异常。
