# 02 — 网关写出会话结束记录

Status: ready

Blocked by: None

**What to build:** 会话空闲满 15 分钟或开始满 4 小时后，在一个扫描周期内，RUM 的 VictoriaLogs 出现一条该会话
的 `session_end` 记录，字段齐全、计数与原始事件一致；按用户或会话删除数据时它一并被删。

- [ ] rumsession 的 Lua 在同一次执行里累计事件数/浏览数/错误数，记录第一个非空入口路由、版本、用户、环境、
      两个 erasure 字段；会话切换时先写快照 key 再清零；维护按 `last_seen` 的 ZSET 索引
- [ ] 只对 `logs/rum` 的事件累计（`rum.application` 路径）；回放流水线（`rum.replay.*` 路径）只分配会话，不累计
- [ ] `assign()` 与返回结构扩展；15 分钟 / 4 小时 / 5 小时保持不变
- [ ] maintainer 新增 VictoriaLogs 写入客户端（`/insert/jsonline`），定期扫描索引、写记录、写成功后移出索引
      并删除快照；失败重试，重试窗口为快照 TTL
- [ ] 快照过期而索引成员仍在：计入丢失计数指标、移出索引、有界 WARNING 汇总
- [ ] maintainer 单副本约束写进 `deploy/rum` 的验收清单和部署说明；会话记录字段契约写进部署说明
- [ ] 测试：真实 Lua（miniredis）覆盖切换后计数从 0 开始、第一路由保留、ZSET；HTTP 桩覆盖写入请求体、
      重试、移出索引、丢失计数；删除过滤器能命中会话记录
- [ ] `make -C deploy/rum test` 与 `make -C deploy/rum validate` 通过

## Notes

- 每个会话 Redis 占用约 160 → 250 字节，切换时另有约 290 字节快照（已验证）。
- 日志不记录会话键、用户、事件正文。
- 不改删除路径（`victoria.go` 的过滤器已能命中 `rum.erasure.*`）。
