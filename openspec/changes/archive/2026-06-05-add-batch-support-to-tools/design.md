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
