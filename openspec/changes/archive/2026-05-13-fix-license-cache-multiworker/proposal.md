## Why

当前 license 缓存使用 Python 进程内全局变量实现，在多 Worker 部署环境（默认 8 个 worker）下存在缓存不一致问题。当一个 worker 新增/禁用 license 并调用 `invalidate_license_cache()` 时，只有该 worker 的缓存被清除，其他 worker 仍返回旧缓存数据，导致用户看到的 license 状态不一致。

## What Changes

- 将 `license_cache.py` 中的进程内缓存（`_licensed_modules_cache` 全局变量）迁移到 Django Cache（Redis backend）
- 保持现有 API 不变：`get_licensed_modules()`、`get_licensed_names()`、`get_licensed_raw_codes()`、`invalidate_license_cache()`
- 修复 `sync_expired_licenses()` 方法缺少缓存失效调用的 bug
- 移除不再需要的 `threading.Lock`（Redis 操作是原子的）

## Capabilities

### New Capabilities

无新增能力。

### Modified Capabilities

- `license-management`: 缓存实现从进程内变量改为 Redis，确保多 Worker 环境下缓存一致性

## Impact

- **代码变更**：`server/apps/license_mgmt/utils/license_cache.py` 重构
- **代码变更**：`server/apps/license_mgmt/services/license_service.py` 在 `sync_expired_licenses()` 末尾添加缓存失效调用
- **依赖**：使用已配置的 `django.core.cache`（Redis backend），无新增依赖
- **API**：对外接口保持不变，调用方无需修改
- **性能**：Redis 网络调用替代内存访问，延迟略增（微秒级），但换取一致性
