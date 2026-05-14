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
