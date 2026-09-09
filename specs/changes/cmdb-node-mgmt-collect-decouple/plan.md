# 节点管理发现与采集解耦 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD。本会话内联执行。不要提交，除非用户要求。

**Goal:** 发现只写 host 库存；采集每次自己拉节点管理、认领已有 host、刷新系统采集任务名单后走现有 `exec_task`；两段租约互不阻塞。

**Architecture:** `acquire_run` 按 `run_type` 写入不同 `active_scope`（`node_mgmt_sync` / `node_mgmt_collect`）。`execute_collect` 去掉 waiting_sync 闸门；`_do_collect_hosts` 先拉源、建壳、按共用身份写 `instances`、退役消失区域，再调用现有下发。`_do_sync_hosts` 删除 `_ensure_region_collect_task` / 写名单 / 退役采集任务。

**Tech Stack:** Django、Celery beat 已有周期任务、现有 `CollectModelService.exec_task`、`host_sync_identity.resolve_host_identity`。

---

### 文件

- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_execution.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_collection.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_models.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_empty_source.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_host_mapping.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_persistence.py`（去掉对发现写采集任务的依赖）
- 不改: `collect_service.exec_task` 业务语义、host plugin

### Task 1: 拆租约

- 增加 `COLLECT_ACTIVE_SCOPE = "node_mgmt_collect"`；`ACTIVE_SCOPE` 仍为同步。
- `acquire_run` 按 run_type 写对应 scope。
- `finish_run` / `heartbeat_run` / `recover_stale_runs` / claim / submitted 刷新 / snapshot CAS：按 **该 run 持有的 scope** 过滤，恢复时 `active_scope__in` 两个 scope。
- 测试：sync 与 collect 可同时 running；同一 scope 仍 unique 冲突。

### Task 2: 去掉采集等待同步

- `_prepare_collect_run` 只 `acquire_run(collect)`。
- 删除 `_has_current_successful_sync` 对采集入口的闸门、`_upsert_waiting_sync_run_locked`、`_build_waiting_sync_run` 的使用。
- 改写 `test_collect_waits_for_first_successful_sync` 等：无成功同步时只要采集打开就刷新并尝试下发。

### Task 3: 采集执行前刷新名单

- 新增认领已有 host（`resolve_host_identity`，不 persist）。
- `_do_collect_hosts` 开头：`_fetch_non_container_nodes` → 分组 → 空源则本段退役采集任务并 BLOCKED（`NODE_SOURCE_EMPTY` / `NO_VALID_NODES`）→ 否则按区域 `_ensure_region_collect_task` + 写入认领到的 instances → `_retire_missing_region_collect_tasks` → 再走现有 `exec_task` 循环。
- 未命中 / conflict 的 sidecar 不进名单、不建 host。

### Task 4: 发现不再碰采集任务

- `_do_sync_hosts` 去掉 query/ensure/save collect task、去掉 retire collect tasks。
- 成功同步的 reconcile 不再因 `retired_regions` 去推采集节点配置。
- 空源同步测试改为不退役采集任务；退役断言改到采集空源。

### 验证

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/cmdb/tests/test_node_mgmt_sync_execution.py \
    apps/cmdb/tests/test_node_mgmt_sync_collection.py \
    apps/cmdb/tests/test_node_mgmt_sync_models.py \
    apps/cmdb/tests/test_node_mgmt_sync_empty_source.py \
    apps/cmdb/tests/test_node_mgmt_sync_host_mapping.py \
    apps/cmdb/tests/test_node_mgmt_sync_persistence.py \
    apps/cmdb/tests/test_node_mgmt_sync_resilience.py \
    --no-cov
```

本地若 sqlite 迁移失败则用仓库现有 Postgres 环境跑同一批。
