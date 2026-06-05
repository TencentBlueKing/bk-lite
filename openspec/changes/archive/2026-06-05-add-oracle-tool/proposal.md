## Why

OpsPilot already supports MySQL and Redis as built-in database tools for LLM-driven operations. Oracle Database is a critical enterprise RDBMS used extensively in production environments. Adding Oracle tool support enables OpsPilot to provide the same multi-instance, LLM-driven diagnostic and monitoring capabilities for Oracle databases, completing the core database tool coverage.

## What Changes

- Add 25 Oracle-specific LLM tools organized into 5 categories: resource discovery (7), dynamic query (3), fault diagnosis (5), runtime monitoring (6), optimization advice (4)
- Add `oracledb` (python-oracledb) dependency using Thin mode (pure Python, no Oracle Client required)
- Register Oracle as a built-in tool (id=-3) with multi-instance support and `enable_extra_prompt=True`
- Add Oracle connection management with host + port + service_name connection mode
- Add frontend Oracle tool editor for multi-instance configuration
- Add Oracle branch in tool selector, API test connection endpoint, and i18n strings

## Capabilities

### New Capabilities
- `oracle-tool-multi-instance`: Oracle database LLM tool set with multi-instance support, 25 tools covering resource discovery, dynamic query, fault diagnosis, runtime monitoring, and optimization advice. Mirrors the MySQL tool architecture (connection management, credential framework, built-in tool registration, batch inspection mode).

### Modified Capabilities
- `mysql-tool-multi-instance`: No requirement changes — referenced as template only.

## Impact

- **Backend**: New `server/apps/opspilot/metis/llm/tools/oracle/` package (~9 files), changes to `tools_loader.py`, `builtin_tools.py`, `chat_service.py`, `llm_view.py`
- **Frontend**: New `oracleToolEditor.tsx`, changes to `toolSelector.tsx`, `skill.ts` API, `zh.json`/`en.json` i18n
- **Dependencies**: `oracledb` added to `server/pyproject.toml`
- **Database**: New built-in tool record (id=-3) created via migration or runtime seeding
