# MinIO 监控接入指南

## 前置要求

- 目标 MinIO 服务已启用 Prometheus v2 指标端点。
- 采集节点能够通过 HTTP 访问 MinIO API 地址和端口，默认端口通常为 `9000`。
- 以下三个端点必须允许采集节点匿名访问：
  - `/minio/v2/metrics/cluster`
  - `/minio/v2/metrics/bucket`
  - `/minio/v2/metrics/resource`
- 如 MinIO 指标端点默认要求认证，需要在 MinIO 侧将 Prometheus 认证类型配置为 `public`，并在受控网络中限制端口访问来源。

当前插件固定使用匿名 HTTP 请求，不会发送用户名、密码或 Bearer Token，也不能配置 HTTPS。若目标环境只允许 HTTPS 或鉴权访问，当前配置无法直接接入。

## 接入步骤

1. 从实际采集节点分别访问三个 MinIO 指标端点，确认均能返回 Prometheus 指标文本。
2. 在监控接入页面选择 `MinIO` 插件。
3. 设置采集间隔，默认 `60` 秒。
4. 在监控对象表格中选择采集节点，填写 MinIO 主机和 API 端口。
5. 设置实例名称及可选分组，保存配置。
6. 等待至少一个采集周期，再到实例或指标页面检查数据。

## 接入前校验

在实际采集节点上执行：

```bash
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/cluster | grep '^minio_'
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/bucket | grep '^minio_'
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/resource | grep '^minio_'
```

三个命令均应成功，并能看到以 `minio_` 开头的 Prometheus 指标。必须在采集节点所在网络执行校验，仅从运维终端访问成功不能证明采集链路可用。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 主机 | 是 | MinIO API 的 IP 地址或域名，不要包含 `http://`、端口或路径。 |
| 端口 | 是 | MinIO API 端口，通常为 `9000`。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行 Telegraf 的采集节点，必须能访问三个指标端点。 |
| 实例名称 | 是 | 平台内展示的实例名称，默认可按 `主机:端口` 生成。 |
| 组 | 否 | 实例所属分组。 |

插件会根据主机和端口固定生成以下 URL，无需在页面填写指标路径：

```text
http://<host>:<port>/minio/v2/metrics/cluster
http://<host>:<port>/minio/v2/metrics/bucket
http://<host>:<port>/minio/v2/metrics/resource
```

## 接入后验证

保存配置并等待至少一个采集周期后，按以下顺序检查：

1. 确认所选节点上的 Telegraf 采集任务正常运行。
2. 确认三个指标端点没有返回连接错误、`401`、`403` 或 `404`。
3. 在平台中确认至少能查询到以下指标：
   - `minio_cluster_health_status_gauge`
   - `minio_cluster_capacity_usable_free_bytes_gauge`
   - `minio_cluster_drive_online_total_gauge`
4. 如需验证资源和 S3 服务数据，再检查：
   - `minio_node_cpu_avg_idle_gauge`
   - `minio_s3_traffic_received_bytes_counter_rate`

## 常见问题

### 1. 返回 `401 Unauthorized` 或 `403 Forbidden`

- 当前插件不支持用户名、密码或 Bearer Token。
- 需要在 MinIO 侧允许采集节点匿名读取 Prometheus 指标端点，例如将 Prometheus 认证类型配置为 `public`。
- 指标端点公开后，应通过防火墙、安全组或受控网络限制访问来源，避免暴露到非可信网络。

### 2. 返回 `404 Not Found`

- 确认目标 MinIO 版本提供 `/minio/v2/metrics/cluster`、`bucket` 和 `resource` 端点。
- 确认填写的是 MinIO API 端口，而不是 Console 管理端口。
- 当前插件不能修改指标路径，也不兼容旧的 `/minio/prometheus/metrics` 路径。

### 3. HTTP 访问失败或发生 TLS 错误

- 当前模板只生成 `http://` URL，不支持 `https://`。
- 检查采集节点到 MinIO API 端口的路由、防火墙和安全组。
- 如果目标强制跳转 HTTPS，当前插件会因协议不匹配而无法直接采集。

### 4. 只有部分 MinIO 指标

- 分别检查 cluster、bucket、resource 三个端点，任一端点失败都会造成对应指标组缺失。
- 没有 Bucket 或相关活动时，部分 Bucket/S3 指标可能暂时没有序列。
- 检查 Telegraf 日志，确认具体失败 URL 和 HTTP 状态码。
