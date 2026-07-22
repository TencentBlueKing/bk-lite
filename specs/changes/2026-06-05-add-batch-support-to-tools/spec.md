# 2026 06 05 Add Batch Support To Tools

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-batch-support-to-tools/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前 `server/apps/opspilot/metis/llm/tools/` 目录下，`fetch`、`postgres`、`jenkins`、`github`、`search` 等多个工具模块缺乏批量参数支持，LLM 在执行多目标任务时必须串行多次调用相同工具，既浪费 token 也增加延迟。此外 `postgres` 缺少多实例（multi-credential）支持，与同类 DB 工具（mysql/mssql/oracle/redis）不一致。

## What Changes

- 为 `fetch` 添加 `fetch_batch` 工具，接受 `urls: List[str]`，一次调用抓取多个 URL
- 为 `postgres` 补充多实例支持（对齐 mysql 的 `credentials` + `execute_with_credentials` 模式），并添加 `execute_safe_select_batch(queries: List[str])` 批量查询工具
- 为 `mysql`、`mssql`、`oracle` 各添加 `execute_safe_select_batch(queries: List[str])` 批量查询工具（已有多实例，只补批量参数）
- 为 `jenkins` 添加 `get_builds_batch(job_names: List[str])` 批量查询多个 Job 状态的工具
- 为 `github` 添加 `get_repos_batch(repos: List[str])` 批量查询多个仓库信息的工具
- 为 `search` 添加 `search_batch(queries: List[str])` 批量搜索工具

所有新增 batch 工具均遵循 **redis_mget 模式**：新增独立的 batch 工具函数，与现有单次调用工具并列存在，不修改原有工具签名。

## Capabilities

### New Capabilities

- `tool-batch-params`: 为 fetch / postgres / mysql / mssql / oracle / jenkins / github / search 新增批量参数工具函数（redis_mget 模式）
- `postgres-multi-instance`: postgres 工具支持多实例凭据（credentials list），对齐 mysql/mssql/oracle/redis 已有规范

### Modified Capabilities

（无现有 spec 级别行为变更）

## Impact

- `server/apps/opspilot/metis/llm/tools/fetch/fetch.py` — 新增 `fetch_batch`
- `server/apps/opspilot/metis/llm/tools/postgres/` — 重构 `utils.py` 引入 credentials adapter，新增 `execute_safe_select_batch`
- `server/apps/opspilot/metis/llm/tools/mysql/dynamic.py` — 新增 `execute_safe_select_batch`
- `server/apps/opspilot/metis/llm/tools/mssql/` — 新增 `execute_safe_select_batch`
- `server/apps/opspilot/metis/llm/tools/oracle/` — 新增 `execute_safe_select_batch`
- `server/apps/opspilot/metis/llm/tools/jenkins/` — 新增 `get_builds_batch`
- `server/apps/opspilot/metis/llm/tools/github/` — 新增 `get_repos_batch`
- `server/apps/opspilot/metis/llm/tools/search/` — 新增 `search_batch`
- `server/apps/opspilot/metis/llm/tools/common/credentials.py` — 无需修改，已支持通用模式
- 无新增外部依赖
- 无 API 变更，向后兼容

## Implementation Decisions

## Context

`server/apps/opspilot/metis/llm/tools/` 是 OpsPilot LLM Agent 的工具层。每个工具是一个 LangChain `@tool` 装饰的函数，参数由 Python 签名自动生成 JSON Schema，供 LLM 调用。

当前工具调用模型是**单次单操作**：每次调用只处理一个目标（一个 URL、一条 SQL、一个 Jenkins Job）。当 Agent 需要并行处理多个目标时，必须串行多次调用，浪费 token 并增加响应延迟。

参考实现：
- `redis/string.py` 中 `redis_get`（单）与 `redis_mget`（批量 keys: List[str]）并列
- `common/credentials.py` 中 `execute_with_credentials` 已实现通用多实例执行循环
- `mysql/connection.py` 中完整的 `CredentialAdapter + build_*_normalized_from_runnable` 模式

postgres 额外问题：`utils.py` 使用旧式 `prepare_context()` 直接读 flat configurable 字段，无法支持 `credentials` list，与其他 DB 工具不一致。

## Goals / Non-Goals

**Goals:**
- 为 fetch / mysql / mssql / oracle / postgres / jenkins / github / search 新增 batch 工具函数
- postgres 工具引入与 mysql 一致的 `CredentialAdapter` + `build_postgres_normalized_from_runnable` 模式
- 所有新 batch 工具遵循统一的"redis_mget 模式"：独立函数，不修改原有工具
- 向后完全兼容，原有单次工具函数签名不变

**Non-Goals:**
- 不修改 `agent_browser`、`browser_use`、`date`、`python`（无批量场景）
- 不修改 `shell`、`ssh`、`kubernetes`、`elasticsearch`、`monitor`（已有批量支持）
- 不引入并发/异步执行（batch 函数内部顺序执行，返回结果列表）
- 不修改 `tools_loader.py`（新工具自动被 `inspect.getmembers` 发现）

## Decisions

### D1：批量函数模式 — 独立工具函数（redis_mget 模式）

**选择**：每个需要批量的工具，新增一个独立的 `xxx_batch` 函数，接受 List 参数，内部循环执行单次逻辑，返回结果列表。

**对比方案**：
- 方案A（选用）— 独立 batch 函数：LLM 能明确区分单次与批量语义；不改原函数签名；每个结果可单独标注 ok/error
- 方案B — 原参数改为 `Union[str, List[str]]`：签名模糊，LLM 理解困难；向后兼容风险高
- 方案C — 通用 batch 装饰器：工程复杂，LangChain tool schema 生成不可控

**返回格式统一**：
```python
{
  "total": N,
  "succeeded": N,
  "failed": N,
  "results": [
    {"input": <原始输入>, "ok": True, "data": <结果>},
    {"input": <原始输入>, "ok": False, "error": "<错误信息>"}
  ]
}
```

---

### D2：postgres 多实例改造 — 新增 connection.py，不替换 utils.py

**选择**：新增 `postgres/connection.py`，实现 `PostgresCredentialAdapter` 和 `build_postgres_normalized_from_runnable`，与 mysql/connection.py 对称。`utils.py` 中原有的 `prepare_context / get_db_connection / execute_readonly_query` 保留不变（向后兼容），新批量工具使用新连接层。

**对比**：直接重构 utils.py 会影响现有所有 postgres 工具函数，风险高且改动量大。新增 connection.py 是增量变更，现有工具零影响。

**postgres 凭据字段**：对齐 mysql adapter 模式，flat fields = `[host, port, database, user, password]`，instance 字段同 `prepare_context` 现有字段名。

---

### D3：fetch_batch 实现 — 复用现有 _http_get_impl

**选择**：`fetch_batch(urls: List[str], format: Literal["html","txt","markdown","json"] = "txt")` 复用 `_http_get_impl`，顺序请求每个 URL，返回统一 batch 结果格式。format 参数控制内容转换类型，避免为每种 fetch 类型各建一个 batch 函数（4个→1个）。

---

### D4：DB batch 工具 — execute_safe_select_batch(queries: List[str])

**选择**：仅提供 `execute_safe_select_batch`（批量 SELECT），不提供通用写操作批量。原因：写操作批量风险高，且当前单次工具已禁止写操作。每条 query 独立走现有 `validate_sql_safety` 检查，结果按 D1 格式返回。

---

### D5：jenkins / github / search batch — 最小化实现

- `jenkins_get_builds_batch(job_names: List[str])` — 内部循环调用现有 Jenkins API 查询逻辑
- `github_get_repos_batch(repos: List[str])` — 内部循环调用现有 GitHub API 查询逻辑（格式：`owner/repo`）
- `search_batch(queries: List[str])` — 内部循环调用现有 DuckDuckGo 查询逻辑

三者均不引入并发，顺序执行，单个失败不中断整体。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| postgres connection.py 与 utils.py 并存，未来维护两套连接逻辑 | 在代码注释中标注"新工具使用 connection.py，旧工具继续用 utils.py"；待全量迁移后统一 |
| batch 函数顺序执行，N 个 URL / query 延迟叠加 | 明确在工具 docstring 中说明顺序执行语义；当前场景 N 通常 < 10，可接受 |
| LLM 可能混用单次和批量工具（重复调用） | batch 工具 docstring 明确标注"当需要同时处理多个目标时使用" |
| postgres adapter 字段名与现有 utils.py prepare_context 字段名不一致 | adapter 使用与 prepare_context 完全相同的字段名（host/port/database/user/password） |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-27
```

## Capability Deltas

### postgres-multi-instance

## ADDED Requirements

### Requirement: postgres 工具支持多实例配置

postgres 工具模块 SHALL 支持通过 `credentials` 列表配置多个 PostgreSQL 实例，对齐 mysql / mssql / oracle / redis 已有的多实例协议。

#### Scenario: 配置多个 postgres 实例

- **WHEN** 用户通过 `credentials` 字段配置多个 PostgreSQL 实例列表
- **THEN** 系统 SHALL 解析每个实例的 `host`、`port`、`database`、`user`、`password` 字段
- **AND** 每个实例 SHALL 可选提供 `name` 字段作为显示名称

#### Scenario: 未配置 credentials 时使用平铺字段

- **WHEN** 用户未提供 `credentials` 列表，而是通过平铺字段（host / port / database / user / password）提供连接信息
- **THEN** 系统 SHALL 将其视为旧式单实例配置并正常建立连接
- **AND** 现有 postgres 工具的行为 SHALL 完全不变

#### Scenario: credentials 与平铺字段同时存在时报错

- **WHEN** 用户同时提供 `credentials` 列表和平铺字段
- **THEN** 系统 SHALL 抛出 `CredentialConflictError`
- **AND** 系统 SHALL 不得执行任何数据库操作

### Requirement: postgres 工具运行时支持实例选择

postgres 工具 SHALL 在多实例配置下支持通过参数指定目标实例或对所有实例批量执行。

#### Scenario: 未显式指定实例时执行（单实例配置）

- **WHEN** 仅配置一个 PostgreSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 使用该唯一实例建立连接
- **AND** 返回结果 SHALL 为单实例格式（不包装聚合结构）

#### Scenario: 未显式指定实例时执行（多实例配置）

- **WHEN** 配置多个 PostgreSQL 实例且工具调用未提供实例标识
- **THEN** 系统 SHALL 对所有已配置实例批量执行该工具
- **AND** 返回结果 SHALL 为聚合格式，包含 `mode`、`total`、`succeeded`、`failed`、`results` 字段

#### Scenario: 显式指定实例时执行

- **WHEN** 工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 PostgreSQL 实例并仅使用该实例建立连接
- **AND** 返回结果 SHALL 为单实例格式

#### Scenario: 指定实例不存在

- **WHEN** 工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误信息
- **AND** 系统 SHALL 不得静默回退到其他实例

### Requirement: postgres 多实例改造不破坏现有工具函数

postgres 工具模块 SHALL 通过新增 `connection.py` 实现多实例支持，原有 `utils.py` 中的 `prepare_context / get_db_connection / execute_readonly_query` 函数 SHALL 保持不变，现有工具函数继续正常工作。

#### Scenario: 现有 postgres 工具在旧式配置下正常工作

- **WHEN** 使用旧式平铺字段配置的 postgres 工具被调用
- **THEN** 系统 SHALL 通过 `utils.py` 的 `prepare_context` 正常建立连接
- **AND** 工具返回结果 SHALL 与改造前完全一致

#### Scenario: 新 batch 工具使用新连接层

- **WHEN** 调用 `execute_safe_select_batch` 等新增 batch 工具
- **THEN** 系统 SHALL 通过 `connection.py` 的 `build_postgres_normalized_from_runnable` 获取连接配置
- **AND** 单实例和多实例路径 SHALL 均正确工作

### Requirement: postgres 多实例执行中单个实例失败不影响其他实例

postgres 工具在多实例批量执行模式下 SHALL 保证单个实例的失败不阻断其他实例。

#### Scenario: 部分实例连接失败

- **WHEN** 批量执行时某个 postgres 实例连接超时或认证失败
- **THEN** 系统 SHALL 在该实例结果中标记 `ok: false` 并记录错误信息
- **AND** 系统 SHALL 继续对剩余实例执行工具
- **AND** 聚合结果中 `failed` 字段 SHALL 正确反映失败数量

### tool-batch-params

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

## Work Checklist

## 1. postgres 多实例支持（新增 connection.py）

- [x] 1.1 在 `postgres/` 目录新建 `connection.py`，实现 `PostgresCredentialAdapter`（flat_fields = host/port/database/user/password）
- [x] 1.2 在 `connection.py` 实现 `build_postgres_config_from_item(item)` 函数，从 CredentialItem 构建 psycopg2 连接参数字典
- [x] 1.3 在 `connection.py` 实现 `build_postgres_normalized_from_runnable(config, instance_name, instance_id)` 函数，对齐 `build_mysql_normalized_from_runnable` 的逻辑
- [x] 1.4 在 `connection.py` 实现 `get_postgres_connection_from_item(item)` 函数，返回 psycopg2 连接对象（使用 RealDictCursor）
- [x] 1.5 确认 `utils.py` 中原有 `prepare_context / get_db_connection / execute_readonly_query` 函数保持不变，不修改任何现有 postgres 工具文件

## 2. fetch 批量工具

- [x] 2.1 在 `fetch/fetch.py` 新增 `fetch_batch` 工具函数，参数：`urls: List[str]`，`format: Literal["html","txt","markdown","json"] = "txt"`，`max_length: Optional[int] = None`，`bearer_token: Optional[str] = None`，`config: RunnableConfig = None`
- [x] 2.2 实现内部循环逻辑：顺序调用 `_http_get_impl` 并按 format 参数转换内容，单个失败不中断循环
- [x] 2.3 返回统一 batch 格式：`{"total": N, "succeeded": N, "failed": N, "results": [{"input": url, "ok": bool, "data": ..., "error": ...}]}`

## 3. mysql 批量查询工具

- [x] 3.1 在 `mysql/dynamic.py` 新增 `execute_safe_select_batch` 工具函数，参数：`queries: List[str]`，`database: str = None`，`instance_name: str = None`，`instance_id: str = None`，`config: RunnableConfig = None`
- [x] 3.2 实现内部循环：每条 query 独立调用 `validate_sql_safety()`，通过后在只读事务中执行，单条失败不中断
- [x] 3.3 返回统一 batch 格式，每项 `input` 为原始 SQL 语句

## 4. mssql 批量查询工具

- [x] 4.1 查阅 `mssql/` 目录下现有动态查询工具的文件名和安全校验函数
- [x] 4.2 在对应文件新增 `execute_safe_select_batch` 工具函数，逻辑与 mysql 版本对称
- [x] 4.3 确保使用 mssql 现有的 `build_mssql_normalized_from_runnable` 和连接工具函数

## 5. oracle 批量查询工具

- [x] 5.1 查阅 `oracle/` 目录下现有动态查询工具的文件名和安全校验函数
- [x] 5.2 在对应文件新增 `execute_safe_select_batch` 工具函数，逻辑与 mysql 版本对称
- [x] 5.3 确保使用 oracle 现有的 `build_oracle_normalized_from_runnable` 和连接工具函数

## 6. postgres 批量查询工具

- [x] 6.1 在 `postgres/dynamic.py` 新增 `execute_safe_select_batch` 工具函数
- [x] 6.2 使用第 1 阶段新增的 `build_postgres_normalized_from_runnable` 和 `get_postgres_connection_from_item`
- [x] 6.3 复用 `postgres/dynamic.py` 现有的 SQL 安全校验逻辑，确保每条 query 独立检查

## 7. jenkins 批量工具

- [x] 7.1 在 `jenkins/build.py` 新增 `get_jenkins_job_info_batch` 工具函数，参数：`job_names: List[str]`，`config: RunnableConfig = None`
- [x] 7.2 实现内部循环：复用 `get_client(config)` 获取客户端，逐个调用 `client.get_job_info(job_name)` 获取 Job 信息
- [x] 7.3 Job 不存在时捕获异常，标记该项 `ok: false`，继续处理剩余 Job
- [x] 7.4 返回统一 batch 格式，每项 `input` 为 job_name

## 8. github 批量工具

- [x] 8.1 在 `github/commits.py` 新增 `get_github_commits_batch` 工具函数，参数：`repos: List[Dict]`（每项含 owner/repo），`since: str`，`until: str`，`token: Optional[str] = None`
- [x] 8.2 实现格式验证：复用 `_validate_datetime_format`
- [x] 8.3 实现内部循环：复用 `_fetch_github_commits` 逐个查询，单个失败不中断
- [x] 8.4 返回统一 batch 格式，每项 `input` 为 `owner/repo` 字符串

## 9. search 批量工具

- [x] 9.1 在 `search/duckduckgo.py` 新增 `duckduckgo_search_batch` 工具函数，参数：`queries: List[str]`，`max_results: Optional[int] = 5`，`config: RunnableConfig = None`
- [x] 9.2 实现内部循环：复用 DDGS 客户端逐个执行搜索，单个失败不中断
- [x] 9.3 返回统一 batch 格式，每项 `input` 为搜索关键词，`data` 为结构化结果列表

## 10. 验证与收尾

- [x] 10.1 在 `server/` 目录执行 `make test`，确认所有现有测试通过
- [x] 10.2 逐个确认新增工具函数被 `tools_loader._extract_tools_from_module` 自动发现（通过 `get_all_tools_metadata()` 返回列表验证）
- [x] 10.3 确认 `postgres/connection.py` 新增后，`tools_loader.py` 中 postgres 条目 `enable_extra_prompt` 可酌情改为 `True`（对齐其他 DB 工具）
