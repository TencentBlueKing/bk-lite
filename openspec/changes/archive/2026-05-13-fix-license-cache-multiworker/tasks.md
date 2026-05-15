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
