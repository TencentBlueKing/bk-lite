## 1. 测试先行

- [ ] 1.1 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加组织差异 helper 的单元测试，覆盖列表、数字、字符串、空值、重复值规范化。
- [ ] 1.2 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加采集任务创建/更新/删除镜像 detail 的测试，断言 `organization_change.field` 固定为 `organization` 且只包含组织 ID。
- [ ] 1.3 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加资产普通属性变更不镜像、资产组织变化才镜像的测试。
- [ ] 1.4 在 `server/apps/system_mgmt/tests/test_audit_mirror_e2e_service.py` 增加端到端测试，确认 `OperationLog.detail.organization_change` 按 JSON 结构持久化。

## 2. 组织变化提取与镜像口径

- [ ] 2.1 在 `server/apps/cmdb/utils/change_record.py` 增加组织 ID 规范化 helper，将 `None`、单值、列表统一为去重后的 ID 列表。
- [ ] 2.2 在 `server/apps/cmdb/utils/change_record.py` 增加 `organization_change` 构建 helper，按 `before_ids`、`after_ids` 计算 `added_ids`、`removed_ids`、`changed`。
- [ ] 2.3 扩展 `_mirror_change_record`，在 detail 中注入 `organization_change`，且无组织上下文时不写该字段。
- [ ] 2.4 保持 `_mirror_change_record` 的异常隔离策略，确保平台操作日志失败不影响 `ChangeRecord` 写入。

## 3. CMDB 对象接入

- [ ] 3.1 确认采集任务 `CollectModelService._snapshot_task` 的 `team` 字段进入 before/after 快照，并通过统一 helper 映射为 `organization_change`。
- [ ] 3.2 补齐模型管理更新路径的 `ChangeRecord`，确保模型 `group` 变化进入平台操作日志的 `organization_change`。
- [ ] 3.3 检查模型创建/删除路径，确保有组织上下文时按创建/删除口径记录 `organization_change`。
- [ ] 3.4 调整资产实例单个更新镜像策略，仅当 `organization` 变化时把普通属性场景额外镜像到平台操作日志。
- [ ] 3.5 调整资产实例批量更新镜像策略，仅对组织发生变化的实例镜像平台操作日志。

## 4. 验证与收口

- [ ] 4.1 运行 `cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_change_record_mirror_service.py apps/system_mgmt/tests/test_audit_mirror_e2e_service.py`。
- [ ] 4.2 如实现触及模型服务或实例服务既有测试，补跑相关最小回归：`apps/cmdb/tests/test_model_service_methods.py`、`apps/cmdb/tests/test_instance_service_crud.py`。
- [ ] 4.3 运行 `PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH openspec status --change add-cmdb-organization-audit-log`，确认 proposal、design、specs、tasks 均完成。
