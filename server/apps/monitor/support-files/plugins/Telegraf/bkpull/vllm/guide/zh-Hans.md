# vLLM 监控接入指南

本插件由 Telegraf 直接拉取 vLLM OpenAI 兼容 API server 暴露的 Prometheus 指标端点。页面要求填写包含协议、主机、端口和指标路径的完整 URL。

## 前置要求

- 目标为已启动的 vLLM API server，并已暴露 `/metrics` 端点（通常与 OpenAI 兼容 API 同端口，例如 `8000`）。
- 官方文档未要求额外启用开关；若反向代理屏蔽了 `/metrics`，需先放通。
- 采集节点能够访问该完整 URL；不要只验证主机端口。
- 指标命名基于 vLLM V1 文档中的 `vllm:` 前缀（例如 `vllm:kv_cache_usage_perc`）。旧版 `gpu_cache_*` 名称不在本插件指标表中。
- HTTPS 场景下，CA、客户端证书和客户端私钥文件必须位于采集节点上，且采集进程有读取权限。
- 优先使用可信 CA。仅在临时排障且已接受证书伪造风险时开启“跳过证书校验”。

## 接入步骤

1. 在采集节点完成“接入前校验”，确认完整指标 URL 返回成功且包含 `vllm:` 前缀指标。
2. 在 vLLM 配置页填写 URL、TLS 文件路径（如需）、采集间隔和证书校验策略。
3. 在监控对象表格中选择节点，填写同一个完整 URL、实例名称和可选分组。
4. 保存配置并等待至少一个采集周期。默认采集间隔为 `60` 秒。

## 接入前校验

HTTP 示例：

```bash
VLLM_METRICS_URL=http://127.0.0.1:8000/metrics
curl --fail-with-body --silent --show-error "$VLLM_METRICS_URL" --output /tmp/vllm-metrics.txt
grep -E -m 8 '^# (HELP|TYPE) vllm:' /tmp/vllm-metrics.txt
grep -E -m 8 '^vllm:' /tmp/vllm-metrics.txt
```

HTTPS 双向认证示例：

```bash
VLLM_METRICS_URL=https://vllm.example.com:8000/metrics
curl --fail-with-body --silent --show-error \
  --cacert /etc/ssl/vllm/ca.pem \
  --cert /etc/ssl/vllm/client.pem \
  --key /etc/ssl/vllm/client-key.pem \
  "$VLLM_METRICS_URL" --output /tmp/vllm-metrics.txt
grep -E -m 8 '^vllm:' /tmp/vllm-metrics.txt
```

`curl` 必须以退出码 `0` 结束，且输出应包含 `vllm:` 前缀的 Prometheus 指标。不要使用仅能证明 TCP 端口开放的结果替代完整 URL 校验。

建议同时记录版本信息，便于后续对照官方指标变更：

```bash
# 按实际部署方式选择其一
vllm --version
# 或从容器/镜像标签记录版本
```

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| URL | 是 | 无 | 完整的 `http://` 或 `https://` 指标 URL，例如 `http://127.0.0.1:8000/metrics`。 |
| CA 证书路径 | 否 | 无 | HTTPS 服务端证书的 CA 文件路径，文件位于采集节点。 |
| 客户端证书路径 | 否 | 无 | mTLS 客户端证书路径，应与客户端密钥成对填写。 |
| 客户端密钥路径 | 否 | 无 | mTLS 客户端私钥路径，应限制文件读取权限。 |
| 间隔 | 是 | `60` 秒 | Telegraf 拉取周期，最小值为 `1` 秒。 |
| 跳过证书校验 | 否 | 关闭 | 开启后不验证 HTTPS 服务端证书。生产环境应保持关闭。 |
| 节点 | 是 | 无 | 执行拉取的采集节点。 |
| URL（监控对象） | 是 | 无 | 当前实例的完整指标 URL；同一接入配置中必须唯一。 |
| 实例名称 | 是 | 无 | 平台中的展示名称，默认可由 URL 带出后再调整。 |
| 组 | 否 | 无 | 实例所属分组。 |

模板固定将请求超时和响应超时设为 `30` 秒；页面没有拆分的协议、主机、端口或指标路径字段。

## 落名说明（写入 VictoriaMetrics 后）

Telegraf `inputs.prometheus`（默认 `metric_version=1`，与本仓库 etcd bkpull 模板一致）将 Prometheus 类型写入 field，经 Influx 线路协议入库后，查询名遵循 `{上游指标名}_{类型}`。对本插件已实采验证（Telegraf 1.32.3）的示例：

| 上游 Prometheus 名 | 类型 | 平台查询名 |
| --- | --- | --- |
| `vllm:num_requests_running` | gauge | `vllm:num_requests_running_gauge` |
| `vllm:num_requests_waiting` | gauge | `vllm:num_requests_waiting_gauge` |
| `vllm:kv_cache_usage_perc` | gauge | `vllm:kv_cache_usage_perc_gauge` |
| `vllm:prompt_tokens_total` | counter | `vllm:prompt_tokens_total_counter` |
| `vllm:generation_tokens_total` | counter | `vllm:generation_tokens_total_counter` |
| `vllm:time_to_first_token_seconds` | histogram | `vllm:time_to_first_token_seconds_count` / `_sum` / `_<le>` |
| `vllm:inter_token_latency_seconds` | histogram | `vllm:inter_token_latency_seconds_count` / `_sum` / `_<le>` |
| `vllm:request_prompt_tokens` | histogram | `vllm:request_prompt_tokens_count` / `_sum` / `_<le>` |
| `vllm:request_generation_tokens` | histogram | `vllm:request_generation_tokens_count` / `_sum` / `_<le>` |
| `vllm:iteration_tokens_total` | histogram | `vllm:iteration_tokens_total_count` / `_sum` / `_<le>` |

冒号前缀会被保留，不会改写成下划线。

## 接入后验证

1. 等待至少一个采集周期，在平台确认实例状态已更新。
2. 在指标页确认以下已注册指标中至少有与目标实例匹配的数据：
   - `vllm:num_requests_running_gauge`
   - `vllm:num_requests_waiting_gauge`
   - `vllm:kv_cache_usage_perc_gauge`
   - `vllm:generation_tokens_total_counter_rate`
   - `vllm:time_to_first_token_seconds_p99`
   - `vllm:inter_token_latency_seconds_p99`
   - `vllm:request_prompt_tokens_p99`
   - `vllm:request_generation_tokens_p99`
   - `vllm:request_success_total_counter_rate`
3. 若实例存在但指标无数据，重新执行完整 URL 校验，并确认响应中确有 `vllm:` 前缀指标。

## 常见问题

### URL 返回 404

页面不会自动补 `/metrics`。确认 URL 中已经包含目标实际暴露的指标路径；若经反向代理，确认未拦截 `/metrics`。

### 能打开 API 但没有 `vllm:` 指标

确认访问的是 vLLM API server 的 metrics 端点，而不是仅健康检查或其它服务。用 `grep '^vllm:'` 核对响应内容。

### HTTPS 握手或证书校验失败

核对 CA 链、证书有效期、主机名和 mTLS 证书/密钥配对。优先修复证书，不要把长期跳过校验当作解决方案。

### 请求超时

确认采集节点到目标主机网络可达，并适当增大页面“间隔”；模板内 HTTP 超时固定为 `30` 秒。

### 指标名与文档不一致

若目标仍暴露已弃用的 `vllm:gpu_cache_usage_perc` 等旧名，本插件默认查询的是 V1 新名 `vllm:kv_cache_usage_perc_gauge`。请升级 vLLM 或按实采结果调整指标表。
