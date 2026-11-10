# 03 — RUM 路由准入在 Redis 故障时不拖慢收数

Status: ready

Blocked by: None

**What to build:** Redis 不可用时，网关收数延迟不随记录数线性增加，日志不刷屏；溢出路由缓存内存有上限。

- [ ] `rumroutecap` 在 Redis 调用失败后进入短暂熔断（时长常量或配置，量级为数秒）；熔断期间未缓存路由直接记为「其他」，不调用 Redis
- [ ] 失败日志按时间窗汇总为一条 WARN，带失败次数、`failed_stage`、`error_type`，不含 Redis 地址、密码、路由原文以外的载荷
- [ ] 本地溢出缓存设条目上限，并定期清理过期项（不依赖同一路由再次出现）；准入缓存不改
- [ ] 失败计数指标保持现有名称和语义
- [ ] RUM 镜像版本升到 `0.1.0-bklite.3`，更新 Makefile、部署文档和上线说明中的引用
- [ ] Go 单测：熔断期间不调用 Redis、熔断结束后恢复调用、日志汇总、溢出缓存不超过上限且过期项被清理；`make -C deploy/rum test` 通过

## Notes

- 不改 100 条上限、35 天 TTL 和 Lua 准入逻辑，也不改路由清洗规则。
- 测试用 miniredis 或现有测试替身，不连接用户本机 6379。

## Completion evidence

