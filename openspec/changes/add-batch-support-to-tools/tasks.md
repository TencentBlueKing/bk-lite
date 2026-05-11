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

- [ ] 10.1 在 `server/` 目录执行 `make test`，确认所有现有测试通过
- [ ] 10.2 逐个确认新增工具函数被 `tools_loader._extract_tools_from_module` 自动发现（通过 `get_all_tools_metadata()` 返回列表验证）
- [ ] 10.3 确认 `postgres/connection.py` 新增后，`tools_loader.py` 中 postgres 条目 `enable_extra_prompt` 可酌情改为 `True`（对齐其他 DB 工具）
