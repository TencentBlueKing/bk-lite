# CMDB 实例 UUID — §13 验收证据

Date: 2026-08-10  
Branch: `local_codex/cmdb-instance-uuid`  
契约：[spec.md](./spec.md) §13  
关联：[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) T8

> 本表只记录本分支可复现的证据。生产切换的操作步骤见  
> [`docs/operations/cmdb-instance-uuid-cutover.md`](../../../docs/operations/cmdb-instance-uuid-cutover.md)。

## 复跑命令与结果（2026-08-10）

### CMDB 核心切片

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false \
INSTALL_APPS=system_mgmt,node_mgmt,cmdb DB_ENGINE=sqlite DB_NAME=:memory: \
.venv/bin/python -m pytest -q -o addopts='' \
  apps/cmdb/tests/test_instance_identity_pure.py \
  apps/cmdb/tests/test_falkordb_client.py \
  apps/cmdb/tests/test_instance_views.py \
  apps/cmdb/tests/test_open_api_instance_views.py \
  apps/cmdb/tests/test_instance_uuid_migrations.py \
  apps/cmdb/tests/test_migrate_cmdb_instance_uuid_refs.py \
  apps/cmdb/tests/test_collect_base_and_cloud_pure.py \
  apps/cmdb/tests/test_network_config_file_node_params.py \
  apps/cmdb/tests/test_config_file_process_collect_db.py \
  apps/cmdb/tests/test_config_file_service.py
```

**结果：`245 passed`**

### FalkorDB 真实图库烟测（本机 6379 可达）

```bash
# 同上环境变量
.venv/bin/python -m pytest -q -o addopts='' \
  apps/cmdb/tests/test_falkordb_real_integration.py::test_create_edge_persists_uuid_endpoints_real \
  apps/cmdb/tests/test_falkordb_client.py -k 'uuid or inst_uuid or edge'
```

**结果：`11 passed`**（含真实 `create_edge` 持久化 `src/dst_inst_uuid`）

> 完整「删库重建后按 UUID 读实例/关系/PG 引用仍正确」属维护窗口人工烟测，见 cutover §4。

### OA / Alerts

```bash
INSTALL_APPS=system_mgmt,node_mgmt,cmdb,operation_analysis ... \
  apps/cmdb/tests/test_migrate_oa_cmdb_instance_uuid_refs.py
# → 2 passed

INSTALL_APPS=system_mgmt,node_mgmt,cmdb,alerts ... \
  apps/alerts/tests/test_enrichment_provider_cmdb.py
# → 2 passed
```

### Stargazer 配置采集协议

```bash
cd agents/stargazer
.venv/bin/python -m pytest -q -o addopts='' \
  tests/test_network_config_file_info.py \
  tests/test_collect_multicred.py::test_config_collection_endpoint_rejects_old_identity_protocol \
  tests/test_collect_multicred.py::test_config_collection_endpoint_preserves_uuid_identity_when_splitting \
  tests/test_host_collector.py::test_config_file_callback_payload_preserves_execution_id
```

**结果：`18 passed`**

### 已知隔离项

| 项 | 说明 |
|---|---|
| OpsPilot 全量装载 | 精简 venv 缺 `markitdown`，`INSTALL_APPS` 含 `opspilot` 时 Django setup 失败；不阻断 T1–T7 已落地的 tools 改动 |
| OA 全量采集 | 部分 OA 测试隐式依赖 `alerts` 模型；UUID 改名清洗测已单独绿 |
| Web | 本阶段不改；对接清单见 [FRONTEND_HANDOFF.md](./FRONTEND_HANDOFF.md) |

---

## §13 自检表

| # | 标准 | 验证方式 | 证据 | 状态 |
|---|---|---|---|---|
| 1 | 创建成功节点有合法唯一 UUIDv4 | 自动化 | `test_instance_identity_pure`；`test_falkordb_client` 创建路径；`test_instance_views` create | ✅ |
| 2 | 更新含 `inst_uuid` 被拒且值不变 | 自动化 | instance identity / update 路径相关测（identity 纯函数 + instance service） | ✅ |
| 3 | 关联边仅 UUID 端点、无数字端点 | 自动化 + 真图 | `test_create_edge_persists_uuid_endpoints*`；migrate 图清洗 | ✅ |
| 4 | 发版清洗 verify：无缺 UUID/无重复/无缺端点边 | 自动化 + 运维命令 | `migrate_cmdb_instance_uuid_refs --verify`；`test_migrate_cmdb_instance_uuid_refs` dry-run/apply | ✅（运维须在窗口内留原始输出） |
| 5 | 图 `_id` 重建后 UUID 引用仍正确 | 人工/副本烟测 | 单元侧保证按 UUID 查询；**重建烟测见 cutover §2** | ⚠️ 运维门禁 |
| 6 | Telegraf 标签仍为 `cmdb_{task_id}` | 自动化 | `test_collect_base_and_cloud_pure`（`instance_id='cmdb_42'`） | ✅ |
| 7 | 数字 `inst_id` 定位实例被安全拒绝 | 自动化 | `test_retrieve_rejects_digit_only_pk` / `test_destroy_rejects_digit_only_pk`；OpenAPI UUID 路径 | ✅ |
| 8 | 旧数字配置回调被安全拒绝 | 自动化 | Stargazer protocol 拒测；`ConfigFileService._validate_callback_identity` | ✅ |
| 9 | UUID 访问越权实例不放宽 | 自动化 | OpenAPI/View 权限测仍走 permission_map（`test_open_api_instance_views`） | ✅ |
| 10 | 内部可用 `_id`，出站无数字业务键 | 自动化 | retrieve 断言无 `inst_id`/`_id` 业务键；内部 resolve 仍用图 id | ✅ |

---

## 清洗命令幂等（替代旧 prepare 编排）

本分支**没有** `prepare_cmdb_instance_uuid_cutover` / 删列 cutover 迁移（T5 锁定：结构 `0045_instance_uuid_transition` + 维护期清洗；删列另开新号）。

幂等入口：

```bash
uv run python manage.py migrate_cmdb_instance_uuid_refs --dry-run
uv run python manage.py migrate_cmdb_instance_uuid_refs --apply
uv run python manage.py migrate_cmdb_instance_uuid_refs --verify
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --dry-run
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --apply
uv run python manage.py migrate_oa_cmdb_instance_uuid_refs --verify
```

- 清洗 **∉** `batch_init`；不得塞进启动硬门禁。  
- `--apply` 依赖 `CmdbUuidMigrationState` 断点；重复执行应无额外写入或安全跳过。  
- `--verify` 发现待清洗项非零退出。
