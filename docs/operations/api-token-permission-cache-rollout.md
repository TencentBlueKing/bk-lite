# API Token 权限代际缓存发布与回滚

本流程只适用于首次上线带权限代际的 API Token 缓存版本，以及回滚到不识别代际的旧版本。
普通版本升级不需要重复执行。

## 首次上线

1. 暂停角色、菜单、组织和数据权限变更入口。
2. 排空并停止全部旧版 Server Worker，确认没有旧二进制继续处理鉴权或写入无版本缓存键。
3. 启动全部新版 Server Worker。
4. 验证 API Token 鉴权和权限变更回归通过后，恢复权限变更入口。

禁止旧版与新版 Server Worker 在权限变更窗口内混合提供鉴权。默认 LocMem 缓存会随旧 Worker
退出而清空；共享 Redis 中的旧键不会被新版读取，并由原 TTL 自然回收。

## 回滚

1. 再次暂停权限变更入口。
2. 排空并停止全部新版 Server Worker。
3. 使用待回滚前的新版镜像执行：

   ```bash
   python manage.py prepare_permission_cache_rollback --confirm
   ```

   该命令只清理 `perm_rules:*`、`token_info:*`、`api_token_permissions:*` 及其索引，
   避免旧二进制重新采用共享 Redis 中残留的无版本权限快照；不会清空 JWT 撤销黑名单、
   OTP 限流或登录挑战等其他默认缓存数据。命令失败时禁止启动旧版本 Worker。
4. 启动全部旧版 Server Worker，完成 API Token 鉴权和权限变更回归后恢复入口。

如果无法执行清缓存命令，必须在全部 Worker 停止后等待
`API_TOKEN_PERMISSION_CACHE_TTL`、`PERMISSION_CACHE_TTL` 与 `TOKEN_INFO_CACHE_TTL`
中最大的 TTL 完整到期，才能启动旧版本。
