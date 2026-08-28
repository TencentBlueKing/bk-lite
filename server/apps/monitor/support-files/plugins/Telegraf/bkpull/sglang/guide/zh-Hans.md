# SGLang 监控接入指南

本插件由 Telegraf 直接拉取 SGLang 服务暴露的 Prometheus 指标端点。页面要求填写包含协议、主机、端口和指标路径的完整 URL。

## 前置要求

- 启动 SGLang 时必须加上 `--enable-metrics`，否则不会暴露 `/metrics`。
- 官方文档示例端口为 `30000`，指标地址形如 `http://<host>:30000/metrics`。
- 可选：`--enable-mfu-metrics` 用于 MFU 相关计数器（本插件首批指标表未包含 MFU 系列）。
- 采集节点能够访问该完整 URL；不要只验证主机端口。
- 当前官方文档示例使用 `sglang:` 冒号前缀；历史上曾出现 `sglang_*` 命名，若实采结果不同，需按目标版本调整指标表。
- HTTPS 场景下，CA、客户端证书和客户端私钥文件必须位于采集节点上，且采集进程有读取权限。

## 接入步骤

1. 确认目标进程已使用 `--enable-metrics` 启动。
2. 在采集节点完成“接入前校验”，确认完整指标 URL 返回成功且包含 `sglang:` 前缀指标。
3. 在 SGLang 配置页填写 URL、TLS（如需）、采集间隔和证书校验策略。
4. 在监控对象表格中选择节点，填写同一个完整 URL、实例名称和可选分组。
5. 保存配置并等待至少一个采集周期。默认采集间隔为 `60` 秒。

## 接入前校验

HTTP 示例：

```bash
SGLANG_METRICS_URL=http://127.0.0.1:30000/metrics
curl --fail-with-body --silent --show-error "$SGLANG_METRICS_URL" --output /tmp/sglang-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) sglang:' /tmp/sglang-metrics.txt
grep -E -m 8 '^sglang:' /tmp/sglang-metrics.txt
```

建议记录启动命令与版本：

```bash
# 示例启动（摘自官方文档）
python -m sglang.launch_server \
  --model-path <your_model_path> \
  --port 30000 \
  --enable-metrics
```

`curl` 必须以退出码 `0` 结束，且输出应包含 `sglang:` 前缀指标。若返回非 metrics 文本或空，优先检查是否遗漏 `--enable-metrics`。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| URL | 是 | 无 | 完整的 `http://` 或 `https://` 指标 URL，例如 `http://127.0.0.1:30000/metrics`。 |
| CA 证书路径 | 否 | 无 | HTTPS 服务端证书的 CA 文件路径，文件位于采集节点。 |
| 客户端证书路径 | 否 | 无 | mTLS 客户端证书路径，应与客户端密钥成对填写。 |
| 客户端密钥路径 | 否 | 无 | mTLS 客户端私钥路径。 |
| 间隔 | 是 | `60` 秒 | Telegraf 拉取周期，最小值为 `1` 秒。 |
| 跳过证书校验 | 否 | 关闭 | 开启后不验证 HTTPS 服务端证书。生产环境应保持关闭。 |
| 节点 | 是 | 无 | 执行拉取的采集节点。 |
| URL（监控对象） | 是 | 无 | 当前实例的完整指标 URL；同一接入配置中必须唯一。 |
| 实例名称 | 是 | 无 | 平台中的展示名称。 |
| 组 | 否 | 无 | 实例所属分组。 |

模板固定将请求超时和响应超时设为 `30` 秒。

## 落名说明（写入 VictoriaMetrics 后）

Telegraf `inputs.prometheus`（默认 `metric_version=1`，与 etcd bkpull 模板一致）落名遵循 `{上游指标名}_{类型}`。对本插件已实采验证（Telegraf 1.32.3）的示例：

| 上游 Prometheus 名 | 类型 | 平台查询名 |
| --- | --- | --- |
| `sglang:num_running_reqs` | gauge | `sglang:num_running_reqs_gauge` |
| `sglang:num_queue_reqs` | gauge | `sglang:num_queue_reqs_gauge` |
| `sglang:prompt_tokens_total` | counter | `sglang:prompt_tokens_total_counter` |
| `sglang:time_to_first_token_seconds` | histogram | `sglang:time_to_first_token_seconds_count` / `_sum` / `_<le>` |
| `sglang:e2e_request_latency_seconds` | histogram | `sglang:e2e_request_latency_seconds_count` / `_sum` / `_<le>` |

冒号前缀会被保留。

## 接入后验证

1. 等待至少一个采集周期，在平台确认实例状态已更新。
2. 在指标页确认以下已注册指标中至少有数据：
   - `sglang:num_running_reqs_gauge`
   - `sglang:num_queue_reqs_gauge`
   - `sglang:cache_hit_rate_gauge`
   - `sglang:gen_throughput_gauge`
   - `sglang:time_to_first_token_seconds_p99`
   - `sglang:time_to_first_token_seconds_p90`
   - `sglang:e2e_request_latency_seconds_p90`
3. 若无数据，重新执行完整 URL 校验，并确认启动参数含 `--enable-metrics`。

## 常见问题

### `/metrics` 返回 404 或非指标正文

确认启动命令包含 `--enable-metrics`，且 URL 指向服务端口上的 `/metrics`。

### 指标前缀是 `sglang_` 而不是 `sglang:`

部分历史版本或中间采集层可能改写冒号。以目标环境 `curl` 与 Telegraf 落名为准，必要时调整 `metrics.json`。

### HTTPS / 超时

与 etcd/vLLM 相同：优先修复证书与网络；模板 HTTP 超时为 `30` 秒。
