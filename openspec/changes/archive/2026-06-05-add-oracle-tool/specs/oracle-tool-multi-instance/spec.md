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
