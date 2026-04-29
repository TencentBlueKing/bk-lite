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

## 口径说明

- 当前文档仅包含首批核心指标，不包含更深入的存储引擎、缓存、WAL 段和查询执行器细粒度指标。
- 频率类指标统一基于最近 5 分钟窗口计算，单位使用产品标准单位 `hertz`，页面会按 `Hz/KHz/MHz` 自动展示。
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
| HTTP 认证失败速率 | `influxdb_httpd_authFail_rate` | Number | `hertz` | 是否突增 | 表示最近 5 分钟 HTTP 接口认证失败的平均速率。突增通常意味着访问配置错误、凭据问题或异常尝试。 |
| HTTP 4XX 错误速率 | `influxdb_httpd_clientError_rate` | Number | `hertz` | 是否持续升高 | 表示最近 5 分钟客户端请求导致 4XX 错误的平均速率。持续升高通常说明请求参数错误、接口使用方式异常或上游调用不规范。 |
| HTTP 5XX 错误速率 | `influxdb_httpd_serverError_rate` | Number | `hertz` | 是否持续升高 | 表示最近 5 分钟服务端处理请求返回 5XX 的平均速率。持续升高通常说明实例内部处理异常、资源压力升高或服务端逻辑故障。 |
| 写点丢弃速率 | `influxdb_httpd_pointsWrittenDropped_rate` | Number | `hertz` | 是否持续非零 | 表示最近 5 分钟写入接口已接收但最终被丢弃的数据点平均速率。该指标持续升高通常说明写入链路存在异常或资源不足。 |
| 写入接口持久化失败速率 | `influxdb_httpd_pointsWrittenFail_rate` | Number | `hertz` | 是否持续非零 | 表示最近 5 分钟写入接口已接收但未能成功持久化的数据点平均速率。持续升高时应优先检查磁盘、存储引擎状态和写入路径异常。 |

### 请求压力

用于观察实例当前承受的写入与查询访问压力，可辅助判断性能波动是否由业务流量变化引起。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 写入请求速率 | `influxdb_httpd_writeReq_rate` | Number | `hertz` | 是否明显上升 | 表示最近 5 分钟写入请求的平均速率，可用于衡量写入压力变化趋势。 |
| 查询请求速率 | `influxdb_httpd_queryReq_rate` | Number | `hertz` | 是否明显上升 | 表示最近 5 分钟查询请求的平均速率，可用于衡量查询压力变化趋势。 |

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
