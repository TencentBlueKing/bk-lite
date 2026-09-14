# 五入口字段 × 条件交叉测试

日期：2026-09-10。状态：已完成交叉测试与本地回归。

本轮任务：逐项覆盖相关性、分派、屏蔽、丰富、处理的每个筛选字段和每个合法条件，并验证非法组合不会放宽筛选。

契约来源：[已确认实施文档](implementation-plan.md)。独立测试清单：[字段与条件矩阵](field-operator-test-matrix.json)。本轮结果补充此前的 [实施与测试报告](business-matching-test-results.md)，不复用此前数字。

## 覆盖口径

| 入口 | 字段数 | 合法字段 × 条件组合 | 实际验证边界 |
| --- | --- | --- | --- |
| 相关性 | 11 | 38 | 规则 API 新增/读取/修改；ORM、即时内存匹配；周期聚合与即时建警产出的 Event 集合 |
| 屏蔽 | 11 | 38 | 规则 API；EventShieldOperator 真实屏蔽结果 |
| 丰富 | 11 | 38 | 规则 API；真实 EnrichmentEngine、CMDBProvider、投影后返回内容 |
| 分派 | 9 | 30 | 规则 API；AlertAssignmentOperator 实际分派结果 |
| 处理 | 9 | 30 | 规则 API；真实 ActionEngine、JobActionHandler、动作执行记录及 running 状态 |
| 合计 | 51 个入口字段 | **174** | 174 个独立参数化用例，不把五入口藏在同一个用例循环里 |

前端同时覆盖公共编辑器与五个正式配置表单：每个组合均验证控件修改、提交值及重开回显。所有接口新增/修改规则使用真实后端 API；前端 HTTP 边界为测试替身。

## 完整字段与条件表

下表每行的全部操作符在该行所有入口均已分开参数化。条件名称和控件语义以实施文档为准；这里列机器操作符便于核验。

| 字段 | key | 入口 | 条件 | 组合数 |
| --- | --- | --- | --- | --- |
| 标题 | title | 相关性、屏蔽、丰富 | eq / ne / contains / not_contains | 12 |
| 正文/内容 | description | 相关性、屏蔽、丰富 | eq / ne / contains / not_contains | 12 |
| 告警源 | source_name | 相关性、屏蔽、丰富 | any_of / none_of | 6 |
| 级别 | level | 相关性、屏蔽、丰富 | any_of / none_of | 6 |
| 类型对象 | resource_type | 相关性、屏蔽、丰富 | any_of / none_of | 6 |
| 对象实例 | resource_id | 相关性、屏蔽、丰富 | any_of / none_of | 6 |
| 监控源 | push_source_id | 相关性、屏蔽、丰富 | any_of / none_of | 6 |
| 资源名称 | resource_name | 相关性、屏蔽、丰富 | any_of / none_of / contains / not_contains / re | 15 |
| 指标 | item | 相关性、屏蔽、丰富 | any_of / none_of / contains / not_contains / re | 15 |
| 服务 | service | 相关性、屏蔽、丰富 | any_of / none_of / contains / not_contains / re | 15 |
| 位置 | location | 相关性、屏蔽、丰富 | any_of / none_of / contains / not_contains / re | 15 |
| 标题 | title | 分派、处理 | eq / ne / contains / not_contains | 8 |
| 正文/内容 | content | 分派、处理 | eq / ne / contains / not_contains | 8 |
| 告警源 | source_names | 分派、处理 | any_of / all_of / none_of | 6 |
| 级别 | level | 分派、处理 | any_of / none_of | 4 |
| 类型对象 | resource_type | 分派、处理 | any_of / none_of | 4 |
| 对象实例 | resource_id | 分派、处理 | any_of / none_of | 4 |
| 监控源 | push_source_ids | 分派、处理 | any_of / all_of / none_of | 6 |
| 资源名称 | resource_name | 分派、处理 | any_of / none_of / contains / not_contains / re | 10 |
| 指标 | item | 分派、处理 | any_of / none_of / contains / not_contains / re | 10 |

## 每个组合的测试内容

- **真实保存与执行**：新增规则 → GET 回显 → 正向/反向集合匹配 → 实际入口结果；PATCH 合法新值 → GET → 匹配结果随之变化；PATCH 错误 value 类型返回 400，原配置不变。
- **独立字段数据**：每个字段使用自己的哨兵值，其他字段填不同内容；避免标题、正文、资源名称全部相同而掩盖取错字段。
- **精确语义**：大小写、相似前缀、单候选、多候选、重复候选、额外集合成员；单候选仍保存数组。集合全部匹配有真实正例和不齐全反例。
- **字符串与集合区分**：名称含逗号、中文、百分号、下划线、星号、反斜杠；集合按完整元素比较，文本包含按字面子串，保留字段的正则按明确模式匹配。
- **空值**：空字符串、空白、空列表、缺失/错误实际值不命中，否定同样不命中；允许 SQL NULL 的模型字段额外验证 ORM NULL。
- **AND/OR**：每个组合加入另一个独立字段，分别验证同组 AND、不同组 OR、组内顺序交换；非法 OR 分支不能被忽略。
- **保存边界**：所有不允许的操作符、历史/其他场景字段、错误类型、空候选、257 字符、51 候选被拒绝；合法 256 字符和 50 候选边界被接受。非法级别用例先证明合法级别对照能够通过保存。
- **来源集合**：每条来源集合夹具都附加候选恢复事件，验证恢复不能补齐正向匹配或破坏排除；普通/closed 来源与同名去重正常。

## 新增测试构成

后端文件：`server/apps/alerts/tests/test_field_operator_cross_product_service.py`。

| 类型 | 独立用例数 |
| --- | --- |
| API 新增/读取/修改/拒绝与实际入口结果 | 174 |
| 合法组合 × 错误 value；非法 OR 整条拒绝 | 174 |
| 各入口字段 × 全部不支持操作符 | 51（每例遍历该字段所有禁止操作符） |
| 每个组合的 AND/OR 与顺序 | 174 |
| 单候选及字面标点 | 164（级别 10 组合使用目录选项，不接受自由文本） |
| 空值/NULL/缺失/错误实际类型 | 174 |
| 合法长度与数量边界 | 174 |
| 生产目录与独立清单一致 | 5 |
| 其他场景字段及历史字段拒绝 | 5 |
| 新 Worker 进程内置 Provider 可用性 | 1 |
| 合计 | **1096** |

前端新增公共编辑器矩阵 `field-operator-cross-product.test.tsx`：174 控件/菜单/提交/回显 + 174 错误值/非法 OR + 5 目录校验 = **353** 项。正式表单 `monitor-source-settings-chain.test.tsx` 新增 **174** 项完整组合编辑提交与回显，保留原有 29 项新增/编辑等链路用例。

这些是组合覆盖数量，不声称穷尽每种字符串、所有正则模式或全部跨字段排列。

## 本轮发现与修复

**已修复：丰富内置 CMDB Provider 依赖导入顺序。** 单独运行丰富入口时未注册 CMDBProvider，规则命中后仍报 `KeyError`，全量测试中其他测试导入恰好掩盖问题。新增全新 Python Worker 进程回归先复现失败，再在 `get_provider` 首次请求 cmdb 时加载内置实现。没有外部 RPC 或启动依赖新增，也不覆盖已注册的自定义 Provider。

- 失败证据：`/tmp/alert-provider-red.log`；真实丰富矩阵初次失败：`/tmp/alert-cross-second.log`。
- 修复仅修改 `server/apps/alerts/enrichment/providers/base.py` 的获取入口。
- 丰富每例使用独立缓存并清理；仅 mock CMDB RPC，真实 Provider、匹配、绑定和投影均执行。

## 审查

### Standards

规范审查未发现硬违规。缓存名称可能因数据库回滚后规则 ID 重复而复用，已改每例 UUID 名称并在 finally 清理。生产代码使用运行时懒加载，不增加启动依赖。

### Spec

首次发现三处测试盲点：相关性仅 matcher、非法级别缺少合法对照、前端仅公共组件。已分别补充实际周期/即时产物断言、独立 Level 目录及合法保存对照、174 个正式表单用例。只读复审确认三项关闭，无新增可行动问题。

## 环境与验证边界

SQLite 内存数据库、项目 Python 3.12、Node 24。后端业务逻辑、ORM、API、Provider/Handler 均真实；目录权限、CMDB、节点和作业 RPC 使用替身。没有向真实主机执行作业或发送通知。

- 尚未部署；生产数据库执行计划、锁竞争及真实外部服务联调未在本轮运行。
- **已记录的既有非筛选问题**：首次周期聚合夹具的全部 `external_id` 为 NULL 时，DuckDB 将该列推断为 INTEGER，现有分组 CASE 与 VARCHAR 混用导致 BinderException（`/tmp/alert-cross-correlation.log`）。本轮组合夹具改为有外部接入标识的事件，所有被测筛选字段仍独立取值；未修改该旧聚合类型推断问题，不将它声明为已修复。原始字段筛选的空值测试仍保留。
- 中间全量回归遇到工作区既有通知日志断言失败，原始证据 `/tmp/alert-cross-full.log`；本任务未修改通知代码或断言。最终结果以本报告后附的新鲜运行记录为准。

## 复现

仓库根目录进入 server：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// .venv/bin/python -m pytest apps/alerts/tests/test_field_operator_cross_product_service.py --nomigrations -o addopts= -q
```

将测试路径替换为 `apps/alerts/tests` 可跑 alerts 全量回归。新进程回归可用 `-k fresh_worker` 独立执行。

仓库根目录进入 web：

```bash
cd web
pnpm exec vitest run src/app/alarm/components/__tests__/field-operator-cross-product.test.tsx src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx --maxWorkers=1 --no-file-parallelism
pnpm type-check
pnpm exec eslint src/app/alarm/components/__tests__/field-operator-cross-product.test.tsx src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx
```

独立矩阵与生产目录做双向一致性断言：以后新增或减少字段/条件，须同时审查业务清单和测试，不能仅改生产配置后自动生成“永远通过”的期望。

## 最终运行结果

| 检查 | 新鲜结果 | 原始证据 |
| --- | --- | --- |
| alerts 全量后端 | **2900 通过、1 跳过**，127.98 秒 | `/tmp/alert-cross-full-final.log`、`/tmp/alert-cross-backend-final.xml` |
| 其中本轮新增后端矩阵 | **1096 全部通过**，无跳过 | 从 JUnit 逐项核验 |
| 前端 6 文件回归 | **587 全部通过**，141.03 秒 | `/tmp/alert-ui-cross-delivery.log`、`/tmp/alert-cross-frontend-final.xml` |
| 本轮修改的 Provider 模块覆盖率 | **89%**（27 行，未覆盖 3 行） | 全量 pytest 的定向 `--cov=apps.alerts.enrichment.providers.base` |
| 定向 ESLint、Flake8、Black/isort | 通过 | `/tmp/alert-cross-eslint.log` 与本轮命令退出码 |
| 正式 TypeScript 类型检查 | 通过 | `pnpm type-check`，`/tmp/alert-cross-typecheck.log`，退出码 0 |
| 变更与新增文件空白检查 | 通过 | `git diff --check` 及新增文件逐行检查 |

全量后端唯一跳过项仍是 SQLite 不支持 `select_for_update` 的既有测试；新矩阵没有跳过。中间通知日志失败在新鲜全量中通过，本任务未改通知文件。前端仅有既有 AntD 属性弃用提示。

已解析两份 JUnit，按独立清单逐项确认以下三个层面均有成功测试记录，不能只依赖“总测试数增加”：

| 入口 | 后端 API/实际入口 | 公共编辑器交互 | 正式表单提交回显 |
| --- | --- | --- | --- |
| 相关性 | 38/38 | 38/38 | 38/38 |
| 屏蔽 | 38/38 | 38/38 | 38/38 |
| 丰富 | 38/38 | 38/38 | 38/38 |
| 分派 | 30/30 | 30/30 | 30/30 |
| 处理 | 30/30 | 30/30 | 30/30 |

合计三个层面各 **174/174**，全部匹配独立业务清单。


## 提交前独立快照验证

为剔除共享工作区中的通知模板和分派优先级改动，本次将筛选相关文件单独叠加到已提交版本上验证：后端相关测试 **1599 通过**，前端六文件 **587 通过**；格式检查后补跑恢复关联、监控源迁移和分派测试 **60 通过**。正式 TypeScript 类型检查、定向 ESLint 及仓库 Python 提交钩子全部通过。

Python 提交钩子要求收敛已有恢复处理函数的复杂度：两个按主键保序去重循环合并为同一辅助方法，保持首次出现对象及原顺序；另清除无用导入、未使用局部变量并完成指定文件格式化。未改变恢复匹配、分派顺序或通知语义。

原始结果：`/tmp/alert-filter-commit-backend.log`、`/tmp/alert-filter-commit-frontend.log`、`/tmp/alert-filter-commit-final-regression.log`、`/tmp/alert-filter-commit-typecheck.log`、`/tmp/alert-filter-commit-hooks-final.log`。独立快照仅复用安装好的依赖，未复制本地凭据；外部服务仍使用测试替身。
