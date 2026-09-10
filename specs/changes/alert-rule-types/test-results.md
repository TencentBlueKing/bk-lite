# 告警规则类型修复：功能测试结果

日期：2026-09-10。环境：Python 3.12 / Django 4.2 / SQLite；Node 24.15 / Vitest 3.2。

## 最终自动验证

| 验证 | 结果 |
| --- | --- |
| Alerts 全量后端测试 | 1786 passed，1 skipped |
| 规则核心模块行覆盖率 | 96%（194 行，8 行未覆盖） |
| 前端正式弹窗、编辑器、详情测试 | 4 files / 42 passed |
| 五个 Storybook 场景浏览器视觉检查 | 通过；长操作符完整显示，字符串/外键/列表控件与类型一致 |
| 前端类型检查 pnpm type-check | 通过 |
| 字段目录生成检查 | 通过 |
| 级别单值/列表类型脚本 | 通过 |
| 本次修改的规则组件与五个弹窗定向 ESLint | 通过 |
| 后端新规则模块 Flake8（150 字符行长） | 通过 |
| 改动范围 git diff --check | 通过 |
| 全仓 pnpm lint | 38 errors / 94 warnings；既有基线，未涉及本次定向检查文件 |

## 功能覆盖

- 五个真实策略 API 的新增、读取、修改；非法修改返回 400，数据库原规则不变。
- 62 组独立字段/操作符矩阵对照当前模型，验证 ORM、即时内存、丰富、分派和处理的命中记录；包含 Event.source_id 正整数主键、Event.description / Alert.content 的作用域差异。
- 字符串、枚举、外键禁止集合操作符和数组；数字不转成字符串；列表禁止标量、非字符串项、空白、超长、超过 50 项；条件组上限 20、条件总数上限 100。
- 历史字段 source_pk / level_id / 中文 key、旧操作符、缺省操作符均拒绝；一个错误 OR 组导致整条规则不命中。
- Alert.push_source_ids 任一/全部/不含任一，额外成员、重复候选、空列表、前导零身份、跨 200 条批次、AND/OR、组织候选范围与去重。
- 真实接入 → 丰富 → 屏蔽 → 即时或周期聚合 → 自动分派 → 告警处理；外部 Provider 和作业执行边界用 fake，内部业务模块与 ORM 实际运行。
- 来源不足时保持未分派，追加来源后 all_of 生效；重复上报、Outbox 重放、已分派告警、恢复与关闭链路保持原有幂等契约。
- 丰富规则按实际外键匹配；Provider 仍收到业务编码；详情、关联事件、事故列表中的监控源完整且组织隔离。
- 五个正式前端弹窗的单值新增/编辑提交、非法数组阻止提交；分派/处理列表新增/编辑保持数组；编辑器下拉仅含类型合法条件，字段不补入历史项。

## 复现命令

```sh
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// \
.venv/bin/python -m pytest apps/alerts/tests --nomigrations -o addopts= \
  --cov=apps.alerts.utils.rule_catalog --cov=apps.alerts.utils.typed_rules \
  --cov=apps.alerts.utils.monitor_source_rules \
  --cov=apps.alerts.aggregation.strategy.matcher \
  --cov=apps.alerts.aggregation.strategy.instant_matcher \
  --cov=apps.alerts.enrichment.matcher --cov=apps.alerts.action.matcher --cov-report=term-missing

cd ../web
pnpm exec vitest run --maxWorkers=1 --no-file-parallelism \
  src/app/alarm/components/__tests__/multivalue-rule-editor.test.tsx \
  src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx \
  src/app/alarm/components/__tests__/monitor-source-rules.test.tsx \
  src/app/alarm/components/__tests__/monitor-sources.test.tsx
pnpm type-check
node scripts/generate-alarm-rule-fields.mjs --check
node --import tsx scripts/alert-assignment-level-multiselect-test.ts
```

## 验证过程与边界

先以五类字符串集合保存和三类无效 OR 运行期用例复现失败，再修复并通过。先前支持标量数组、中文别名和 source_pk 的测试按已确认的新契约更新为拒绝用例或显式 AND/OR 用例。

一次并行重任务验证中，Storybook 读取正在被 type-check 重建的企业版元数据失败，两项前端测试达到默认 5 秒上限；顺序执行前端测试后 42 项全部通过，未修改超时上限。

跳过项为 SQLite 不支持 select_for_update 的并发安装令牌行锁测试。本次没有执行生产数据库、真实 CMDB/作业服务或部署联调；不把 fake 边界测试等同于外部服务验收。未迁移或转换存量规则。

浏览器验证使用本机 Storybook 的 MultiAssignment、MultiShield、MultiCorrelation、MultiEnrichment、MultiAction 五个场景，检查字段切换清空、字符串五个操作符、外键两个操作符、列表标签及长文案布局。开发服务只监听本机，验证后已关闭。
