# 告警业务字段匹配：实施与测试结果

日期：2026-09-10。结论：已按用户确认的 [实施文档](implementation-plan.md) 完成本地实现与验证，尚未部署。本记录取代旧版单选来源 ID、级别单选等方案的验收结论。

## 交付内容

- 相关性、分派、屏蔽、丰富、处理共用字段矩阵，区分字符串子串、标量多候选和集合成员匹配。
- 级别按对应场景下拉多选，保存代码数组；标题和正文仅开放四种简单字符串条件。
- 告警源由用户输入名称后回车确认，没有来源候选下拉。标签去重，保留名称内逗号，支持中文输入法组合输入。
- Alert 告警源通过关联 Event 查询名称集合，排除恢复事件，保留 closed 事件；任一、全部、排除均采用完整名称语义。详情、列表筛选及处理上下文共用此定义。
- 保留 Alert.source_name 字符串快照和通知/参数绑定协议；不新增告警源持久化列。监控源 push_source_ids 的既有持久化与恢复关联维护范围不变。
- 失效规则整条不命中，API 拒绝非法修改并保留原配置；新建空行显示填写提示。

## 环境与最终结果

本机 macOS；Server 使用项目 `.venv` Python 3.12、SQLite 内存数据库、内存 Celery broker/backend。Web 使用 Node 24.15.0、pnpm、Vitest 和本地 Storybook。测试数据独立构造，未访问生产数据库。

| 验证 | 本轮结果 | 范围与证据 |
| --- | --- | --- |
| 后端 alerts 全量 | **1802 通过，1 跳过**，68.01 秒 | `apps/alerts/tests`；原始日志 `/tmp/alert-backend-delivery.log` |
| 前端定向功能 | **5 文件、60 通过**，28.59 秒 | 公共编辑器、五类正式配置组件、规则摘要与详情；`/tmp/alert-frontend-delivery.log` |
| 正式类型检查 | 通过 | `pnpm type-check`，包含 Next route typegen 与项目 TypeScript 检查；`/tmp/alert-typecheck-final.log` |
| 字段目录生成一致性 | 通过 | `generate-alarm-rule-fields.mjs --check` |
| 分派级别多选专项脚本 | 通过 | `alert-assignment-level-multiselect-test.ts` |
| 定向 ESLint | 通过 | 编辑器、匹配工具、列表筛选、详情、测试及 Storybook mock；`/tmp/alert-eslint-final.log` |
| 定向 Flake8 | 通过 | 来源解析器、目录校验、类型匹配器及新增来源服务测试；`/tmp/alert-flake8.log` |
| 浏览器检查 | 通过 | 五个规则场景、来源回车输入、级别多选和深色主题 |
| 变更空白检查 | 通过 | 任务范围 `git diff --check` 及新文档/新增文件空白检查 |

后端唯一跳过项由 `test_k8s_install_token_service.py` 的 `has_select_for_update` 条件控制：SQLite 不支持生产数据库行锁。它不是告警源匹配用例。前端有现有 AntD 属性弃用提示，未导致测试失败。

## 功能、完整性与链路证据

| 范围 | 已验证行为 | 主要测试文件（相对 server/apps/alerts/tests 或 web/src/app/alarm/components/__tests__） |
| --- | --- | --- |
| 全字段矩阵 | 五场景合法/非法字段、操作符和 value 形状，标量候选数组、列表数组、标题正文四操作符 | `test_multivalue_completeness_service.py`、`multivalue-rule-editor.test.tsx` |
| 多执行器一致 | Event 名称候选经 ORM、即时匹配和丰富匹配结果一致；空值、大小写、数字字符串与 AND/OR 反例 | `test_source_name_rules_service.py`、完整性矩阵及现有匹配器测试 |
| 非恢复来源集合 | 任一/全部/排除；恢复不能补齐来源；仅恢复关联时否定也不命中；closed 参与；同名不同 ID 去重；改名与软删除 | `test_source_name_rules_service.py` |
| 五类 API | 新增、读取、修改名称数组；非法修改返回 400，原规则保持不变 | `test_monitor_sources_chain.py` |
| 五类正式表单 | 名称新增与编辑回显、真实保存回调参数；来源没有下拉；级别多选；无效条件阻止保存 | `monitor-source-settings-chain.test.tsx`、`source-name-editor.test.tsx` |
| 输入细节 | Enter 标签、重复去除、中文组合输入、名称含逗号保持一个值、新建空行提示 | `source-name-editor.test.tsx` |
| 详情与列表 | 两套基础信息显示 source_names 而非 source_name 快照；JSON 数组筛选支持逗号名称；列表按批次取值 | `monitor-sources.test.tsx`、`test_source_name_rules_service.py`、`test_alert_list_query_efficiency.py` |
| 来源追加到分派 | 首个来源不足时未分派；第二个来源普通事件实际接入并聚合后，重试分派成功，详情显示两来源 | `test_monitor_sources_chain.py::test_source_name_all_of_from_ingress_append_to_assignment_and_detail` |
| 整体接入链路 | 接入 → 丰富 → 屏蔽 → 即时/周期聚合 → 分派 → 处理与详情；监控源、恢复维护及重复执行回归 | `test_monitor_sources_chain.py` 及 alerts 全量回归 |
| 告警处理 | 追加事件后的最新来源；同次评估多规则只读取一次集合；动作幂等；非法 JSON 规则跳过后仍执行后续合法规则 | `test_source_name_rules_service.py` |
| 候选范围与性能 | 在原组织候选 QuerySet 上过滤；Exists 不产生重复 Alert；来源按页/批次读取；不拉取完整 Event payload | `test_source_name_rules_service.py`、`test_alert_list_query_efficiency.py` |

后端链路使用真实业务入口与测试数据库；外部目录权限、Provider/CMDB、作业/通知等外部边界使用测试替身。前端正式组件测试验证请求参数和回显，浏览器使用 Storybook 配置的测试级别目录；没有声称浏览器连到完整部署后端进行了端到端外部投递。

## 浏览器检查记录

使用本地 Storybook 的 `business-alarm-ruleeditor` 五个场景，检查真实公共编辑器。

1. 分派：监控源“包含全部”展示 a、b；告警源新增 `平台C,生产` 保持单标签、无菜单；级别从严重、预警增加提醒，显示三个级别名称；深色主题文字与控件可读。
2. 屏蔽：切换告警源后仅出现候选“包含/不包含”；回车输入平台 A、平台 B，两个标签正常显示，说明为完整候选匹配。
3. 相关性：指标正则维持单输入，正则值完整呈现，字段/操作符/输入布局无截断。
4. 丰富：内容操作符仅等于、不等于、包含、不包含，无集合条件与正则选项。
5. 处理：监控源排除 test-a、test-b，显示空值不命中说明，标签和操作符完整可见。

Storybook 来源目录不提供选项；新增 level mock 仅供 Storybook 展示业务名称，不影响生产 API。检查结束后关闭临时预览与本次启动的端口 6011 服务。

## 失败复现、修复和审查

- 先增加来源名称/候选交互回归，用失败结果确认旧目录、旧来源取值与新契约冲突，再实现各层；初始失败证据保留于 `/tmp/alert-source-red.log`。
- 更新先前按来源 ID 单选、级别 eq 标量等旧契约编写的合法夹具；非法历史字段反例仍保留。中间全量失败不作为交付结果，最终以新鲜全量 1802/1 为准。
- 规范审查（Standards）：发现标签归一化重复，已复用 `normalizeRuleTags`；发现 Action 原始规则值为整数/布尔值时先遍历会抛异常，已先校验整条规则。
- 契约审查（Spec）：同样发现 Action 非法 JSON 形状可能中断后续规则。先新增 5 种 malformed 值回归，其中整数/布尔值两例复现失败（`/tmp/alert-invalid-action-red.log`），修复后均通过，并确认后续有效动作只执行一次。复审已关闭该问题。
- 中间前端一次在并行重负载验证时出现单例默认超时；隔离重跑及最终完整 60 项均通过，未提高测试超时掩盖问题。
- 工作区存在通知和 Agent 等其他改动，本次保持其状态；全量 alerts 回归通过不代表那些改动由本任务实现。

## 复现命令

后端（仓库根目录进入 server）：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// .venv/bin/python -m pytest apps/alerts/tests --nomigrations -o addopts= -q
```

前端（仓库根目录进入 web；使用 Node 24 环境）：

```bash
cd web
pnpm exec vitest run src/app/alarm/components/__tests__/source-name-editor.test.tsx src/app/alarm/components/__tests__/multivalue-rule-editor.test.tsx src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx src/app/alarm/components/__tests__/monitor-source-rules.test.tsx src/app/alarm/components/__tests__/monitor-sources.test.tsx --maxWorkers=1 --no-file-parallelism
pnpm type-check
node scripts/generate-alarm-rule-fields.mjs --check
node --import tsx scripts/alert-assignment-level-multiselect-test.ts
```

定向静态检查（仓库根目录；工具可执行文件使用本机已安装版本）：

```bash
flake8 --max-line-length=150 server/apps/alerts/service/source_names.py server/apps/alerts/utils/rule_catalog.py server/apps/alerts/utils/typed_rules.py server/apps/alerts/tests/test_source_name_rules_service.py
git diff --check -- server/apps/alerts web/src/app/alarm web/src/stories/alarm-rule-editor.stories.tsx web/.storybook specs/changes/alert-rule-types specs/changes/alert-rule-multivalue specs/changes/alert-monitor-sources
```

定向 ESLint 在 web 下执行，路径用引号保护括号：

```bash
pnpm exec eslint 'src/app/alarm/(pages)/settings/components/matchRule.tsx' src/app/alarm/utils/multivalueRules.ts src/app/alarm/components/alarmFilters/index.tsx 'src/app/alarm/(pages)/alarms/components/baseInfo.tsx' src/app/alarm/components/alarm-base-info/index.tsx src/app/alarm/components/__tests__/source-name-editor.test.tsx .storybook/mocks/alarm/common-api.ts
```

## 发布前仍需验证

- 生产数据库上的关联查询执行计划、索引利用、大批量关联数据性能与行锁竞争。本轮未启动生产型数据库或完整消息中间件。
- 真实外部 Provider、CMDB、作业和通知投递联调。
- 生产存量规则只读盘点及不兼容配置处置；旧规则不会自动转义或迁移为新语义，非法整条规则不命中。
- 既有监控源迁移依赖、前后端与所有规则 Worker 协调发布，以及回退前的新规则处置。

以上是环境/发布检查边界，不把 SQLite、组件测试或 Storybook 验证当作生产部署验证。
