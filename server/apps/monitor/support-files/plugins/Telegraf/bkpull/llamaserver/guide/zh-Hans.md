# llama-server 监控接入指南

本插件由 Telegraf 直接拉取 llama.cpp `llama-server` 暴露的 Prometheus 指标端点。页面要求填写包含协议、主机、端口和指标路径的完整 URL。

## 前置要求

- 启动 `llama-server` 时必须加上 `--metrics`（或环境变量 `LLAMA_ARG_ENDPOINT_METRICS`），否则 `/metrics` 不可用。
- 默认示例端口常见为 `8080`，指标地址形如 `http://<host>:8080/metrics`。
- 采集节点能够访问该完整 URL。
- Router 模式下，主进程与子模型进程可能各自暴露 metrics，且可能需要 `?model=` 查询参数；请先确认实际应刮取的端口与 URL。
- HTTPS 场景下，证书材料必须位于采集节点且对采集进程可读。

## 接入步骤

1. 确认目标以 `--metrics` 启动。
2. 在采集节点完成“接入前校验”，确认响应包含 `llamacpp:` 前缀指标。
3. 在 LlamaServer 配置页填写 URL、TLS（如需）、间隔与证书校验策略。
4. 选择采集节点，填写同一完整 URL、实例名称和可选分组。
5. 保存并等待至少一个采集周期（默认 `60` 秒）。

## 接入前校验

```bash
LLAMA_METRICS_URL=http://127.0.0.1:8080/metrics
curl --fail-with-body --silent --show-error "$LLAMA_METRICS_URL" --output /tmp/llamaserver-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) llamacpp:' /tmp/llamaserver-metrics.txt
grep -E -m 8 '^llamacpp:' /tmp/llamaserver-metrics.txt
```

若未开启 metrics，官方行为通常返回不支持该端点的错误；请改用带 `--metrics` 的启动参数后重试。

建议记录构建/版本信息：

```bash
llama-server --version 2>/dev/null || true
# 或记录镜像 tag / 提交号
```

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| URL | 是 | 无 | 完整指标 URL，例如 `http://127.0.0.1:8080/metrics`。 |
| CA 证书路径 | 否 | 无 | HTTPS CA 路径。 |
| 客户端证书路径 | 否 | 无 | mTLS 客户端证书。 |
| 客户端密钥路径 | 否 | 无 | mTLS 客户端私钥。 |
| 间隔 | 是 | `60` 秒 | Telegraf 拉取周期。 |
| 跳过证书校验 | 否 | 关闭 | 生产环境保持关闭。 |
| 节点 | 是 | 无 | 采集节点。 |
| URL（监控对象） | 是 | 无 | 实例完整指标 URL，需唯一。 |
| 实例名称 | 是 | 无 | 展示名称。 |
| 组 | 否 | 无 | 可选分组。 |

模板 HTTP 超时固定为 `30` 秒。

## 落名说明（写入 VictoriaMetrics 后）

Telegraf `inputs.prometheus`（默认 `metric_version=1`）落名遵循 `{上游指标名}_{类型}`。对本插件已实采验证（Telegraf 1.32.3）的示例：

| 上游 Prometheus 名 | 类型 | 平台查询名 |
| --- | --- | --- |
| `llamacpp:requests_processing` | gauge | `llamacpp:requests_processing_gauge` |
| `llamacpp:kv_cache_usage_ratio` | gauge | `llamacpp:kv_cache_usage_ratio_gauge` |
| `llamacpp:prompt_tokens_total` | counter | `llamacpp:prompt_tokens_total_counter` |
| `llamacpp:tokens_predicted_total` | counter | `llamacpp:tokens_predicted_total_counter` |
| `llamacpp:n_decode_total` | counter | `llamacpp:n_decode_total_counter` |
| `llamacpp:n_busy_slots_per_decode` | counter | `llamacpp:n_busy_slots_per_decode_counter` |

冒号前缀会被保留。

> **注意**：较新版本 llama.cpp 可能已移除 `llamacpp:kv_cache_usage_ratio`；若目标无此指标，KV 相关面板/告警可能无数据，以实采 `/metrics` 为准。

## 接入后验证

1. 等待至少一个采集周期，确认实例状态更新。
2. 在指标页确认以下指标有数据：
   - `llamacpp:requests_processing_gauge`
   - `llamacpp:requests_deferred_gauge`
   - `llamacpp:predicted_tokens_seconds_gauge`
   - `llamacpp:n_decode_total_counter_rate`
   - `llamacpp:n_busy_slots_per_decode_gauge`
   - `llamacpp:tokens_per_decode_gauge`
3. 若无数据，确认 `--metrics` 已开启，并核对 Router 模式下刮取的端口。

## 常见问题

### `/metrics` 提示不支持

未加 `--metrics`。按官方 README 启用后重试。

### Router 模式指标不全

主进程与子模型进程可能分别暴露 metrics。确认业务需要的是聚合端点还是单模型端口，并在 URL 中填写对应地址（必要时带 `model` 查询参数）。

### HTTPS / 超时

优先修复证书与网络；模板超时为 `30` 秒。
