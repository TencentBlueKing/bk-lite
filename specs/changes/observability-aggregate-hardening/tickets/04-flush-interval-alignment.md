# 04 — Server 刷出间隔与采集端同源

Status: ready

Blocked by: 01, 02

**What to build:** 运维修改 `APM_AGG_FLUSH_INTERVAL` 或 `RUM_AGG_BATCH_TIMEOUT` 时，在 Server 设置同名变量即可让查询结束时间对齐，
不用改代码。

- [ ] `server/apps/apm/adapters/aggregate_red.py` 与 `server/apps/rum/services/aggregate_reads.py` 的刷出间隔改为读取同名环境变量，
  默认 60s / 10s；支持采集端使用的时长写法（如 `60s`、`1m`），非法值按默认值并记一条 WARN（不含变量以外的内容）
- [ ] 解析放在一个两边都能引用的位置，例如 `apps/core/aggregate_promql.py`，不新增配置抽象
- [ ] 单测：默认值、自定义值、非法值；保持现有查询结果契约
- [ ] 文档：上线说明的 Server 段与变量表、`aggregate-metrics-store.md` 写明两边必须一致
- [ ] sqlite 跑 `apps/apm/tests`、`apps/rum/tests`、`apps/core/tests`，对照 master 基线不新增失败

## Notes

- 日志遵守 `specs/capabilities/backend-engineering.md` §8；修改日志需要回归测试锁定模板与参数。

## Completion evidence

