## 1. Service Layer

- [x] 1.1 Add `sync_node_properties()` method to `SidecarConfigService` class
- [x] 1.2 Implement node_name field update in sidecar.yaml
- [x] 1.3 Implement organization tags sync with `group:<org_id>` format
- [x] 1.4 Preserve non-group tags (zone, install_method, node_type, etc.)
- [x] 1.5 Call service restart after config update

## 2. Celery Task

- [x] 2.1 Create `server/apps/node_mgmt/tasks/sidecar_config.py` with async task
- [x] 2.2 Implement `sync_node_properties_to_sidecar(node_id, name, organizations)` task
- [x] 2.3 Register task in `__init__.py`

## 3. View Integration

- [x] 3.1 Modify `update_node` action in `NodeViewSet` to trigger sync
- [x] 3.2 Fire Celery task after successful DB update
- [x] 3.3 Remove unused standalone `sidecar_config` action (superseded design)

## 4. Cleanup

- [x] 4.1 Delete `server/apps/node_mgmt/serializers/sidecar_config.py` (no longer needed)
