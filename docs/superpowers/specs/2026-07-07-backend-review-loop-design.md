# 后端周度代码 Review Loop 设计

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

- `server/`：按 Python/Django Staff Engineer 标准 Review。
- `agents/stargazer/`：按 Python/Sanic/Agent 插件框架标准 Review，不套 Django/DRF/ORM 规则。

排除：

- `web/`
- `mobile/`
- `webchat/`
- `algorithms/`
- 其他与后端 Review Loop 无关的路径

默认时间窗口为最近 7 天。脚本应支持通过参数覆盖时间窗口、base/head commit 和输出路径。

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
- 只纳入 `server/` 和 `agents/stargazer/`。
- 生成 Markdown 报告到 `docs/reviews/YYYY-MM-DD-backend-weekly-code-review.md`。

建议参数：

- `--days 7`
- `--since YYYY-MM-DD`
- `--until YYYY-MM-DD`
- `--base <commit>`
- `--head <commit>`
- `--paths server agents/stargazer`
- `--output <path>`

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

`server/` 的聚类规则：

- `server/apps/<app_name>/views`、`viewsets`：API 入口。
- `server/apps/<app_name>/serializers`：输入输出校验。
- `server/apps/<app_name>/services`：业务规则。
- `server/apps/<app_name>/tasks`：异步任务。
- `server/apps/<app_name>/nats`：消息入口。
- `server/apps/<app_name>/models`：数据模型。
- `server/apps/<app_name>/migrations`：schema 变更。
- `server/apps/core`、`server/apps/base`、`server/config`、`server/apps/*/db_patches`：核心基础能力或数据库兼容。

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
```

脚本只填充 `Staff Review 结论` 之前的事实部分。Agent 深审后再填充结论。

## 错误处理

脚本必须做到：

- 当前目录不是 git 仓库时清晰报错并退出。
- `--base` 不存在时提示用户传入有效 commit。
- 最近 7 天没有 `server/` 或 `agents/stargazer/` 改动时生成空报告，明确写“本周期无后端变更”。
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

- 能生成最近 7 天 `server/` + `agents/stargazer/` 后端事实报告。
- 能排出 P0/P1/P2/P3 深审队列。
- 能区分 Django 后端和 Stargazer 非 Django Agent 框架。
- 脚本测试通过。
- 不误纳入前端和算法服务。

本周 Staff Review 完成标准：

- P0 队列全部人工深审。
- P1 队列至少按模块覆盖核心链路。
- 每个 review 单元按指定格式输出。
- 没问题的单元明确建议保持现状。
- 有问题的 finding 必须有证据、触发场景、修复建议、测试建议。
- 最终给出整体 `Approve` / `Approve with comments` / `Request changes`。
