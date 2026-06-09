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
