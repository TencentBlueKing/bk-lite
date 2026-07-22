# Historical Superpowers change: 2026-07-07-backend-review-loop

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-07-backend-review-loop-design.md

日期：2026-07-07

## 目标

建立一个可复用的后端周度代码 Review Loop，用于检查最近 7 天提交的后端代码。该 Loop 先用脚本采集事实、聚类变更、生成风险候选队列，再由 Agent 以 Staff Software Engineer 的标准逐项深审。

本设计不以语法扫描或关键词告警为目标。它的目标是帮助 Reviewer 像真实的大型互联网公司后端 Code Reviewer 一样发现：

- Bug、隐藏 Bug、边界情况、并发问题、数据一致性问题。
- Django ORM、DRF、事务、权限、数据库性能、N+1 Query、索引问题。
- 安全漏洞，包括越权、SQL 注入、SSRF、CSRF、路径遍历、敏感日志、Token 泄露。
- API 设计、架构分层、可维护性、可测试性、扩展性、Pythonic 和 Django Best Practice 问题。

Review 不为凑数量而提出建议。如果某段代码没有明显问题，应明确写出“这一部分没有明显问题，我建议保持现状。”如果代码设计优秀，也要说明为什么好。

## 范围

纳入：

- `server/apps/cmdb/`：按 Python/Django Staff Engineer 标准 Review。
- `server/apps/cmdb_enterprise/`：按 Python/Django Staff Engineer 标准 Review。
- `server/apps/alerts/`：按 Python/Django Staff Engineer 标准 Review。
- `server/apps/operation_analysis/`：按 Python/Django Staff Engineer 标准 Review。
- `agents/stargazer/`：按 Python/Sanic/Agent 插件框架标准 Review，不套 Django/DRF/ORM 规则。

排除：

- 除 `cmdb`、`cmdb_enterprise`、`alerts`、`operation_analysis` 外的其他 `server/apps/*`。
- `server/config/`、`server/apps/core/`、`server/apps/base/` 等通用后端目录，除非后续用户明确扩大范围。
- `web/`
- `mobile/`
- `webchat/`
- `algorithms/`
- 其他与后端 Review Loop 无关的路径

默认时间窗口为最近 7 天。脚本应支持通过参数覆盖时间窗口、base/head commit 和输出路径。

## 周期与 token 预算

Review Loop 分为每日轻量循环、周度完整循环和合并前循环。默认自动化周期采用每日轻量循环。

### 每日轻量循环

每日轻量循环定在北京时间每天 `00:15` 之后执行，检查前一天 `00:00:00` 到 `23:59:59` 的后端变更。

每日循环目标不是完整 Staff Review，而是用最低 token 成本识别是否存在 P0/P1 高风险候选。每日循环只输出：

- 前一天后端变更范围。
- P0/P1 候选队列。
- 建议后续人工深审队列。
- 是否需要触发周度完整循环或人工立即介入。

每日循环禁止：

- 逐行深审 P2/P3。
- 生成完整 Staff Review 结论。
- 运行大范围测试。
- 修改业务代码。
- 提交代码。
- 展开大型 diff 或 fixture。

若脚本尚未实现，自动化应只输出“脚本尚未实现，跳过执行”并结束，避免无意义消耗 token。

### 周度完整循环

周度完整循环默认每周执行一次，检查最近 7 天后端变更。周度循环用于生成完整报告、执行 Staff Review、输出 TDD 与覆盖率结论。

周度循环可以消费更多上下文，但仍应先处理 P0/P1，再按剩余预算覆盖 P2。P3 只抽样检查。

### 合并前循环

合并前循环针对当前分支相对目标分支的后端差异执行，例如：

```bash
scripts/review-weekly-changes --base origin/master --head HEAD
```

合并前循环适用于 hotfix、大功能合并、权限/事务/NATS/Celery/Stargazer 采集插件等高风险变更。

### token 预算保护

为了避免耗尽周 token 量，自动化默认使用低推理强度和 quick 模式。任何自动化运行都必须遵守：

- 每日循环只处理 P0/P1 候选，不做完整人工 Review。
- 如果候选过多，只输出 Top N 高风险项和分组摘要，并提示需要人工确认是否继续。
- 不读取大文件、二进制、fixture、locale、锁文件全文。
- 不展开完整 diff；只读取必要 hunk 和路径摘要。
- 不运行全量测试；只给建议命令。
- 不重复扫描上一周期已经确认无风险的低风险文件。
- 发现 P0 安全/权限/数据破坏风险时，立即停止扩展扫描，优先输出该风险和建议人工深审。

建议每日自动化初始状态为 `PAUSED`，待脚本实现并验证后再启用为 `ACTIVE`。

## 角色标准

执行人工 Review 的 Agent 固定扮演：

> 15 年经验的 Python/Django Staff Software Engineer，同时也是大型互联网公司的 Code Reviewer。

该角色不是代码生成器。Review 时应严格、客观、专业，不因为提交者身份降低标准，也不为了提出建议而刻意挑刺。

## 总体架构

Review Loop 分为两阶段。

第一阶段是事实采集与风险排序。脚本只读 git 历史和 diff，输出结构化报告和深审队列。脚本不直接宣称某段代码有 bug，只标记“需要 Staff Reviewer 深审的候选风险”。

第二阶段是 Staff Review。Agent 按报告队列逐项阅读 diff 和上下文，必要时使用 CodeGraph 理解调用路径和影响面，然后按固定输出格式给出分级结论。

建议落地产物：

```text
scripts/review-weekly-changes
scripts/review_weekly_changes.py
tests/test_review_weekly_changes.py
docs/reviews/YYYY-MM-DD-backend-weekly-code-review.md
docs/superpowers/specs/2026-07-07-backend-review-loop-design.md
```

## 脚本职责

`scripts/review-weekly-changes` 是可执行入口。默认行为：

- 检查最近 7 天。
- 只纳入 `server/apps/cmdb/`、`server/apps/cmdb_enterprise/`、`server/apps/alerts/`、`server/apps/operation_analysis/` 和 `agents/stargazer/`。
- 生成 Markdown 报告到 `docs/reviews/YYYY-MM-DD-backend-weekly-code-review.md`。

建议参数：

- `--days 7`
- `--since YYYY-MM-DD`
- `--until YYYY-MM-DD`
- `--base <commit>`
- `--head <commit>`
- `--paths server/apps/cmdb server/apps/cmdb_enterprise server/apps/alerts server/apps/operation_analysis agents/stargazer`
- `--output <path>`
- `--mode quick|full`
- `--previous-day`

`scripts/review_weekly_changes.py` 承载核心逻辑，尽量保持纯函数化，便于测试。

脚本采集的信息包括：

- base/head commit。
- 提交列表、作者、提交信息、merge / non-merge 分布。
- 文件 numstat，包括新增、删除、二进制、rename。
- Django app 或 Stargazer 模块归属。
- 文件角色标签。
- 风险候选等级。
- 建议阅读顺序。
- 建议验证命令。

脚本不执行测试、不安装依赖、不联网、不改业务代码。

## 模块与文件角色识别

`server` 的聚类规则只应用于以下 Django app：

- `server/apps/cmdb/`
- `server/apps/cmdb_enterprise/`
- `server/apps/alerts/`
- `server/apps/operation_analysis/`

四个 app 内部按文件角色聚类：

- `views`、`viewsets`：API 入口。
- `serializers`：输入输出校验。
- `services`：业务规则。
- `tasks`：异步任务。
- `nats`：消息入口。
- `models`：数据模型。
- `migrations`：schema 变更。
- `db_patches`：数据库兼容。

`agents/stargazer/` 的聚类规则：

- `agents/stargazer/api`：Sanic API 层。
- `agents/stargazer/service`：框架服务层。
- `agents/stargazer/tasks`：任务与 NATS 辅助逻辑。
- `agents/stargazer/plugins/inputs`：采集插件。
- `plugin.yml`：插件契约。
- `agents/stargazer/tests`：测试。

## 风险等级

- P0：必须优先深审。可能造成越权、数据破坏、生产事故、安全漏洞、任务失控、跨组织数据泄露。
- P1：高优先级深审。可能造成隐藏 bug、性能退化、数据不一致、异常路径失败、任务不可恢复。
- P2：常规深审。主要是架构分层、可维护性、可测试性、重复代码、Pythonic。
- P3：抽样审查。test-only、文档、低风险配置，除非删除大量测试或触及关键契约。

风险分计算模型：

```text
风险分 = 路径权重 + 关键词权重 + diff 规模权重 + 删除权重 + 测试覆盖修正 + 历史敏感修正
```

风险分只用于排序，不等于最终问题等级。

## Django 后端风险规则

P0 候选：

- 涉及 `permission`、`auth`、`token`、`group`、`team`、`organization`。
- `nats/`、`tasks/` 中新增数据查询或写操作。
- `views/`、`viewsets/` 中新增详情、批量、导出、下载、删除接口。
- `services/` 中新增跨组织资源查询、批量写入、资源归属变更。
- 涉及 API Secret、密码、下载链接、登录、OAuth、回调。
- 删除权限校验、删除过滤条件、扩大 queryset。
- 新增 `subprocess`、文件路径拼接、外部请求、上传下载。

P1 候选：

- `models/`、`migrations/`、`db_patches/`。
- `bulk_create`、`bulk_update`、`update()`、循环 `save()`。
- 缓存写入/失效、状态机、定时任务、重试逻辑。
- `transaction.atomic` 缺失或粒度可疑。
- 捕获宽泛异常后继续执行。
- 循环中 ORM 查询、QuerySet 重复求值。
- Serializer 校验逻辑大改。
- 删除测试或把集成测试改成浅 mock。

P2 候选：

- 大型 service 文件继续膨胀。
- View/Serializer/Task 承担业务规则。
- 跨 app 调内部 helper。
- 重复分支、魔法字符串、隐式状态。
- 类型不清、命名不表达领域含义。
- 缺少边界测试但风险不高。

## Stargazer 风险规则

Stargazer 不是 Django 项目，不应用 Django/DRF/ORM 标准。Review 应按 Python/Sanic/Agent 插件框架标准执行。

P0 候选：

- 采集命令执行、网络扫描、远程连接、凭据处理。
- NATS handler 接收外部任务参数。
- 插件输入参数未经校验直接执行。
- 缺少 timeout、并发边界、资源上限。
- 日志输出密码、token、连接串。

P1 候选：

- 插件输出格式变化。
- `plugin.yml` 契约变化。
- 异步任务未 await、异常吞掉、部分失败无记录。
- 批量采集一个目标失败导致整批失败。
- 新增依赖、锁文件变化、运行时入口变化。

P2 候选：

- 插件代码重复。
- 采集结果字段命名不稳定。
- 测试只覆盖正常路径。
- 框架层与插件层耦合过高。

## 降噪与升级规则

降噪：

- 纯测试新增且不影响断言质量：降级。
- 纯文档：降级。
- 纯 rename 且内容未变：降级。
- 生成类文件或大 fixture：单独列出，不默认深审。
- locale、静态资源、锁文件：只在影响运行时依赖时升高。

强制升级：

- 删除权限过滤。
- 新增后台入口。
- 新增批量删除/更新。
- 新增 token/password/api secret 处理。
- 新增文件路径、外部 URL、命令执行。
- 新增 DB migration。
- 删除或弱化关键测试断言。
- 捕获异常后静默继续。
- 新增跨 app 直接调用内部函数。

## 深审队列生成

脚本应将单文件风险合并成 review 单元，而不是要求 Reviewer 孤立逐文件看。

示例：

```md
### Review 单元：CMDB IPAM 发现链路
风险等级：P0
建议阅读顺序：
1. server/apps/cmdb/views/collect.py
2. server/apps/cmdb/services/ipam_discovery.py
3. server/apps/cmdb/tasks/celery_tasks.py
4. server/apps/cmdb/tests/test_ipam_discovery_service.py
5. server/apps/cmdb/tests/test_ipam_discovery_task.py

重点问题：
- 组织隔离是否贯穿 view/service/task？
- 批量扫描部分失败是否可恢复？
- 是否存在脏 subnet_id 击穿整批？
- Celery 重试是否幂等？
```

Stargazer 示例：

```md
### Review 单元：网络设备配置采集插件
风险等级：P0
建议阅读顺序：
1. agents/stargazer/plugins/inputs/network_config_file/plugin.yml
2. agents/stargazer/plugins/inputs/network_config_file/constants.py
3. agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py
4. agents/stargazer/tests/test_network_config_file_info.py

重点问题：
- 参数是否校验？
- 是否限制命令集合？
- 是否有 timeout？
- 日志是否泄露凭据？
- 输出格式是否稳定？
```

## Staff Review 执行协议

每个 review 单元必须按固定步骤执行：

1. 读变更范围：确认 commit、diff、文件列表、测试文件，以及变更类型。
2. 读运行上下文：补读调用方和被调用方。
3. 判断职责边界：确认代码是否放在正确层级，是否存在职责混杂或跨 app 依赖穿透。
4. 判断正确性与边界：主动寻找空数据、脏数据、缺字段、权限为空、多组织、重复执行、部分失败、并发执行、数据库异常、外部依赖超时、老数据状态不完整等反例。
5. 判断安全与权限：检查水平越权、垂直越权、后台入口绕过前台权限、敏感日志、可控文件路径/URL/命令参数，以及 NATS/Celery 组织上下文。
6. 判断性能与数据库：检查循环查库、QuerySet 重复执行、`select_related` / `prefetch_related`、无界查询、bulk 跨库安全、`update()` 副作用、索引和锁风险。
7. 判断测试质量：检查权限反例、异常分支、脏数据、部分失败、幂等/重复执行、跨库敏感行为，以及是否 mock 掉核心逻辑。
8. 输出结论：有问题按级别输出；没问题明确保持现状；好设计写 Positive Feedback。

复杂链路应使用 CodeGraph 辅助定位调用路径和影响面，尤其是 service 多入口、权限上下文跨层传递、Celery/NATS 异步入口、Stargazer 插件入口和公共 helper 重构。

## Finding 证据要求

每条 finding 必须包含：

- 文件路径和行号。
- 严重级别。
- 触发场景。
- 为什么危险。
- 修复方向。
- 是否已有测试覆盖。
- 建议补充的测试。

不允许空泛结论，例如“建议优化代码结构”“这里可能有问题”“需要注意性能”。证据不足时标为“待确认风险”，不升级为 bug。

## Review 输出模板

每个单元使用以下模板：

```md
### Review 单元：<模块/链路名称>

#### 总体评价（1~10 分）
总体质量：
风险等级：
是否建议合并：
一句话总结：

#### Critical（必须修改）
- 无 / <finding>

#### Major（建议修改）
- 无 / <finding>

#### Minor（优化建议）
- 无 / <finding>

#### Performance
- 无 / <finding>

#### Security
- 无 / <finding>

#### Architecture
- 无 / <finding>

#### Django Best Practice
- 无 / <finding>

#### Positive Feedback
- <说明哪里做得好，以及为什么好>

#### 最终建议
- ✅ Approve / 🟡 Approve with comments / ❌ Request changes
- 理由：
```

`agents/stargazer/` 单元将 `Django Best Practice` 替换为：

```md
#### Sanic / Agent Plugin Best Practice
```

判定规则：

- 有 Critical：最终建议必须是 `❌ Request changes`。
- 有 Security Critical：必须先修，不允许 `Approve with comments`。
- 有 Major 但不阻断主流程：`🟡 Approve with comments`。
- 只有 Minor 或无问题：可 `✅ Approve`。
- 如果代码质量好：明确建议保持现状。

## TDD 修复协议与覆盖率门禁

当 Staff Review 发现需要修改业务代码的问题时，后续修复必须严格遵循 TDD。Reviewer 在提出修复建议前，应先说明这段代码应该被哪些测试保护，并先生成失败测试。只有测试设计完成后，才允许给出业务代码修改建议。

TDD 顺序：

1. 理解需求和现有代码。
2. 设计测试用例。
3. 先写测试代码，形成可失败的测试。
4. 再指出需要如何修改业务代码。
5. 最后用测试验证修复是否成功。

覆盖率硬性目标：

- 行覆盖率：`>= 80%`。
- 分支覆盖率：尽量 `>= 80%`。
- 核心业务逻辑覆盖率：必须 `>= 90%`。

如果当前代码无法达到 80%，Review 结论必须明确指出原因，并继续补充测试建议，不能只写“增加测试”。

### TDD 输出格式

每个需要修复的 finding，如果进入修复设计阶段，必须按以下顺序输出：

```md
## 1. 测试需求分析

说明这段代码应该被哪些测试保护。

## 2. 测试用例清单

| 测试场景 | 输入数据 | 预期结果 | 风险等级 | 是否必须覆盖 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 3. 先生成失败测试

先给出测试代码。测试应覆盖正常流程、异常流程、边界条件、权限、并发、数据库事务、外部依赖 Mock、API 返回值、Celery / Redis / 第三方接口异常。

## 4. 再生成业务代码修改建议

只有测试设计完成后，才允许给出业务代码修改建议。

## 5. 覆盖率检查

给出适合当前模块的覆盖率命令。

## 6. 覆盖率不足时的处理

明确哪些文件、函数、分支没覆盖，应该新增哪些测试，并给出新增测试代码。

## 7. 最终结论

- 是否符合 TDD：
- 是否达到 80% 覆盖率：
- 哪些核心逻辑达到 90%：
- 是否建议合并：
- 如果不建议合并，还缺哪些测试：
```

### 测试覆盖要求

测试设计必须覆盖以下类型，除非 Reviewer 明确说明该场景与当前代码无关：

- 正常流程。
- 异常流程。
- 边界条件。
- 权限与组织隔离。
- 并发和重复执行。
- 数据库事务与部分失败。
- 外部依赖 Mock。
- API 返回值与错误结构。
- Celery、Redis、NATS、第三方接口异常。
- Stargazer 插件参数校验、采集超时、空结果、脏数据、输出格式契约。

对于纳入范围的四个 Django app，覆盖率检查命令应优先使用项目现有 pytest / Django 测试方式，并在报告里给出可执行示例。通用示例：

```bash
cd server && uv run pytest apps/cmdb/tests apps/cmdb_enterprise/tests apps/alerts/tests apps/operation_analysis/tests --cov=apps.cmdb --cov=apps.cmdb_enterprise --cov=apps.alerts --cov=apps.operation_analysis --cov-report=term-missing --cov-fail-under=80
```

如果需要限制到某个 Django app 或测试切片，应给出更小的命令，避免要求一次跑完整后端导致反馈过慢。例如：

```bash
cd server && uv run pytest apps/cmdb/tests/test_ipam_discovery_service.py --cov=apps.cmdb --cov-report=term-missing --cov-fail-under=80
```

对于 `agents/stargazer/`，覆盖率检查命令应按其 Python/Sanic/Agent 插件框架执行，例如：

```bash
cd agents/stargazer && uv run pytest --cov=. --cov-report=term-missing --cov-fail-under=80
```

### 覆盖率不足处理

如果预计或实际覆盖率低于 80%，Reviewer 必须继续补充测试设计，并明确：

- 哪些文件没覆盖。
- 哪些函数没覆盖。
- 哪些分支没覆盖。
- 应该新增哪些测试。
- 新增测试代码是什么。

核心业务逻辑未达到 90% 时，不能给出无条件 `Approve`。如果缺口只影响非核心路径，可给 `Approve with comments`，但必须说明剩余风险和补测计划。

## 缺陷分发修复 Loop

Review Loop 可以支持“一键分发修复”，但该能力只针对 Staff Review 已确认的缺陷，不针对脚本扫描出的候选风险。候选风险必须先经过人工 Review 确认为真实缺陷，才能进入修复分发。

缺陷分发修复 Loop 的目标是把多个已确认缺陷拆成互不冲突的修复窗口，每个窗口单独走 `/fix` 流程、TDD 和验证，主窗口只负责调度、跟踪和验收。

### 分发前置条件

只有满足以下条件的 finding 才能分发修复：

- 来源于 full Staff Review 结论，不是 quick loop 的未确认候选。
- 严重级别为 `Critical`、`Security`、明确会导致 bug 的 `Major`，或用户明确要求修复的 finding。
- finding 已包含文件路径、行号、触发场景、危险原因、修复方向和测试建议。
- finding 不依赖未确认的产品决策或外部信息。

不允许自动分发：

- 证据不足的“待确认风险”。
- 纯风格建议。
- P2/P3 抽样发现但未确认影响的可维护性问题。
- 需要产品取舍或架构取舍的开放问题。

### 分组与并发规则

分发前必须按文件冲突和业务链路分组：

- 同一文件、同一 service、同一 view/service/task/nats 链路的缺陷必须进入同一个修复窗口。
- 同一 Django app 内共享模型、迁移、权限上下文的缺陷，默认不并发。
- Stargazer 同一插件或同一 NATS handler 相关缺陷，默认不并发。
- 不同 app、不同链路、无共享文件的缺陷可以并发。
- 一次最多建议创建 3 个并行修复窗口。
- P0 / Security Critical 优先于普通 Major。

主窗口必须先输出分发计划，等待用户确认后再创建修复窗口。分发计划包含：

- 将创建哪些修复窗口。
- 每个窗口处理哪些 finding。
- 涉及文件和潜在冲突。
- 每个窗口的 `/fix` prompt。
- 预计测试命令。
- 是否需要单独 worktree。

### 修复窗口要求

每个修复窗口必须是独立 Codex thread。默认建议使用 worktree，除非用户明确要求同目录修复。

每个修复窗口必须遵守：

- 必须走 `/fix` 流程。
- 只修复分配给该窗口的缺陷组。
- 先系统化调试确认根因。
- 先写失败测试。
- 再做最小业务代码修改。
- 最后运行目标测试和覆盖率检查。
- 不做无关重构。
- 不修改无关文件。
- 不扩大功能范围。
- 不自动合并或提交到主分支，除非用户明确要求。

修复窗口 prompt 模板：

```text
请按 /fix 流程修复以下已确认缺陷。

缺陷来源：
<粘贴 Review finding，包括文件、行号、触发场景、危险原因、建议修复方向>

约束：
- 只修复这个缺陷组，不处理其他问题。
- 只修改相关文件。
- 不做无关重构。
- 不扩大功能范围。
- 必须先理解现有代码和调用链。
- 必须先写失败测试。
- 测试必须覆盖正常流程、异常流程、边界条件、权限/组织隔离、事务或并发风险。
- 再做最小业务代码修改。
- 最后运行目标测试和覆盖率检查。
- 如果无法达到行覆盖率 >= 80% 或核心逻辑覆盖率 >= 90%，必须说明原因并补充测试建议。

输出：
1. 根因分析
2. 失败测试设计
3. 新增/修改的测试
4. 业务代码修改
5. 验证命令和结果
6. 覆盖率结果
7. 剩余风险
8. 是否建议合并
```

主窗口一键分发 prompt 模板：

```text
请从当前后端 full review 报告中提取已确认缺陷，按文件冲突和业务链路分组，生成多个 /fix 修复窗口的任务清单。

要求：
- 只处理 Critical、Security、明确会导致 bug 的 Major。
- P0 优先。
- 同文件或同链路缺陷合并到同一个修复窗口。
- 一次最多建议 3 个并行窗口。
- 每个窗口都必须走 /fix + TDD。
- 不要现在修改代码。
- 先输出将创建哪些缺陷窗口、每个窗口的 prompt、预计测试命令、冲突风险。
```

### 修复结果回收

主窗口在所有修复窗口完成后进行验收汇总。每个修复窗口必须回报：

- 修复摘要。
- 修改文件。
- 新增/修改测试。
- 测试命令和结果。
- 覆盖率结果。
- 是否满足 TDD。
- 是否满足行覆盖率 `>= 80%` 和核心逻辑覆盖率 `>= 90%`。
- 剩余风险。
- 是否建议合并。

主窗口必须检查：

- 是否存在跨窗口文件冲突。
- 是否有窗口未写失败测试。
- 是否有窗口未运行目标测试。
- 是否有窗口覆盖率不足且未解释。
- 是否有修复引入新 P0/P1 风险。

未满足 TDD 或验证要求的修复窗口不能标记完成。

## 报告结构

脚本生成的事实报告包含：

```md
# 后端周度代码 Review

## Review 范围
## 提交概览
## 模块热力图
## 高风险候选队列
## Staff Review 任务队列
## 建议验证命令
## Staff Review 结论
## 缺陷分发修复计划
## 修复窗口验收汇总
```

脚本只填充 `Staff Review 结论` 之前的事实部分。Agent 深审后再填充结论。缺陷分发修复计划和修复窗口验收汇总只由主窗口在用户确认后填充，不能由脚本自动生成并执行。

## 错误处理

脚本必须做到：

- 当前目录不是 git 仓库时清晰报错并退出。
- `--base` 不存在时提示用户传入有效 commit。
- 最近 7 天没有四个目标 Django app 或 `agents/stargazer/` 改动时生成空报告，明确写“本周期无后端变更”。
- git 命令失败时报告命令、退出码、stderr 摘要，不吞异常。
- 输出目录不存在时自动创建 `docs/reviews/`。
- 报告已存在时默认覆盖同名本次报告；可用 `--output` 指定路径。
- 不执行测试、不安装依赖、不联网、不改业务代码。

## 脚本测试

实现时应补最小但真实的单元测试：

- `git numstat` 解析：新增、删除、二进制文件、rename。
- 路径分类：`server/apps/cmdb/services/x.py` 能归到 `cmdb/service`。
- 风险打标：权限、NATS、Celery、migration、Stargazer plugin 能正确升权。
- 降噪规则：纯文档、纯测试新增、fixture 不误升 P0。
- 报告渲染：空 diff、正常 diff、高风险队列都能生成 Markdown。
- CLI 参数：`--days`、`--base`、`--head`、`--paths`、`--output` 行为稳定。

测试不依赖真实仓库历史，核心逻辑抽成纯函数，CLI 层只做薄封装。

## 验证命令

脚本实现后的最小验证：

```bash
python scripts/review_weekly_changes.py --days 7 --output /tmp/backend-review.md
python -m unittest discover -s tests -p 'test_review_weekly_changes*.py'
```

实际 Staff Review 报告还应列出建议运行的 `server` 和 `agents/stargazer` 模块级验证命令。

## 完成标准

脚本实现完成标准：

- 能生成最近 7 天四个目标 Django app + `agents/stargazer/` 后端事实报告。
- 能以 `--previous-day --mode quick` 生成前一天 P0/P1 候选日报。
- 能排出 P0/P1/P2/P3 深审队列。
- 能区分 Django 后端和 Stargazer 非 Django Agent 框架。
- 能通过 quick 模式限制输出体量，避免每日自动化耗尽 token。
- 脚本测试通过。
- 不误纳入其他 server app、前端和算法服务。

本周 Staff Review 完成标准：

- P0 队列全部人工深审。
- P1 队列至少按模块覆盖核心链路。
- 每个 review 单元按指定格式输出。
- 没问题的单元明确建议保持现状。
- 有问题的 finding 必须有证据、触发场景、修复建议、测试建议。
- 最终给出整体 `Approve` / `Approve with comments` / `Request changes`。

缺陷分发修复 Loop 完成标准：

- 只从 full Staff Review 已确认缺陷中提取修复项。
- 分发前已按文件冲突和业务链路分组。
- 分发前已输出修复窗口计划并获得用户确认。
- 一次并行窗口不超过 3 个。
- 每个修复窗口都使用 `/fix` 流程。
- 每个修复窗口都先写失败测试，再做最小修复。
- 每个修复窗口都回报测试命令、结果、覆盖率和剩余风险。
- 主窗口完成冲突检查和验收汇总。
- 没有通过 TDD、测试和覆盖率要求的窗口不得标记完成。
