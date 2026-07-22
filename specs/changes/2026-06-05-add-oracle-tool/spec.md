# 2026 06 05 Add Oracle Tool

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-oracle-tool/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

OpsPilot has an established pattern for built-in database tools: MySQL (id=-2, 35 tools, 9 files) and Redis (id=-1). Both use multi-instance architecture with credential management, `enable_extra_prompt=True` for LLM instance injection, and dedicated frontend editors. Oracle follows this exact pattern.

Key constraint: Oracle is single-database-multi-schema (unlike MySQL's multi-database). Data dictionary uses `v$` views and `dba_/all_/user_` views instead of `information_schema`. Memory model is SGA+PGA, logging is Redo+Archive, replication is Data Guard.

## Goals / Non-Goals

**Goals:**
- 25 Oracle tools covering resource discovery, dynamic query, fault diagnosis, monitoring, optimization
- Multi-instance support with batch inspection mode
- `oracledb` Thin mode — pure Python, no Oracle Client installation required
- Connection via host + port + service_name only
- Built-in tool registration (id=-3) with frontend editor

**Non-Goals:**
- SID, TNS, or full DSN connection modes
- DBA write operations (ALTER SYSTEM, SHUTDOWN, etc.)
- Oracle RAC cluster-aware tooling
- Performance parity with MySQL tool count (25 vs 35 — intentional to manage token budget)

## Decisions

### 1. Driver: `oracledb` Thin mode
- **Why**: Pure Python, no Oracle Instant Client dependency. Simplifies Docker builds and dev setup.
- **Alternative**: `cx_Oracle` — requires native Oracle Client libraries, heavier dependency.

### 2. Connection: host + port + service_name only
- **Why**: Most common modern Oracle deployment pattern. SID is deprecated. TNS/DSN adds complexity without broad benefit.
- **Alternative**: Support all connection modes — adds config complexity for edge cases.

### 3. 25 tools (not 35 like MySQL)
- **Why**: Oracle's data dictionary queries are more verbose (more token usage per tool). 25 tools keeps total token budget manageable while covering all essential DBA operations.

### 4. File structure mirrors MySQL exactly
- 9 files: `__init__.py`, `connection.py`, `utils.py`, `resources.py`, `dynamic_queries.py`, `diagnostics.py`, `monitoring.py`, `optimization.py`, `analysis.py`
- **Why**: Consistency reduces onboarding cost and makes the pattern predictable.

### 5. SQL safety: Oracle-specific deny list
- Blocked keywords: `ALTER SYSTEM`, `ALTER DATABASE`, `CREATE TABLESPACE`, `DROP TABLESPACE`, `SHUTDOWN`, `STARTUP`, `GRANT`, `REVOKE`, `CREATE USER`, `DROP USER`, `TRUNCATE`, `DELETE`, `UPDATE`, `INSERT`, `MERGE`
- Read-only enforcement via `SET TRANSACTION READ ONLY` before user-submitted SELECT queries.

## Risks / Trade-offs

- [Risk] Oracle permissions vary by deployment — some `v$` and `dba_` views may be inaccessible → Tools return clear error messages indicating missing privileges rather than failing silently.
- [Risk] Thin mode doesn't support all Oracle features (e.g., Advanced Queuing, LDAP) → Non-goal for this scope; Thin mode covers all read-only diagnostic needs.
- [Risk] Token budget with 25 tools may still be tight for some LLMs → Tool descriptions kept concise; batch inspection prompt tested during MySQL work.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-21
```

## Capability Deltas

### oracle-tool-multi-instance

## ADDED Requirements

### Requirement: Oracle connection management
The system SHALL connect to Oracle databases using `oracledb` in Thin mode via host + port + service_name. The system SHALL support multiple named Oracle instances per built-in tool configuration. Each instance SHALL have fields: name, host, port, service_name, user, password, nls_lang (optional). The system SHALL designate one instance as default.

#### Scenario: Successful connection with default instance
- **WHEN** user invokes any Oracle tool without specifying an instance
- **THEN** the system connects using the default instance configuration and executes the tool

#### Scenario: Connection with named instance
- **WHEN** user invokes an Oracle tool with `instance_name` parameter
- **THEN** the system connects using the matching named instance configuration

#### Scenario: Connection failure
- **WHEN** the Oracle database is unreachable or credentials are invalid
- **THEN** the system returns a clear error message indicating the connection failure reason

### Requirement: Oracle built-in tool registration
The system SHALL register Oracle as a built-in tool with id=-3 in `builtin_tools.py`. The tool SHALL be registered in `tools_loader.py` with `enable_extra_prompt=True`. The `chat_service.py` SHALL recognize Oracle built-in tools by name matching (`BUILTIN_ORACLE_TOOL_NAME`).

#### Scenario: Built-in tool loaded at startup
- **WHEN** the system initializes built-in tools
- **THEN** Oracle tool (id=-3) is available with all 25 sub-tools registered

#### Scenario: LLM receives instance context
- **WHEN** `enable_extra_prompt` is True and Oracle instances are configured
- **THEN** the LLM system prompt includes instance names and instructs the LLM to use the default instance without asking the user

### Requirement: Resource discovery tools (7 tools)
The system SHALL provide: `get_current_database_info` (v$database + v$instance + v$version), `list_oracle_tablespaces` (dba_tablespaces + usage), `list_oracle_tables` (user_tables/all_tables), `list_oracle_indexes` (user_indexes + columns), `get_table_structure` (user_tab_columns + constraints), `list_oracle_users` (dba_users + roles), `get_database_config` (v$parameter key params).

#### Scenario: Get database info
- **WHEN** LLM calls `get_current_database_info`
- **THEN** the system returns database name, instance name, version, and status from Oracle data dictionary

#### Scenario: List tablespaces with usage
- **WHEN** LLM calls `list_oracle_tablespaces`
- **THEN** the system returns all tablespaces with size, used space, free space, and usage percentage

### Requirement: Dynamic query tools (3 tools)
The system SHALL provide: `search_tables_by_keyword` (all_tables + all_tab_columns LIKE search), `execute_safe_select` (validated read-only SELECT with `SET TRANSACTION READ ONLY`), `explain_query_plan` (EXPLAIN PLAN FOR + DBMS_XPLAN output).

#### Scenario: Safe SELECT execution
- **WHEN** LLM calls `execute_safe_select` with a valid SELECT statement
- **THEN** the system validates the query against the deny list, executes within a read-only transaction, and returns results

#### Scenario: Blocked unsafe query
- **WHEN** LLM calls `execute_safe_select` with a statement containing ALTER SYSTEM, DROP, TRUNCATE, or other denied keywords
- **THEN** the system rejects the query and returns an error explaining the restriction

### Requirement: Fault diagnosis tools (5 tools)
The system SHALL provide: `diagnose_slow_queries` (v$sql TOP N), `diagnose_lock_conflicts` (v$lock + dba_waiters), `diagnose_connection_issues` (v$session vs parameters), `check_database_health` (comprehensive health check), `check_dataguard_status` (Data Guard state + lag).

#### Scenario: Diagnose slow queries
- **WHEN** LLM calls `diagnose_slow_queries`
- **THEN** the system returns top N queries by elapsed time from v$sql with execution stats

#### Scenario: Data Guard not configured
- **WHEN** LLM calls `check_dataguard_status` on a standalone database
- **THEN** the system returns a message indicating Data Guard is not configured

### Requirement: Runtime monitoring tools (6 tools)
The system SHALL provide: `get_database_metrics` (v$sysstat core metrics), `get_table_metrics` (dba_segments + statistics), `get_sga_pga_stats` (SGA + PGA + buffer cache hit ratio), `get_io_stats` (v$filestat), `check_redo_log_status` (v$log + archive status), `get_processlist` (v$session + v$process active sessions).

#### Scenario: SGA/PGA stats retrieval
- **WHEN** LLM calls `get_sga_pga_stats`
- **THEN** the system returns SGA component sizes, PGA stats, and buffer cache hit ratio

### Requirement: Optimization advice tools (4 tools)
The system SHALL provide: `check_tablespace_usage` (usage + growth + autoextend), `check_unused_indexes` (unused index detection), `check_table_fragmentation` (fragmentation + row migration/chaining), `check_configuration_tuning` (parameter tuning suggestions).

#### Scenario: Unused index detection
- **WHEN** LLM calls `check_unused_indexes`
- **THEN** the system queries index usage statistics and returns indexes that have not been used since last stats reset

### Requirement: Oracle tool test connection API
The system SHALL expose a `test_oracle_connection` API endpoint in `llm_view.py` that accepts Oracle connection parameters and returns success/failure with version info.

#### Scenario: Successful test connection
- **WHEN** frontend calls `testOracleConnection` with valid Oracle credentials
- **THEN** the API returns success with Oracle version string

### Requirement: Oracle frontend tool editor
The system SHALL provide an `oracleToolEditor.tsx` component for configuring multiple Oracle instances. The tool selector SHALL recognize Oracle tools and render the dedicated editor. The frontend SHALL include i18n strings for Oracle tool labels in both zh.json and en.json.

#### Scenario: Add Oracle instance in editor
- **WHEN** user clicks "Add Instance" in the Oracle tool editor
- **THEN** a new instance form appears with fields: name, host, port, service_name, user, password, nls_lang

#### Scenario: Test connection from editor
- **WHEN** user clicks "Test Connection" for an Oracle instance
- **THEN** the frontend calls `testOracleConnection` API and displays the result

## Work Checklist

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
