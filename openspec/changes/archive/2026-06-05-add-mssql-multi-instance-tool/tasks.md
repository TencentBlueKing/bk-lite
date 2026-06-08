## 1. Backend Connection Module

- [x] 1.1 Create `server/apps/opspilot/metis/llm/tools/mssql/connection.py` — implement `MSSQL_INSTANCE_FIELDS`, `normalize_mssql_instance()`, `parse_mssql_instances()`, `get_mssql_instances_from_configurable()`, `resolve_mssql_instance()`, `test_mssql_instance()`, `get_mssql_instances_prompt()`, legacy flat-field compatibility
- [x] 1.2 Update `server/apps/opspilot/metis/llm/tools/mssql/__init__.py` — change CONSTRUCTOR_PARAMS from flat fields to `mssql_instances` + `mssql_default_instance_id`
- [x] 1.3 Update `server/apps/opspilot/metis/llm/tools/mssql/utils.py` — modify `prepare_context()` / `get_db_connection()` to use multi-instance resolution via `connection.py`

## 2. Backend Registration & Integration

- [x] 2.1 Update `server/apps/opspilot/services/builtin_tools.py` — add `BUILTIN_MSSQL_TOOL_ID = -4`, `BUILTIN_MSSQL_TOOL_NAME = "mssql"`, `build_builtin_mssql_tool()`, `build_builtin_mssql_runtime_tool()`
- [x] 2.2 Update `server/apps/opspilot/services/chat_service.py` — add MSSQL built-in tool name matching branch
- [x] 2.3 Update `server/apps/opspilot/viewsets/llm_view.py` — add `test_mssql_connection` endpoint and include MSSQL in tool list API
- [x] 2.4 Update `server/apps/opspilot/metis/llm/tools/tools_loader.py` — set `enable_extra_prompt=True` for mssql module

## 3. Frontend Editor Component

- [x] 3.1 Create `web/src/app/opspilot/components/skill/mssqlToolEditor.tsx` — multi-instance editor with left panel (instance list + add button) and right panel (name, host, port, database, user, password fields + test status badge)
- [x] 3.2 Update `web/src/app/opspilot/components/skill/toolSelector.tsx` — add `isMssqlTool()`, `parseMssqlToolConfig()`, `serializeMssqlToolConfig()`, `getDefaultMssqlInstance()`, `getNextMssqlInstanceName()`, state hooks, event handlers, and modal integration
- [x] 3.3 Update `web/src/app/opspilot/api/skill.ts` — add `testMssqlConnection` API function

## 4. Localization

- [x] 4.1 Update `web/src/app/opspilot/locales/zh.json` — add `tool.mssql.*` section (host, port, database, user, password, instance name, status labels, test connection, etc.)
- [x] 4.2 Update `web/src/app/opspilot/locales/en.json` — add corresponding English `tool.mssql.*` keys

## 5. Verification

- [x] 5.1 Run `cd server && make test` to verify no backend regressions
- [x] 5.2 Run `cd web && pnpm lint && pnpm type-check` to verify frontend compiles
