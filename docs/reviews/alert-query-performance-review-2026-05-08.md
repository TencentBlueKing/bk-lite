# 告警查询性能 Review（2026-05-08）

## 结论

DuckDB 聚合链路存在一处链路级严重技术债务：聚合任务会按“每个活跃策略”重复从 PostgreSQL 拉取窗口内事件、在 Python 中整批序列化、再整批装载进 DuckDB 内存表，但当前策略配置对 `window_size` 没有代码级上限约束，也没有任何输入行数上限或共享输入复用。

## 仓库证据

- `server/apps/alerts/aggregation/processor/aggregation_processor.py`
  - `process_aggregation()` 会遍历全部 `is_active=True` 的策略并逐个调用 `_process_strategy(...)`。
  - `get_events_for_strategy()` 直接使用 `params["window_size"]` 计算 `received_at__gte=cutoff_time`，没有最大窗口保护。
  - `_aggregate_for_dimensions()` 每个策略都会调用 `self.db_conn.load_events_to_memory(events)`，随后执行一次 DuckDB SQL。
- `server/apps/alerts/aggregation/engine/connection.py`
  - `load_events_to_memory()` 会把 QuerySet 直接 `values(...) -> list(...)` 全量拉到 Python。
  - 之后逐条 `json.dumps(...)`，再构造成 `pandas.DataFrame`，最后 `DROP TABLE/CREATE TABLE` 重建整张 `events_table`。
- `server/apps/alerts/aggregation/window/factory.py`
  - `create_from_strategy()` 直接信任 `params["window_size"]`，没有上限、没有非正数保护。
- `server/apps/alerts/serializers/strategy.py`
  - 仅对 `missing_detection` 做参数校验；普通聚合策略的 `params.window_size`、`group_by`、`time_out` 没有任何规模约束。

## 影响范围

- 活跃策略一多，且窗口有重叠时，会重复执行“PG 扫窗口事件 -> Python 序列化 -> DataFrame 构造 -> DuckDB 重装表”的整套链路。
- 单个策略只要把 `window_size` 配得过大，就会同步放大 PostgreSQL 读取量、Python 内存占用和 DuckDB 装载成本。
- 这不是局部慢查询，而是策略数量与窗口大小共同驱动的乘法型放大，直接影响聚合时延、Worker 稳定性和排障成本。

## 本次不直接修复的原因

这条债务已经是聚合执行模型问题，不是单点 if/else 能安全补掉的缺陷。直接在本轮硬加窗口上限或粗暴裁剪输入，会改变现有策略语义和告警覆盖范围；而要做真正闭环修复，需要同时重构策略参数契约、任务切片方式与输入复用策略。

## 建议后续处理

1. 给普通聚合策略建立明确的 `window_size` 合法区间与最大输入预算。
2. 把“按策略重复装载事件”改成“按时间窗/来源共享候选集，再做策略内过滤”。
3. 在聚合执行链路记录每次策略的输入行数、装载耗时、DuckDB 执行耗时，便于后续治理和告警。
