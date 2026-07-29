# InfluxDB 监控接入指南

本能力通过 Telegraf `inputs.influxdb` 读取 InfluxDB v1 的 `/debug/vars` 运行时统计。

## 前置要求

- 目标是能够提供 `/debug/vars` 的 InfluxDB v1 实例，采集节点可访问其完整 HTTP(S) URL。
- 服务器地址必须包含协议、端口和 `/debug/vars` 路径。
- 若端点启用 Basic Auth，准备用户名和密码；未启用时两项均留空。
- HTTPS 可填写 CA、客户端证书和客户端密钥路径；这些路径必须存在于实际采集节点。

## 接入步骤

1. 从实际采集节点验证 `/debug/vars` URL 和可选认证。
2. 填写服务器地址、可选用户名/密码、采集间隔（默认 `60` 秒）和超时时间（默认 `30` 秒）。
3. HTTPS 场景按需填写 CA、客户端证书、客户端密钥和跳过证书校验开关。
4. 在监控对象表格中选择节点，填写服务器地址、实例名称和可选分组。
5. 保存后等待至少一个采集周期。

## 接入前校验

无认证端点：

```bash
curl --fail --silent --show-error "http://influxdb.example.com:8086/debug/vars"
```

Basic Auth 端点可使用下列命令，由 `curl` 交互式询问密码：

```bash
curl --fail --silent --show-error --user monitor "http://influxdb.example.com:8086/debug/vars"
```

请求应返回 `200` 和 JSON；`--fail` 会保留 `4xx/5xx` 失败状态。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 服务器地址 | 是 | 完整 URL，通常以 `/debug/vars` 结尾。 |
| 用户名、密码 | 否 | Basic Auth 启用时成对填写，否则留空。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 超时时间 | 是 | 单次请求超时，单位秒，默认 `30`。 |
| CA 证书路径 | 否 | 采集节点上的 CA 文件路径。 |
| 客户端证书路径 | 否 | 双向 TLS 的客户端证书路径。 |
| 客户端密钥路径 | 否 | 与客户端证书配套的密钥路径。 |
| 跳过证书校验 | 否 | 是否跳过服务端证书校验，默认关闭。 |
| 节点 | 是 | 能够访问目标 URL 且持有相应证书文件的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `influxdb_database_numSeries`
- `influxdb_httpd_writeReq_rate`
- `influxdb_httpd_pointsWrittenFail_rate`
- `influxdb_runtime_HeapAlloc`

## 常见问题

### 返回 `401`、`403` 或 `404`

- 核对认证是否启用、用户名和密码是否成对填写。
- 确认 URL 指向 InfluxDB v1 的 `/debug/vars`，不是根路径或 v2 API。

### HTTPS 失败

- 证书路径由采集节点读取，不能填写只存在于其他主机的路径。
- 仅在明确接受风险时使用跳过证书校验开关。

### 只有部分数据

- 所有数据来自 `/debug/vars` 返回体；先确认目标版本实际返回对应统计字段。
- 超时会导致整次请求失败，可结合接口耗时调整页面超时时间。
