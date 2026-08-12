# MinIO 多版本监控接入指南

本能力通过 Telegraf Prometheus 采集器抓取 MinIO 官方 Metrics v2/v3 指标，覆盖集群健康、容量、请求流量和节点资源等监控场景。

## 版本选择

| MinIO 版本 | 页面选择 | 说明 |
| --- | --- | --- |
| `RELEASE.2021-01-30` 之前 | 不支持 | legacy Metrics v1 不在本能力范围内。 |
| `RELEASE.2021-01-30` 至 `RELEASE.2024-05-27` | v2 | 使用兼容端点。 |
| `RELEASE.2024-05-28` 及之后 | v3（推荐） | 使用分组明确的 Metrics v3 核心端点。 |

Metrics v3 最早出现于 `RELEASE.2024-03-15`，但早期接口仍在演进，因此本能力以 `RELEASE.2024-05-28` 作为完整核心能力起点。较新的 MinIO 同时保留 v2/v3，不存在“仅支持 2024-07-15 及之前版本”的上限。

旧实例缺少新增字段时继续按 `v2 + HTTP + public` 运行，并保留原来的 cluster、bucket、resource 三端点；新建实例默认 `v3 + HTTPS + Bearer Token`。

## 前置要求

- 填写 MinIO **API 端口**，不是 Console 管理端口。默认部署中 API 常为 `9000`、Console 常为 `9001`，但以实际部署为准。
- 生产环境使用 HTTPS，并确保采集节点信任服务端证书链。`跳过证书校验` 只用于临时排障。
- 默认鉴权使用 Bearer Token。不要填写 Access Key、Secret Key、用户名密码或 `Bearer ` 前缀。
- 建议创建只授予 `admin:Prometheus` 的专用访问身份，再使用该身份对应的 `mc` alias 生成 Token。v3 必须显式指定 API 版本；省略 `--api-version` 时，当前 `mc` 生成的是 v2 抓取配置：

```bash
mc admin prometheus generate ALIAS --api-version v3
```

如果 `mc` 提示不支持 `--api-version`，请先升级 `mc`。旧版 `mc admin prometheus generate ALIAS` 仍可生成 Bearer Token，但输出的是 v2 抓取配置；使用该 Token 前，应按下文命令直接验证页面所选的 v3 端点。

Token 通过采集器环境变量注入，不写入 Telegraf TOML 正文。只有服务端显式设置 `MINIO_PROMETHEUS_AUTH_TYPE=public` 时才选择“公开访问”；不要把匿名指标端点直接暴露到公网。

## 核心与扩展指标

- v2 核心端点：`/minio/v2/metrics/cluster`、`/minio/v2/metrics/resource`。
- 早于 `RELEASE.2023-10-07T15-07-38Z` 的 v2 版本尚未提供 `/minio/v2/metrics/resource`；Telegraf 会对该 URL 报 404，但仍可从 cluster 端点采集当时已有的指标。若不能接受持续的 404 日志，请先升级 MinIO 再启用本接入。BK-Lite 不会在运行期自动删除端点或回退版本。
- v3 核心端点：`/api/requests`、`/cluster/health`、`/cluster/erasure-set`、`/cluster/usage/objects`、`/system/cpu`、`/system/memory`、`/system/drive`、`/system/process`、`/system/network/internode`，均位于 `/minio/metrics/v3` 下。
- Bucket 扩展：v2 bucket 端点或 v3 `/cluster/usage/buckets`。首版不自动分页枚举每个 Bucket 的 `/bucket/.../<bucket>` 明细。
- 复制、生命周期、审计通知、IAM/KMS 为按需扩展。KMS 指标来自 v2 cluster 端点；当前 v3 官方分组提供 IAM 而没有独立 KMS 端点。

模板用 `namepass` 只写入所选核心及扩展指标族，并排除 TTFB histogram，以控制时序基数。每条时序都带有 `minio_metrics_version=v2|v3` 标签。

## 指标最低版本

指标详情的“描述”会逐项显示完整的最低 MinIO release。下表按本能力登记的指标族汇总；低于对应版本时，即使端点本身可访问，该项指标也可能不存在。v3 核心建议仍以 `RELEASE.2024-05-28T17-19-04Z` 及之后版本使用；扩展指标应另外满足下表版本。

| API | 本能力登记的指标 | 最低 MinIO release |
| --- | --- | --- |
| v2 | 集群容量、在线/离线磁盘、在线/离线节点、S3 收发流量 | `RELEASE.2021-01-30T00-20-58Z` |
| v2 | S3 等待请求 | `RELEASE.2021-02-23T20-05-01Z` |
| v2 | 进程运行时间 | `RELEASE.2021-03-26T00-00-41Z` |
| v2 | S3 鉴权拒绝 | `RELEASE.2021-04-18T19-26-29Z` |
| v2 | 进程 CPU、进程常驻内存 | `RELEASE.2021-05-11T23-27-41Z` |
| v2 | Scanner 对象扫描 | `RELEASE.2021-12-18T04-42-33Z` |
| v2 | S3 当前传入请求 | `RELEASE.2022-02-12T00-51-25Z` |
| v2 | S3 5xx 错误 | `RELEASE.2022-06-10T16-59-15Z` |
| v2 | KMS 请求内部失败 | `RELEASE.2022-07-13T23-29-44Z` |
| v2 | 集群健康状态 | `RELEASE.2023-08-04T17-40-21Z` |
| v2 | Resource CPU、磁盘 I/O/利用率 | `RELEASE.2023-10-07T15-07-38Z` |
| v2 | Resource 内存使用率 | `RELEASE.2023-12-07T04-16-00Z` |
| v2 | 纠删组在线磁盘 | `RELEASE.2023-12-23T07-19-11Z` |
| v2 | 纠删组健康状态 | `RELEASE.2024-01-28T22-35-53Z` |
| v3 | API 请求、集群健康/容量、纠删组、对象使用量、节点间网络 | `RELEASE.2024-03-15T01-07-19Z` |
| v3 | 系统内存、磁盘 | `RELEASE.2024-04-18T19-09-19Z` |
| v3 | 系统 CPU、进程、通知错误 | `RELEASE.2024-04-28T17-53-50Z` |
| v3 | IAM 同步失败 | `RELEASE.2024-05-07T06-41-25Z` |
| v3 | Scanner、Audit | `RELEASE.2024-05-27T19-17-46Z` |
| v3 | ILM | `RELEASE.2024-06-06T09-36-42Z` |
| v3 | Bucket 使用量（本能力使用的端点修复后） | `RELEASE.2024-07-15T19-02-30Z` |
| v3 | 复制最近积压 | `RELEASE.2024-08-03T04-33-23Z` |

## 接入步骤

1. 在实际采集节点验证所选版本、协议和认证方式。
2. 新建实例时显式确认指标 API 版本、协议和认证方式。
3. 填写 API 主机和端口；主机字段不要包含协议、端口或路径。
4. 按需开启扩展指标，保存后等待至少一个采集周期。

Bearer v3 示例：

```bash
export MINIO_METRICS_TOKEN='从 mc admin prometheus generate 输出中取得的 Token'
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${MINIO_METRICS_TOKEN}" \
  "https://minio.example.com:9000/minio/metrics/v3/cluster/health"
```

public v2 示例：

```bash
curl --fail --silent --show-error \
  "http://minio.example.com:9000/minio/v2/metrics/cluster"
```

不要在 shell 历史、平台日志或工单中打印真实 Token。生产环境不要用 `curl -k` 代替正确的证书信任配置。

## 页面字段

| 字段 | 说明 |
| --- | --- |
| 指标 API 版本 | 新建默认 v3；旧版本选择 v2。 |
| 协议 | 新建默认 HTTPS。HTTP 仅用于隔离可信网络。 |
| 认证方式 | 新建默认 Bearer；public 仅匹配服务端显式匿名配置。 |
| Bearer Token | 加密字段，仅 Bearer 模式显示，经环境变量注入。 |
| 扩展指标 | 支持多选且默认关闭；只有选中的分组会在核心指标之外额外采集。 |
| 跳过证书校验 | 默认关闭，仅用于临时排障。 |
| 主机、端口 | MinIO API 地址，不是 Console 地址。 |

## 故障定位

- `401/403`：Token 缺失、错误、过期或缺少 `admin:Prometheus`；public 模式与服务端设置不一致。
- `404`：通常是版本路径选错，或误填 Console 端口。本能力不在运行期自动回退。
- TLS 失败：检查证书链、主机名和采集节点系统 CA；不要长期启用跳过校验。
- 只有部分指标：确认对应扩展已开启，且 MinIO 功能实际启用并产生数据；MinIO 会省略无值指标。
