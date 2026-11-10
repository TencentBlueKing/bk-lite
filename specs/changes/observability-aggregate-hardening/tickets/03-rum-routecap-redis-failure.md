# 03 — RUM 路由准入在 Redis 故障时不拖慢收数

Status: done

Blocked by: None

**What to build:** Redis 不可用时，网关收数延迟不随记录数线性增加，日志不刷屏；溢出路由缓存内存有上限。

- [x] `rumroutecap` 在 Redis 调用失败后进入短暂熔断（时长常量或配置，量级为数秒）；熔断期间未缓存路由直接记为「其他」，不调用 Redis
- [x] 失败日志：窗口内第一次失败立即一条 WARN；同窗口后续失败在窗口到期后的下一次路由处理或 Shutdown 时再汇总一条（只含未输出的次数），带 `failure_count`、`failed_stage`、`error_type`，不含 Redis 地址、密码、路由原文或载荷
- [x] 本地溢出缓存设条目上限，并定期清理过期项（不依赖同一路由再次出现）；准入缓存不改
- [x] 失败计数指标保持现有名称和语义
- [x] RUM 镜像版本升到 `0.1.0-bklite.3`，更新 Makefile、部署文档和上线说明中的引用
- [x] Go 单测：熔断期间不调用 Redis、熔断结束后恢复调用、日志汇总、溢出缓存不超过上限且过期项被清理；`make -C deploy/rum test` 通过

## Notes

- 不改 100 条上限、35 天 TTL 和 Lua 准入逻辑，也不改路由清洗规则。
- 测试用 miniredis 或现有测试替身，不连接用户本机 6379。

## Completion evidence

熔断时长是常量 `redisCircuitOpenFor = 5s`，不做成配置。`Config` 只有 Redis 地址、口令文件和分片，没有同类时长旋钮。Redis `admit` 失败后打开熔断；到期（`now` 不早于 `openUntil`）后下一次未缓存路由重新调用 Redis。已准入的路由仍走本地缓存，不进熔断。启动时 Ping 失败也会打开熔断，避免刚启动的一批事件各自等满 200ms 超时；这条仍是原来的单次 WARN，不计入查找失败指标。

日志窗口是常量 `failureLogWindow = 5s`。窗口内第一次查找失败立即打一条 WARN，`failure_count=1`。同一窗口里后面的失败只累计，不逐条打。窗口到期后，下一次 `routeFor`（不论这次 Redis 成功还是失败）或 `Shutdown` 再打一条汇总，`failure_count` 只含还没输出过的次数。一个窗口最多约两条。没有后台 goroutine，也不用等下一次故障才看得到开头。字段仍是 `failed_stage=route_admission`、`error_type`（只有 `%T`）、`failure_count`。不写 Redis 地址、口令、错误字符串、路由原文或事件载荷。指标名仍是 `core_rum_aggregate_route_redis_failures`，语义仍是「因为 Redis 不可用而被记为其他的查找」：熔断期间跳过 Redis 的查找也计数。

溢出缓存上限 `overflowCacheLimit = 1024`。满了不再写入新的溢出项，已缓存的溢出路由保留。淘汰旧项会把热点溢出路由打回 Redis；新路由这次本来就会记为「其他」，名额空出来之后可以再缓存。清理不靠后台 goroutine：每次 `routeFor` 若距上次扫描已满 `overflowSweepInterval`（1 分钟，与溢出 TTL 相同）就扫掉全部过期项，不需要同一条路由再出现。写不进去且缓存里全是过期项时会强制再扫一次，避免过期项占满名额。准入缓存没有上限，逻辑未改。100 条上限、35 天 TTL、Lua 和路由清洗都没改。

镜像标签改为 `bklite/rum-collector:0.1.0-bklite.3`（Makefile、compose、`.env.example`、OPS-DEPLOY、README、契约默认镜像、聚合库运维规则、上线说明、ADR 0011 的当前标签）。ADR 里「在 bklite.2 上补验」和已完成的 `observability-aggregate-metrics` ticket 05 是当时的验证记录，没有改。

日志时机在复核后改过：第一次失败立即可见，汇总不再等下一次故障。复核后的验证：

- `cd deploy/rum/collector && go test ./internal/rum/components/rumroutecap/ -count=1`：ok，1.351s。
- `cd deploy/rum/collector && go test -race ./internal/rum/components/rumroutecap/ -count=1`：ok，2.466s。Makefile 的 `test` 没有 `-race`。
- `make -C deploy/rum test`：退出码 0。包含 collector、controller、maintainer。`aggregatecontract` 未设置 `RUN_RUM_AGG_CONTRACT=1`，没有起容器。
- 复核通过后，用修正后的代码构建 `bklite/rum-collector:0.1.0-bklite.3`，digest `sha256:64f93c0ed7ed`。

