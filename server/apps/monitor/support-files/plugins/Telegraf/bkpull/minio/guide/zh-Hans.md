# MinIO 监控接入指南

本能力通过 Telegraf `inputs.prometheus` 固定访问 MinIO Prometheus v2 的 cluster、bucket 和 resource 三个端点。

## 前置要求

- 采集节点能够通过 HTTP 访问 MinIO API 主机和端口。
- 三个固定端点均允许匿名读取：`/minio/v2/metrics/cluster`、`/minio/v2/metrics/bucket`、`/minio/v2/metrics/resource`。
- 当前页面只有主机、端口和间隔字段；模板不会发送用户名、密码或 Bearer Token，也不会生成 HTTPS URL。
- 若 MinIO 端点要求认证或强制 HTTPS，当前配置无法直接接入。开放匿名指标时应通过网络边界限制来源。

## 接入步骤

1. 从实际采集节点验证三个固定指标端点。
2. 在接入页面设置采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，只填写 MinIO API 主机和端口，不要包含协议或路径。
4. 填写实例名称和可选分组，保存后等待至少一个采集周期。

## 接入前校验

以下命令使用示例地址；`--fail` 会保留 `4xx/5xx` 失败状态：

```bash
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/cluster"
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/bucket"
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/resource"
```

三个命令都应成功。必须从实际采集节点所在网络验证。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 主机 | 是 | MinIO API 的 IP 或域名，不包含 `http://`、端口或路径。 |
| 端口 | 是 | MinIO API 实际端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问三个固定端点的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `minio_cluster_health_status_gauge`
- `minio_cluster_capacity_usable_free_bytes_gauge`
- `minio_cluster_drive_online_total_gauge`
- `minio_node_cpu_avg_idle_gauge`

## 常见问题

### 返回 `401` 或 `403`

- 当前模板不支持任何认证字段；确认指标端点允许采集节点匿名读取。
- 不要在主机字段中拼接凭据或 Token。

### 返回 `404`

- 确认填写的是 MinIO API 端口，而不是 Console 端口。
- 当前路径固定为 Prometheus v2 三个端点，不支持旧路径。

### HTTP 或 TLS 失败

- 当前模板只生成 HTTP URL；强制 HTTPS 的目标不能直接接入。
- 检查采集节点到 MinIO API 端口的路由、防火墙和安全组。

### 只有部分数据

- 分别验证 cluster、bucket 和 resource 端点；任一端点失败都会缺少对应数据。
- 没有 Bucket 或相关活动时，部分序列可能暂时不存在。
