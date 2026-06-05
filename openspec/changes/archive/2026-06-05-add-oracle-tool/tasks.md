## 1. Dependencies & Project Setup

- [x] 1.1 Add `oracledb` to `server/pyproject.toml` dependencies
- [x] 1.2 Create `server/apps/opspilot/metis/llm/tools/oracle/` package directory with `__init__.py`

## 2. Oracle Connection & Utilities

- [x] 2.1 Create `oracle/connection.py` — OracleConnectionManager (multi-instance, Thin mode, host+port+service_name), `get_oracle_instances_prompt()`, `test_oracle_connection()`
- [x] 2.2 Create `oracle/utils.py` — SQL safety validation (Oracle deny list), result formatting, error handling helpers

## 3. Oracle Tools Implementation (25 tools)

- [x] 3.1 Create `oracle/resources.py` — 7 resource discovery tools (get_current_database_info, list_oracle_tablespaces, list_oracle_tables, list_oracle_indexes, get_table_structure, list_oracle_users, get_database_config)
- [x] 3.2 Create `oracle/dynamic_queries.py` — 3 dynamic query tools (search_tables_by_keyword, execute_safe_select, explain_query_plan)
- [x] 3.3 Create `oracle/diagnostics.py` — 5 fault diagnosis tools (diagnose_slow_queries, diagnose_lock_conflicts, diagnose_connection_issues, check_database_health, check_dataguard_status)
- [x] 3.4 Create `oracle/monitoring.py` — 6 runtime monitoring tools (get_database_metrics, get_table_metrics, get_sga_pga_stats, get_io_stats, check_redo_log_status, get_processlist)
- [x] 3.5 Create `oracle/optimization.py` — 4 optimization advice tools (check_tablespace_usage, check_unused_indexes, check_table_fragmentation, check_configuration_tuning)

## 4. Backend Registration & Integration

- [x] 4.1 Update `tools_loader.py` — Add oracle to TOOL_MODULES with `enable_extra_prompt=True`
- [x] 4.2 Update `builtin_tools.py` — Add Oracle built-in tool definition (id=-3, BUILTIN_ORACLE_TOOL_NAME)
- [x] 4.3 Update `chat_service.py` — Add Oracle built-in tool name matching branch
- [x] 4.4 Update `llm_view.py` — Add Oracle to tool list API and add `test_oracle_connection` endpoint

## 5. Frontend Implementation

- [x] 5.1 Create `oracleToolEditor.tsx` — Multi-instance editor component (name, host, port, service_name, user, password, nls_lang fields)
- [x] 5.2 Update `toolSelector.tsx` — Add Oracle tool detection and editor routing
- [x] 5.3 Update `api/skill.ts` — Add `testOracleConnection` API function
- [x] 5.4 Update `zh.json` and `en.json` — Add `tool.oracle.*` i18n strings

## 6. Verification

- [x] 6.1 Run `cd server && make test` to verify no regressions
- [x] 6.2 Run `cd web && pnpm lint && pnpm type-check` to verify frontend compiles
