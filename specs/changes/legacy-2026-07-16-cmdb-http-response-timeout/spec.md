# Historical Superpowers change: 2026-07-16-cmdb-http-response-timeout

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-16-cmdb-http-response-timeout-design.md

## 背景

CMDB 配置采集通过 Telegraf HTTP 输入调用 Stargazer。当前 `BaseNodeParams` 将 `response_timeout` 固定为 10 秒，Stargazer 则在同一个 HTTP 请求中逐个拆分并入队多个目标。任务 296 扫描 `/24` 网段时，线上观察到单轮只生成到 `10.10.69.138`，后续目标（例如 `10.10.69.247`）未进入 Redis 队列。

## 目标

- 将所有 CMDB HTTP 配置采集的响应等待时间从 10 秒调整为 30 秒。
- 为大网段、多 IP 任务提供足够的任务拆分和入队时间。
- 不改变采集协议自身的超时和 ARQ 整任务超时。

## 方案

在 `server/apps/cmdb/node_configs/base.py` 中将 `BaseNodeParams.response_timeout` 的默认值由 10 调整为 30。保留现有模板和下发链路：

```text
BaseNodeParams.response_timeout=30
  → push_params() 模板上下文
  → base.child.toml.j2
  → Telegraf response_timeout="30s"
```

本次不增加页面字段或环境变量，也不为网络采集建立单独覆盖，确保所有使用同一 HTTP 下发机制的 CMDB 多目标任务获得一致行为。

## 边界与影响

- 仅影响 Telegraf 等待 Stargazer HTTP 响应的时间。
- 不修改页面上的采集 `timeout`；任务 296 仍保持 SNMP 单请求 5 秒。
- 不修改 `TASK_JOB_TIMEOUT`；线上 ARQ 整任务超时仍约为 300 秒。
- Stargazer 无响应时，Telegraf 最长等待时间将增加 20 秒。
- 已下发的 Telegraf 配置不会自动变化，需要重新同步或重新下发相关采集任务。

## 测试与验收

1. 新增回归测试，实例化 CMDB 节点参数并生成配置。
2. 先验证测试在当前 10 秒实现下失败。
3. 将全局默认值调整为 30 后，验证生成内容包含 `response_timeout = "30s"`。
4. 运行相关 CMDB 节点参数定向测试。
5. 线上重新同步任务 296 后，确认生成过程能够覆盖 `10.10.69.247`。

## 回滚

将 `BaseNodeParams.response_timeout` 恢复为 10，并重新同步相关任务配置即可。该调整不涉及数据库结构和数据迁移。
