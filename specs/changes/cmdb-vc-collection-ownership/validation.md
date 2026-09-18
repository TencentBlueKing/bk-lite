# 本地验证记录

日期：2026-09-17。未执行真实 VC 采集或修改运行中任务。

## 执行环境

从仓库根目录执行，使用 `server/.venv/bin/python`。环境变量为测试占位值：

```sh
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=vc-test ENABLE_CELERY=true \
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=vc-test MINIO_SECRET_KEY=vc-test \
MINIO_USE_HTTPS=0 PYTHONPATH=. server/.venv/bin/python -m pytest \
  <下列测试文件> -c server/pytest.ini -o addopts='' --nomigrations \
  --cov=apps.cmdb.services.vmware_collection_scope \
  --cov=apps.cmdb.collection.vmware_reconciliation --cov-report=term-missing -q
```

MinIO 变量只用于满足 Django 初始化配置检查，没有启动或访问 MinIO。首次覆盖率运行缺少这些变量时初始化失败；补齐占位值后的完整回归通过。

## 回归范围

全部位于 `server/apps/cmdb/tests/`：

- `test_vmware_collection_ownership_service.py`：21 项新增行为测试。
- `test_collect_base_runner_pure.py`
- `test_collect_management_service.py`
- `test_collect_management_hooks.py`
- `test_collect_service_methods.py`
- `test_collect_task_single_flight.py`
- `test_collect_snapshot_uuid.py`
- `test_collect_service_first_collection.py`
- `test_collect_celery_tasks_svc.py`
- `test_scan_finalize_service.py`
- `test_network_topology_pipeline.py`
- `test_slice_collect_tool_data_cleanup_k8s.py`
- `test_serializers.py`
- `test_collect_model_credential_pool.py`
- `e2e/test_vmware_pipeline.py`

最终输出：

```text
vmware_reconciliation.py      41 statements, 0 missed, 100%
vmware_collection_scope.py   131 statements, 11 missed, 92%
TOTAL                       172 statements, 11 missed, 94%
363 passed in 7.70s
```

另用相同环境、`--no-cov` 执行 `test_unique_write_lock.py`：`3 passed in 0.58s`。

## 关键验收证据

1. 新建同端点不同根实例的任务：实际保存服务拒绝，任务不创建、不写图。
2. 已存在重复任务：原任务拥有子资源、根为空时，新任务整轮无写入；原任务可补齐根归属。
3. 真实插件处理 VC、ESXi、DS、VM 四类指标：根先更新，子资源及四条关联边成功写入。
4. 删除原任务：实际清空归属服务保留原实例；新任务继续更新同一批 UUID，关联端点不变，重复同步不复制资产。
5. 实际 worker 执行归属冲突：持久化状态 ERROR，`add=0`、`update_error=4`，详情明确提示其他任务归属。
6. 根改名、根写入失败、缺少根样本、混合所有者、跨组织等场景均按约定拒绝或更新。
7. 立即清理保留历史重复根、其他任务的资产和本轮未命中的无任务资产。

这些结果验证本地代码与适配器契约，不代替真实 FalkorDB 和真实 VC 的现场验收。
