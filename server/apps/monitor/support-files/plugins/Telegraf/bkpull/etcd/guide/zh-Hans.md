# Etcd 监控接入指南

本插件由 Telegraf 直接拉取 etcd 的 Prometheus 指标端点。页面要求填写包含协议、主机、端口和指标路径的完整 URL。

## 前置要求

- etcd 已暴露 Prometheus 指标端点，通常为 `/metrics`。
- 采集节点能够访问该完整 URL；不要只验证主机端口。
- HTTPS 场景下，CA、客户端证书和客户端私钥文件必须位于采集节点上，且采集进程有读取权限。
- 优先使用可信 CA。仅在临时排障且已接受证书伪造风险时开启“跳过证书校验”。

## 接入步骤

1. 在采集节点完成“接入前校验”，确认完整指标 URL 返回成功。
2. 在 Etcd 配置页填写 URL、TLS 文件路径（如需）、采集间隔和证书校验策略。
3. 在监控对象表格中选择节点，填写同一个完整 URL、实例名称和可选分组。
4. 保存配置并等待至少一个采集周期。默认采集间隔为 `60` 秒。

## 接入前校验

HTTP 示例：

```bash
ETCD_METRICS_URL=http://127.0.0.1:2379/metrics
curl --fail-with-body --silent --show-error "$ETCD_METRICS_URL" --output /tmp/etcd-metrics.txt
grep -E -m 4 '^(etcd_|process_)' /tmp/etcd-metrics.txt
```

HTTPS 双向认证示例：

```bash
ETCD_METRICS_URL=https://etcd-1.example.com:2379/metrics
curl --fail-with-body --silent --show-error \
  --cacert /etc/ssl/etcd/ca.pem \
  --cert /etc/ssl/etcd/client.pem \
  --key /etc/ssl/etcd/client-key.pem \
  "$ETCD_METRICS_URL" --output /tmp/etcd-metrics.txt
grep -E -m 4 '^(etcd_|process_)' /tmp/etcd-metrics.txt
```

`curl` 必须以退出码 `0` 结束，且输出应包含 etcd 的 Prometheus 指标。不要使用仅能证明 TCP 端口开放的结果替代完整 URL 校验。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| URL | 是 | 无 | 完整的 `http://` 或 `https://` 指标 URL，例如 `http://127.0.0.1:2379/metrics`。 |
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

## 接入后验证

1. 等待至少一个采集周期，在平台确认实例状态已更新。
2. 在指标页确认以下已注册指标中至少有与目标实例匹配的数据：
   - `etcd_server_has_leader_gauge`
   - `etcd_backend_allocated_usage_percent`
   - `etcd_server_proposals_pending_gauge`
   - `etcd_disk_wal_fsync_p99_seconds`
3. 若实例存在但指标无数据，重新执行完整 URL 校验，并核对实际生效节点上的 TLS 文件路径。

## 常见问题

### URL 返回 404

页面不会自动补 `/metrics`。确认 URL 中已经包含目标实际暴露的指标路径。

### HTTPS 握手或证书校验失败

核对 CA 链、证书有效期、主机名和 mTLS 证书/密钥配对。优先修复证书，不要把长期跳过校验当作解决方案。

### 请求超时

从配置的采集节点验证完整 URL。模板超时固定为 `30` 秒；端口可达不代表 HTTP 指标响应可用。

### 接入成功但没有 etcd 指标

检查下载内容是否为 Prometheus 文本且含 `etcd_` 指标，避免把代理登录页或其他服务页面当作指标端点。
