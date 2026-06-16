# Ops Analysis Governance Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add commercial-only CMDB governance health data sources and query APIs for operation analysis dashboards.

**Architecture:** Implement the health query contract inside `apps.cmdb_enterprise.governance`, expose it as NATS `rest_api` functions only when the enterprise app is loaded, and register operation-analysis data sources via an enterprise management command. Operation analysis remains a read-only consumer through its existing data source proxy.

**Tech Stack:** Django 4.2, pytest, NATS function registration, operation_analysis `DataSourceAPIModel`.

---

### Task 1: Governance Health Query Service

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/health_query.py`

- [ ] **Step 1: Write failing tests**

Create tests covering admin/global overview, normal user model-in-current-organization overview, forbidden organization access, trend date range, ranking by model/organization, and problem ranking.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py -q`

Expected: FAIL because `apps.cmdb_enterprise.governance.health_query` does not exist.

- [ ] **Step 3: Implement minimal query service**

Implement:
- `get_governance_health_overview`
- `get_governance_health_trend`
- `get_governance_health_rank`
- `get_governance_health_problem_top`

The service must infer snapshot dimension from `user_info`, `model_id`, and `organization_id`, deny normal-user global/model queries, and return only fields defined in the design doc.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py -q`

Expected: PASS.

### Task 2: Enterprise NATS Registration

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/nats.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/registry_hooks.py`

- [ ] **Step 1: Write failing tests**

Create tests asserting NATS wrapper functions return `{result: True, data: ...}` for valid queries and `{result: False, code: 403, message: ...}` for permission failures.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: FAIL because the NATS module does not exist.

- [ ] **Step 3: Implement minimal NATS wrappers**

Create `governance/nats.py` with four `@nats_client.register` functions matching the registered `rest_api` paths. Import the module from `registry_hooks.py` so the handlers are registered only in enterprise edition.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: PASS.

### Task 3: REST API Usage Documentation

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/governance/docs/ops_analysis_rest_api.md`

- [ ] **Step 1: Write usage documentation**

Document the four `cmdb_enterprise/*` `rest_api` endpoints, supported params, returned fields, and permission behavior for manual configuration in the operation-analysis data source page.

- [ ] **Step 2: Verify no built-in data source registration remains**

Run: `rg -n "init_cmdb_governance_operation_analysis_sources|GOVERNANCE_OPERATION_ANALYSIS_SOURCES|GOVERNANCE_HEALTH_FIELD_SCHEMA" enterprise/server/apps/cmdb_enterprise server/apps`

Expected: no matches.

### Task 4: Final Verification

**Files:**
- All files changed by Tasks 1-3.

- [ ] **Step 1: Run targeted enterprise tests**

Run: `cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_query.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_ops_analysis.py -q`

Expected: PASS.

- [ ] **Step 2: Check worktree**

Run: `git status --short`

Expected: Only intended files are changed, plus any pre-existing user changes.
