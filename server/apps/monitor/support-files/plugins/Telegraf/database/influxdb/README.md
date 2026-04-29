# InfluxDB 监控说明

## 监控概述

InfluxDB 监控用于帮助使用者持续观察 InfluxDB v1 实例的基数规模、HTTP 服务质量、写入链路健康度、查询请求压力和运行时内存占用情况，适合用于以下场景：

- 日常巡检时快速判断实例是否稳定
- 容量评估时判断序列规模是否持续膨胀
- 写入异常排查时识别丢点、持久化失败、客户端错误和服务端错误
- 性能分析时观察查询与写入压力是否异常增大
- 内存风险排查时判断进程堆内存是否持续升高

## 监控价值

本监控对象围绕 InfluxDB v1 的核心运行路径进行设计，重点覆盖以下几个方面：

- 序列规模是否持续增长并带来基数压力
- HTTP 接口是否出现认证失败、客户端错误或服务端错误
- 写入请求是否出现丢点或持久化失败
- 查询与写入请求压力是否显著升高
- 运行时堆内存是否持续增长并带来 GC 压力

## 功能简介

用于采集 InfluxDB v1 的关键运行指标，覆盖序列规模、HTTP 访问质量、写入链路、查询请求与运行时内存等核心场景，帮助使用者及时发现异常、评估容量风险并定位性能瓶颈。

## 接入方式

| 项目 | 内容 |
| --- | --- |
| 监控对象 | InfluxDB |
| 采集方式 | 由 Telegraf 采集器基于 InfluxDB v1 `debug/vars` 端点主动拉取采集 |
| 数据来源 | InfluxDB v1 暴露的 `/debug/vars` 接口 |
| 默认采集地址 | `http(s)://<host>:8086/debug/vars` |

## 前置要求

- 当前插件面向 InfluxDB v1，依赖实例暴露 `debug/vars` 端点。
- 采集器到目标地址必须网络可达。
- 页面中的“服务器地址”需要填写完整 URL，例如 `http://10.0.0.20:8086/debug/vars`。
- 如果目标端启用了 Basic Auth 或 HTTPS，需要提前确认用户名、密码和证书文件路径。

## 接入步骤

1. 先确认目标实例可访问 `debug/vars` 接口。
2. 在监控接入页面选择 `InfluxDB` 插件。
3. 填写完整的服务器地址和采集间隔。
4. 如目标端开启认证或 HTTPS，再补充用户名、密码和 TLS 字段。
5. 保存配置后，等待一个采集周期，确认实例开始上报指标。

### 1. 接入前验证

无认证 HTTP 场景可先执行：

```bash
curl http://<host>:8086/debug/vars
```

Basic Auth 场景可先执行：

```bash
curl -u <username>:<password> http://<host>:8086/debug/vars
```

HTTPS 场景可先执行：

```bash
curl --cacert /path/to/ca.pem https://<host>:8086/debug/vars
```

满足以下任一情况即可认为端点基本可用：

- 返回状态码为 `200`
- 响应内容为 JSON，且包含 `database`、`httpd`、`runtime` 等字段

### 2. 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 服务器地址 `server` | 是 | 填写完整 URL，例如 `http://10.0.0.20:8086/debug/vars`。 |
| 用户名 `username` | 否 | 仅在目标端启用 Basic Auth 时填写。 |
| 密码 `ENV_PASSWORD` | 否 | 仅在目标端启用 Basic Auth 时填写。 |
| 间隔 `interval` | 是 | 采集周期，单位秒，默认 `10`。 |
| CA 证书路径 `tls_ca` | 否 | HTTPS 场景下校验服务端证书使用。 |
| 客户端证书路径 `tls_cert` | 否 | 双向认证场景下使用。 |
| 客户端密钥路径 `tls_key` | 否 | 双向认证场景下使用。 |
| 跳过证书校验 `insecure_skip_verify` | 否 | 仅建议在测试或临时排障时使用。 |

### 3. 最小配置示例

无认证 HTTP：

```text
服务器地址: http://10.0.0.20:8086/debug/vars
间隔: 10
```

Basic Auth：

```text
服务器地址: http://10.0.0.20:8086/debug/vars
用户名: monitor
密码: ******
间隔: 10
```

HTTPS：

```text
服务器地址: https://influxdb.example.com:8086/debug/vars
间隔: 10
CA证书路径: /etc/ssl/influxdb/ca.pem
跳过证书校验: 关闭
```

## 接入校验

保存接入后，建议按以下顺序检查：

1. 实例列表中已出现对应 InfluxDB 实例，实例名称通常取服务器地址中的主机部分。
2. 一个采集周期后，可查询到 `influxdb_database_numSeries`、`influxdb_httpd_writeReq_rate`、`influxdb_runtime_HeapAlloc` 等指标。
3. 若平台支持查看最近数据，确认最近 5 分钟内持续有 InfluxDB 指标上报。

## 常见接入问题

| 现象 | 常见原因 | 排查建议 |
| --- | --- | --- |
| 返回 `401` 或 `403` | 用户名密码错误，或目标端启用了认证 | 用 `curl -u` 先验证账号是否可访问 `debug/vars`。 |
| 返回 `404` | 地址不是 `debug/vars` 端点 | 检查是否误填为根路径、查询接口或 v2 接口。 |
| 返回非 JSON 内容 | 接入了反向代理首页或错误页面 | 确认填写的是完整 `debug/vars` URL。 |
| HTTPS 握手失败 | CA 或证书配置不正确 | 校验证书链、域名匹配关系和证书路径。 |
| 接入成功但没有指标 | 目标端不是 InfluxDB v1，或 `debug/vars` 未正常暴露 | 先确认接口返回内容中包含 `database`、`httpd`、`runtime` 字段。 |

## 口径说明

- 当前文档仅包含首批核心指标，不包含更深入的存储引擎、缓存、WAL 段和查询执行器细粒度指标。
- 频率类指标统一基于最近 5 分钟窗口计算，事件与请求类速率单位使用 `cps`。
- 容量类指标使用产品标准单位 `bytes`，页面会按 `B/KiB/MiB/GiB` 自动展示。

## 建议优先关注指标

如果需要快速判断 InfluxDB 是否处于健康状态，建议优先关注以下指标：

- `influxdb_database_numSeries`：判断序列规模是否进入高基数风险区
- `influxdb_httpd_pointsWrittenFail_rate`：判断写入数据是否出现持久化失败
- `influxdb_httpd_pointsWrittenDropped_rate`：判断写入链路是否开始丢点
- `influxdb_runtime_HeapAlloc`：判断进程堆内存是否持续膨胀
- `influxdb_httpd_writeReq_rate`：判断写入压力是否明显升高
- `influxdb_httpd_queryReq_rate`：判断查询压力是否明显升高

## 快速判断思路

如果只想快速判断当前 InfluxDB 实例是否健康，建议按下面顺序查看：

1. 先看“写入接口持久化失败速率”和“写点丢弃速率”，确认写入链路是否正常。
2. 再看“序列数”，确认是否存在高基数膨胀风险。
3. 然后看“Runtime 堆已分配内存”，确认进程内存是否持续走高。
4. 最后结合“写入请求速率”和“查询请求速率”，判断是否为业务流量增长导致的压力变化。

## 指标清单

### 基数与容量

用于判断 InfluxDB 的序列规模是否持续增长，是发现高基数风险和容量压力的关键分组。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 序列数 | `influxdb_database_numSeries` | Number | `counts` | 是否持续增长、是否接近阈值 | 表示单个数据库中的序列总数，是 InfluxDB 最重要的基数风险指标之一。序列数过高通常会带来内存占用上升、索引压力增大和查询性能下降。 |

### HTTP 服务质量

用于观察 HTTP 接口是否出现认证异常、客户端请求异常以及写入链路质量问题。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| HTTP 认证失败速率 | `influxdb_httpd_authFail_rate` | Number | `cps` | 是否突增 | 表示最近 5 分钟 HTTP 接口认证失败的平均速率。突增通常意味着访问配置错误、凭据问题或异常尝试。 |
| HTTP 4XX 错误速率 | `influxdb_httpd_clientError_rate` | Number | `cps` | 是否持续升高 | 表示最近 5 分钟客户端请求导致 4XX 错误的平均速率。持续升高通常说明请求参数错误、接口使用方式异常或上游调用不规范。 |
| HTTP 5XX 错误速率 | `influxdb_httpd_serverError_rate` | Number | `cps` | 是否持续升高 | 表示最近 5 分钟服务端处理请求返回 5XX 的平均速率。持续升高通常说明实例内部处理异常、资源压力升高或服务端逻辑故障。 |
| 写点丢弃速率 | `influxdb_httpd_pointsWrittenDropped_rate` | Number | `cps` | 是否持续非零 | 表示最近 5 分钟写入接口已接收但最终被丢弃的数据点平均速率。该指标持续升高通常说明写入链路存在异常或资源不足。 |
| 写入接口持久化失败速率 | `influxdb_httpd_pointsWrittenFail_rate` | Number | `cps` | 是否持续非零 | 表示最近 5 分钟写入接口已接收但未能成功持久化的数据点平均速率。持续升高时应优先检查磁盘、存储引擎状态和写入路径异常。 |

### 请求压力

用于观察实例当前承受的写入与查询访问压力，可辅助判断性能波动是否由业务流量变化引起。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 写入请求速率 | `influxdb_httpd_writeReq_rate` | Number | `cps` | 是否明显上升 | 表示最近 5 分钟写入请求的平均速率，可用于衡量写入压力变化趋势。 |
| 查询请求速率 | `influxdb_httpd_queryReq_rate` | Number | `cps` | 是否明显上升 | 表示最近 5 分钟查询请求的平均速率，可用于衡量查询压力变化趋势。 |

### 运行时资源

用于观察 InfluxDB 进程运行时的内存占用情况，是判断进程是否存在内存膨胀风险的重要分组。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| Runtime 堆已分配内存 | `influxdb_runtime_HeapAlloc` | Number | `bytes` | 是否持续升高 | 表示 Go runtime 当前已经分配并正在使用的堆内存。持续升高通常意味着高基数、写入压力或查询负载正在推动进程内存膨胀。 |

## 使用建议

- 日常巡检建议优先关注“HTTP 服务质量”和“运行时资源”两组指标。
- 容量治理建议重点关注“基数与容量”分组，尤其是序列数。
- 写入异常建议优先结合“写点丢弃速率”“写入接口持久化失败速率”和“Runtime 堆已分配内存”一起分析。
- 如果实例同时承担大量写入与查询，建议结合“请求压力”和“运行时资源”共同判断是否需要容量扩展或负载拆分。

## 附录：指标与查询对照

如果需要排查指标口径或与查询平台中的表达式进行对照，可参考下表。

| 指标ID | 查询表达式 |
| --- | --- |
| `influxdb_database_numSeries` | `influxdb_database_numSeries{__$labels__}` |
| `influxdb_httpd_authFail_rate` | `sum(rate(influxdb_httpd_authFail{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_clientError_rate` | `sum(rate(influxdb_httpd_clientError{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_serverError_rate` | `sum(rate(influxdb_httpd_serverError{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_pointsWrittenDropped_rate` | `sum(rate(influxdb_httpd_pointsWrittenDropped{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_pointsWrittenFail_rate` | `sum(rate(influxdb_httpd_pointsWrittenFail{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_writeReq_rate` | `sum(rate(influxdb_httpd_writeReq{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_httpd_queryReq_rate` | `sum(rate(influxdb_httpd_queryReq{__$labels__}[5m])) by (instance_id, bind)` |
| `influxdb_runtime_HeapAlloc` | `influxdb_runtime_HeapAlloc{__$labels__}` |
