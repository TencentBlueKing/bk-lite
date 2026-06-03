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
# 存储结构: {"modules": [...], "app_names": [...], "raw_codes": [...], "date": "2026-05-13"}
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
