# 02 — 网关写出会话结束记录

Status: done

Blocked by: None

**What to build:** 会话空闲满 15 分钟或开始满 4 小时后，在一个扫描周期内，RUM 的 VictoriaLogs 出现一条该会话
的 `session_end` 记录，字段齐全、计数与原始事件一致；按用户或会话删除数据时它一并被删。

- [x] rumsession 的 Lua 在同一次执行里累计事件数/浏览数/错误数，记录第一个非空入口路由、版本、用户、环境、
      两个 erasure 字段；会话切换时先写快照 key 再清零；维护按 `last_seen` 的 ZSET 索引
- [x] 只对 `logs/rum` 的事件累计（`rum.application` 路径）；回放流水线（`rum.replay.*` 路径）只分配会话，不累计
- [x] `assign()` 与返回结构扩展；15 分钟 / 4 小时 / 5 小时保持不变
- [x] maintainer 新增 VictoriaLogs 写入客户端（`/insert/jsonline`），定期扫描索引、写记录、写成功后移出索引
      并删除快照；失败重试，重试窗口为快照 TTL
- [x] 快照过期而索引成员仍在：计入丢失计数指标、移出索引、有界 WARNING 汇总
- [x] maintainer 单副本约束写进 `deploy/rum` 的验收清单和部署说明；会话记录字段契约写进部署说明
- [x] 测试：真实 Lua（miniredis）覆盖切换后计数从 0 开始、第一路由保留、ZSET；HTTP 桩覆盖写入请求体、
      重试、移出索引、丢失计数；删除过滤器能命中会话记录
- [x] `make -C deploy/rum test` 与 `make -C deploy/rum validate` 通过

## Notes

- 每个会话 Redis 占用约 160 → 250 字节，切换时另有约 290 字节快照（已验证）。
- 日志不记录会话键、用户、事件正文。
- 不改删除路径（`victoria.go` 的过滤器已能命中 `rum.erasure.*`）。
- 快照 key 为 `ops:rum:v2:ended:{session_key}`，TTL 沿用 `state_ttl`（默认 5 小时），每条触达该会话的事件刷新，不另加配置。可写之后大约还能重试 4 小时 45 分钟。
- 活动索引是一个 ZSET：`ops:rum:v2:session:activity`，member 为 32 位会话键。score 在距 4 小时上限还早时等于 `last_seen`；一旦 `first_seen + 4h - 15min` 更早，score 取这个更早的值。这样维护进程只用 `score <= now - 15min` 就能在开始满 4 小时的那个扫描周期取到仍在活动的会话。记录的结束时间仍是快照里的最后活动时间（`_time`），不是 score。
- 每条事件都刷新当前会话的快照，不只在切换时写。没有后续事件时，空闲 15 分钟仍能写出记录。
- 切换时只有该会话还在索引里才再次封存。维护进程已经取走的会话，后续事件不会把它放回索引，避免空闲或满 4 小时之后再写一条。spec 允许的重复只剩「写入成功、移出索引之前进程停了」；查询按会话键对数值取 `max`。不在存储层加幂等键。
- 扫描每 1 分钟一次。一轮内按每批最多 200 条排空到期会话，一批拼成多行 JSON、一次 `POST /insert/jsonline`；45 秒扫描预算用完或某批写入失败则停止，失败的那一批留在索引里，下一分钟再试。
- 只累计 `rum.application` 路径：每条事件 `events + 1`，`view` 再 `views + 1`，`error` 再 `errors + 1`。入口路由、版本、用户、环境取第一个非空的 `rum.view.name`、`rum.release`、`rum.user.id`、`rum.environment`。回放不增加这三个计数，也不覆盖这四个已有值；仍会更新 `last_seen`、流量类型和快照 TTL。
- 快照缺失（含过期）、字段损坏，或 member 不是 32 位十六进制，都计入 `core_rum_session_end_records_lost_total`，移出索引，打一条汇总 WARNING。不逐条、不写会话键。
- 不删除活会话 hash。维护进程只有会话键，删活 hash 会和正在切换的 Lua 抢同一条状态。
- Maintainer 用已有 `rum-maintainer` 身份连接会话库（默认 DB 1）。会话库 URL 为空是配置错误，进程退出。会话库暂时连不上不退出，扫描下一分钟重试，擦除和对账继续。
- 会话记录字段契约写在 `deploy/rum/OPS-DEPLOY.md`「会话结束记录」。

## Completion evidence

- `GOTOOLCHAIN=auto GOPROXY=https://goproxy.cn,direct make -C deploy/rum test`：`rumsessionprocessor`、`maintainer` 及同级包全部 `ok`。
- 同一范围 `go test -json -count=1 ./internal/rum/... ./internal/rumprivacy/... ./pkg/rum/...`：`passed=349 failed=0 skipped=0`。
- `GOTOOLCHAIN=auto GOPROXY=https://goproxy.cn,direct make -C deploy/rum validate`：compose config、gateway `validate`、`bklite-rum-gateway` / `bklite-rum-controller` / `bklite-rum-maintainer` 构建成功。
- 未起临时 Redis / VictoriaLogs 容器。删除命中用 HTTP 桩和现有过滤器验证。
- 吞吐修正：一轮内按每批最多 200 条排空。`make -C deploy/rum test` 全部 `ok`；`go test -json -count=1 ./internal/rum/... ./internal/rumprivacy/... ./pkg/rum/...` 为 `passed=352 failed=0 skipped=0`。`make -C deploy/rum validate` 通过。
