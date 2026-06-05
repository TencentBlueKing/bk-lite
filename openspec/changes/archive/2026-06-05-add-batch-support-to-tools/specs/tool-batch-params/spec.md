## ADDED Requirements

### Requirement: 批量工具函数与单次工具函数并列存在

每个支持批量操作的工具模块 SHALL 提供一个独立的 batch 工具函数，与现有单次工具函数并列，不修改原有函数签名。

#### Scenario: batch 工具函数可被正常加载

- **WHEN** `tools_loader` 加载对应工具模块（fetch / mysql / mssql / oracle / postgres / jenkins / github / search）
- **THEN** 系统 SHALL 同时发现并注册单次工具函数和对应的 batch 工具函数
- **AND** 原有单次工具函数的名称、参数、行为 SHALL 保持不变

### Requirement: fetch_batch 支持批量抓取多个 URL

fetch 工具模块 SHALL 提供 `fetch_batch` 工具，接受多个 URL 和统一格式参数，一次调用返回所有 URL 的抓取结果。

#### Scenario: 批量抓取多个 URL

- **WHEN** 调用 `fetch_batch(urls=["url1","url2"], format="txt")`
- **THEN** 系统 SHALL 顺序请求每个 URL
- **AND** 返回结果 SHALL 包含 `total`、`succeeded`、`failed`、`results` 字段
- **AND** `results` 中每项 SHALL 包含 `input`（原始 URL）、`ok`（bool）、`data` 或 `error` 字段

#### Scenario: 单个 URL 失败不中断其他 URL

- **WHEN** `fetch_batch` 中某个 URL 请求失败（网络错误或非 2xx）
- **THEN** 该项结果 SHALL 标记 `ok: false` 并记录 `error` 信息
- **AND** 系统 SHALL 继续处理剩余 URL
- **AND** 最终 `failed` 计数 SHALL 正确反映失败数量

#### Scenario: format 参数控制内容格式

- **WHEN** 调用 `fetch_batch` 时指定 `format` 参数（html / txt / markdown / json 之一）
- **THEN** 每个成功抓取的 URL 内容 SHALL 按指定格式转换后返回
- **AND** `format` 默认值 SHALL 为 `txt`

### Requirement: DB 工具支持批量 SELECT 查询

mysql / mssql / oracle / postgres 工具模块 SHALL 各自提供 `execute_safe_select_batch` 工具，接受多条 SQL 语句列表，一次调用返回所有查询结果。

#### Scenario: 批量执行多条 SELECT

- **WHEN** 调用 `execute_safe_select_batch(queries=["SELECT ...", "SELECT ..."])`
- **THEN** 系统 SHALL 对每条 SQL 独立执行 `validate_sql_safety()` 检查
- **AND** 每条 SQL SHALL 在只读事务中执行
- **AND** 返回格式 SHALL 遵循统一 batch 结果格式（total / succeeded / failed / results）

#### Scenario: 危险 SQL 在批量中被单独拦截

- **WHEN** `execute_safe_select_batch` 的 queries 列表中包含含有 `DROP`/`ALTER` 等禁止关键词的 SQL
- **THEN** 该条 SQL SHALL 被拒绝执行，结果标记 `ok: false`
- **AND** 系统 SHALL 继续执行列表中其余合法 SQL
- **AND** 危险 SQL SHALL 不被发送到数据库

#### Scenario: 单条查询失败不中断批量

- **WHEN** `execute_safe_select_batch` 执行过程中某条 SQL 抛出数据库异常
- **THEN** 该条结果 SHALL 标记 `ok: false` 并记录错误信息
- **AND** 系统 SHALL 继续执行剩余 SQL

### Requirement: jenkins_get_builds_batch 支持批量查询多个 Job

jenkins 工具模块 SHALL 提供 `jenkins_get_builds_batch` 工具，接受多个 Job 名称，一次调用返回所有 Job 的构建状态。

#### Scenario: 批量查询多个 Job 构建状态

- **WHEN** 调用 `jenkins_get_builds_batch(job_names=["job-a", "job-b"])`
- **THEN** 系统 SHALL 顺序查询每个 Job 的最近构建信息
- **AND** 返回格式 SHALL 遵循统一 batch 结果格式
- **AND** `results` 中每项的 `input` SHALL 为对应的 job 名称

#### Scenario: Job 不存在时单独标记失败

- **WHEN** `jenkins_get_builds_batch` 中某个 job_name 在 Jenkins 中不存在
- **THEN** 该项结果 SHALL 标记 `ok: false`
- **AND** 系统 SHALL 继续查询剩余 Job

### Requirement: github_get_repos_batch 支持批量查询多个仓库

github 工具模块 SHALL 提供 `github_get_repos_batch` 工具，接受多个仓库标识（`owner/repo` 格式），一次调用返回所有仓库信息。

#### Scenario: 批量查询多个仓库

- **WHEN** 调用 `github_get_repos_batch(repos=["owner/repo-a", "owner/repo-b"])`
- **THEN** 系统 SHALL 顺序查询每个仓库信息
- **AND** 返回格式 SHALL 遵循统一 batch 结果格式
- **AND** `results` 中每项的 `input` SHALL 为对应的 `owner/repo` 字符串

#### Scenario: 仓库格式错误时单独标记失败

- **WHEN** `github_get_repos_batch` 中某个 repo 字符串不符合 `owner/repo` 格式
- **THEN** 该项结果 SHALL 标记 `ok: false` 并记录格式错误信息
- **AND** 系统 SHALL 继续查询剩余格式正确的仓库

### Requirement: search_batch 支持批量搜索多个关键词

search 工具模块 SHALL 提供 `search_batch` 工具，接受多个搜索关键词，一次调用返回所有关键词的搜索结果。

#### Scenario: 批量搜索多个关键词

- **WHEN** 调用 `search_batch(queries=["keyword-a", "keyword-b"])`
- **THEN** 系统 SHALL 顺序执行每个关键词的 DuckDuckGo 搜索
- **AND** 返回格式 SHALL 遵循统一 batch 结果格式
- **AND** `results` 中每项的 `input` SHALL 为对应的搜索关键词

#### Scenario: 单个关键词搜索失败不中断批量

- **WHEN** `search_batch` 某个关键词因网络或 API 限制失败
- **THEN** 该项结果 SHALL 标记 `ok: false`
- **AND** 系统 SHALL 继续执行剩余关键词搜索

### Requirement: 批量结果格式统一

所有 batch 工具函数 SHALL 返回统一结构的聚合结果，便于 LLM 解析。

#### Scenario: 全部成功时的返回格式

- **WHEN** batch 工具所有输入项均执行成功
- **THEN** 返回结果 SHALL 包含 `total`、`succeeded`（等于 total）、`failed`（为 0）、`results` 字段
- **AND** `results` 中每项 SHALL 包含 `input`、`ok: true`、`data` 字段

#### Scenario: 部分失败时的返回格式

- **WHEN** batch 工具部分输入项执行失败
- **THEN** `succeeded + failed` SHALL 等于 `total`
- **AND** 失败项 SHALL 包含 `ok: false` 和 `error` 字段（无 `data` 字段）
- **AND** 成功项 SHALL 包含 `ok: true` 和 `data` 字段（无 `error` 字段）
