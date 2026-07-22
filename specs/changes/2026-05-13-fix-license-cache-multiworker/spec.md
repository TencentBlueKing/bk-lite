# 2026 05 13 Fix License Cache Multiworker

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-13-fix-license-cache-multiworker/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

当前 `license_cache.py` 使用 Python 进程内全局变量 `_licensed_modules_cache` 作为缓存：

```python
_licensed_modules_cache = {
    "modules": set(),
    "app_names": set(),
    "raw_codes": set(),
    "date": None,  # 日期级失效
    "lock": threading.Lock(),
}
```

生产环境通过 `APP_WORKERS=8` 运行多个 uvicorn worker 进程。每个进程有独立的内存空间，导致：
1. Worker A 新增 license 并调用 `invalidate_license_cache()` 只清除 Worker A 的缓存
2. Worker B-H 的缓存仍是旧数据
3. 后续请求随机分配到不同 worker，导致用户看到不一致的 license 状态

项目已配置 Django Cache 使用 Redis backend（`django.core.cache`），可直接复用。

## Goals / Non-Goals

**Goals:**
- 使用 Redis 作为共享缓存，确保多 Worker 环境下缓存一致性
- 保持现有 API 签名不变，调用方无需修改
- 修复 `sync_expired_licenses()` 缺少缓存失效调用的 bug
- 保持日期级缓存失效策略（跨天自动刷新）

**Non-Goals:**
- 不改变缓存的业务逻辑（仍然缓存 modules/app_names/raw_codes）
- 不引入新的缓存框架或依赖
- 不修改 license 的其他业务逻辑

## Decisions

### Decision 1: 使用 Django Cache 而非直接操作 Redis

**选择**: 使用 `django.core.cache.cache`

**理由**:
- 项目已配置 Django Cache 使用 Redis backend，无需额外配置
- Django Cache 提供统一的 API，未来切换 backend 无需改代码
- 自动处理序列化/反序列化

**替代方案**:
- 直接使用 `redis-py`：需要额外管理连接池和序列化，增加复杂度

### Decision 2: 缓存 Key 设计

**选择**: 使用单一 key `license:modules_cache` 存储整个缓存结构

```python
CACHE_KEY = "license:modules_cache"
```

**理由**:
- 三个集合（modules/app_names/raw_codes）总是一起刷新，使用单一 key 保证原子性
- 简化失效逻辑：`cache.delete(CACHE_KEY)` 一次清除所有

**替代方案**:
- 三个独立 key：增加复杂度，需要处理部分失效的边界情况

### Decision 3: 缓存 TTL 策略

**选择**: TTL 设置为当天剩余秒数，午夜自动过期

```python
def _get_seconds_until_midnight():
    """计算距离午夜的秒数"""
    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), time.min)
    return int((midnight - now).total_seconds())
```

**理由**:
- 与原有"日期级缓存"语义完全一致：当天有效，跨天自动失效
- 无需在读取时检查日期，Redis TTL 自动处理过期
- 简化代码逻辑

**替代方案**:
- 固定 25 小时 TTL + 日期检查：增加复杂度，需要在缓存中存储日期并每次读取时校验

### Decision 4: 移除 threading.Lock

**选择**: 移除 `threading.Lock`，依赖 Redis 原子操作

**理由**:
- Redis `GET`/`SET`/`DELETE` 是原子操作
- 多 Worker 环境下，进程内 Lock 本就无法跨进程同步
- 简化代码

### Decision 5: Set 序列化

**选择**: 将 `set` 转换为 `list` 存储，读取时转回 `set`

**理由**:
- JSON 不支持 `set` 类型
- Django Cache 默认使用 JSON 序列化
- 转换开销可忽略（通常 < 20 个元素）

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Redis 不可用导致 license 校验失败 | 缓存 miss 时从 DB 加载，Redis 故障不影响功能正确性，仅影响性能 |
| 网络延迟增加 | Redis 调用通常 < 1ms，相比 DB 查询仍有优势；且 license 校验不在热路径 |
| 缓存数据格式变更导致旧数据解析失败 | 使用 try-except 包裹反序列化，失败时视为 cache miss 重新加载 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-13
```

## Capability Deltas

### license-management

## ADDED Requirements

### Requirement: 许可缓存必须在多 Worker 环境下保持一致

系统 MUST 使用共享缓存（Redis）存储许可模块缓存，确保任意 Worker 进程的缓存变更对所有 Worker 立即可见。

#### Scenario: 多 Worker 环境下新增许可后缓存一致
- **WHEN** Worker A 执行 `add_license()` 并调用 `invalidate_license_cache()`
- **THEN** Worker B 的后续 `get_licensed_modules()` 调用 MUST 返回包含新许可的数据

#### Scenario: 多 Worker 环境下禁用许可后缓存一致
- **WHEN** Worker A 执行 `disable_license()` 并调用 `invalidate_license_cache()`
- **THEN** Worker B 的后续 `get_licensed_modules()` 调用 MUST 不再包含被禁用许可的模块

#### Scenario: 许可过期同步后缓存一致
- **WHEN** `sync_expired_licenses()` 将许可状态更新为 expired
- **THEN** 系统 MUST 调用 `invalidate_license_cache()` 清除缓存

### Requirement: 许可缓存必须保持日期级失效策略

系统 MUST 在缓存中记录数据对应的日期，跨天时自动刷新缓存。

#### Scenario: 同一天内缓存命中
- **WHEN** 缓存中的日期等于当前日期
- **THEN** 系统 MUST 直接返回缓存数据，不查询数据库

#### Scenario: 跨天缓存自动刷新
- **WHEN** 缓存中的日期不等于当前日期
- **THEN** 系统 MUST 从数据库重新加载许可数据并更新缓存

### Requirement: 许可缓存必须容忍 Redis 故障

系统 MUST 在 Redis 不可用或缓存数据损坏时降级为直接查询数据库。

#### Scenario: Redis 连接失败
- **WHEN** Redis 连接不可用
- **THEN** 系统 MUST 从数据库加载许可数据，不抛出异常

#### Scenario: 缓存数据格式损坏
- **WHEN** 缓存中的数据无法反序列化
- **THEN** 系统 MUST 视为缓存未命中，从数据库重新加载

## Work Checklist

## 1. 重构 license_cache.py

- [x] 1.1 添加 Django Cache 导入和缓存 key 常量定义
- [x] 1.2 重构 `_refresh_licensed_modules()` 将数据写入 Redis 缓存，TTL 设置为当天剩余秒数（午夜过期）
- [x] 1.3 重构 `get_licensed_modules()` 从 Redis 读取缓存，保留日期检查逻辑
- [x] 1.4 重构 `get_licensed_names()` 从 Redis 读取缓存
- [x] 1.5 重构 `get_licensed_raw_codes()` 从 Redis 读取缓存
- [x] 1.6 重构 `invalidate_license_cache()` 使用 `cache.delete()` 清除 Redis 缓存
- [x] 1.7 移除不再需要的 `_licensed_modules_cache` 全局变量和 `threading.Lock`
- [x] 1.8 添加 try-except 处理 Redis 故障降级逻辑

## 2. 确保 license 变更时缓存更新

- [x] 2.1 确认 `add_license()` 已调用 `invalidate_license_cache()`（已有）
- [x] 2.2 确认 `disable_license()` 已调用 `invalidate_license_cache()`（已有）
- [x] 2.3 在 `sync_expired_licenses()` 方法末尾添加 `invalidate_license_cache()` 调用（缺失）

## 3. 验证

- [x] 3.1 运行 `cd server && make test` 确保现有测试通过
- [x] 3.2 检查 `lsp_diagnostics` 确保无类型错误
