# Consul 监控接入指南

本插件通过 Telegraf `inputs.consul` 调用 HashiCorp Consul 的 HTTP API，仅采集健康检查（health checks）状态，不采集 Consul telemetry。如需 telemetry 请自行启用 StatsD 协议将指标外发。Consul API 默认端口 `8500`。

## 前置要求

- 目标 Consul 集群已启动，HTTP API 默认端口 `8500`。
- 采集节点到 Consul 主机网络可达（含安全组 / 防火墙放通）。
- Consul 已启用必要的健康检查 / 服务注册（`consul_health_checks` 表来自 `/v1/health/service/:name` + `/v1/health/state/:state`）。
- 如启用了 ACL，需要为监控账号准备 `token`。

> Telegraf 输出 `consul_health_checks` 一张指标表，维度包含 `node`、`service_name`、`check_id`、`check_name`、`service_id`、`status`，并以 `passing`/`critical`/`warning` 的 int 计数表示状态。

## 推荐账号权限

Consul 健康检查默认对所有 HTTP 客户端开放读取，无需 ACL。如启用 ACL：

```hcl
# 监控 token 只需 health 相关读权限
acl = "write"
```

```bash
# 推荐做法：使用只读策略
consul acl policy create -name monitor-read -rules - <<EOF
service ".*" {
  policy = "read"
}
operator = "read"
EOF

consul acl token create -description "monitor" -policy-name monitor-read
```

## 接入步骤

1. 在采集节点验证 Consul API 可达：

   ```bash
   curl http://<host>:8500/v1/status/leader
   ```

2. 在监控接入页填写 URL（默认 `http://<host>:8500`）、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

Consul API 可达性：

```bash
curl http://<host>:8500/v1/health/service/consul
```

返回 200 + JSON 数组即视为正常。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Consul HTTP API 地址，例如 `http://10.0.0.5:8500` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 Consul 服务已启动且 HTTP API 端口 `8500` 可达。
- 在采集节点直接用 `curl /v1/status/leader` 验证。
- 等待至少一个采集间隔后再查看；检查节点上 Telegraf / 采集任务是否正常运行。

### 2. 认证失败

- Consul 启用 ACL 后需要在 `inputs.consul` 增加 `token = "<token>"` 字段，当前 Telegraf 模板未启用；如启用 ACL，请同步调整模板并把 token 注入到 env_config 中。
- 检查 Consul 主配置 `acl.tokens.default` 与 `acl.enabled` 是否一致。

### 3. 部分指标缺失

- `consul_health_checks` 仅采集健康检查状态，不包括 telemetry / runtime metrics；运行时数据请用 `inputs.prometheus` 抓取 Consul 自暴露的 `/v1/agent/metrics`（如有开启）。
- 不同 Consul 版本的字段可能略有差异，`metric_version = 2`（v1.16+ 默认）会把字符串字段移到 tag 上，建议升级到该版本以上。
- 没有注册任何 service 时，`consul_health_checks` 只会剩下 `serfHealth` 等节点级检查，属正常现象。