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
