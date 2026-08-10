# Tomcat 监控接入指南

本能力通过 Telegraf `inputs.tomcat` 拉取 Tomcat Manager 的 XML status 端点。

## 前置要求

- 目标 Tomcat 已启用 Manager status，并提供完整 URL，例如 `http://tomcat.example.com:8080/manager/status/all?XML=true`。
- 准备仅授予 `manager-status` 角色的监控账号；不要为采集额外授予管理或脚本角色。
- 采集节点能够访问 Manager 端口，且 RemoteAddrValve 允许实际采集节点来源 IP。
- 当前页面要求 URL、用户名和密码，URL 必须返回 XML status 内容。

限制单个采集节点 IP 的四段地址正则示例：

```xml
<Valve className="org.apache.catalina.valves.RemoteAddrValve"
       allow="10\.0\.0\.25"/>
```

## 接入步骤

1. 从实际采集节点验证 XML status URL、`manager-status` 账号和来源 IP 白名单。
2. 填写完整 URL、用户名、密码和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

下列命令会交互式询问密码：

```bash
curl --fail --silent --show-error --user monitor "http://tomcat.example.com:8080/manager/status/all?XML=true"
```

请求应返回 `200` 和 XML；`--fail` 会保留 `4xx/5xx` 失败状态。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Tomcat Manager XML status 完整 URL，需包含 `?XML=true`。 |
| 用户名 | 是 | 具有 `manager-status` 角色的账号。 |
| 密码 | 是 | 对应账号密码。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 Manager status 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `tomcat_jvm_memory_free`
- `tomcat_jvm_memorypool_used`
- `tomcat_connector_request_count_rate`
- `tomcat_connector_current_thread_utilization`

## 常见问题

### 返回 `401` 或 `403`

- 确认账号角色统一为 `manager-status`。
- 核对 RemoteAddrValve 正则是否为正确的四段 IP，并包含实际采集节点来源地址。

### 返回 HTML 或解析失败

- 确认 URL 包含 `?XML=true`，且反向代理未删除查询串。
- 从实际采集节点执行接入前命令复现。

### 只有部分数据

- 连接器和内存池维度取决于目标 Tomcat 与 JVM 实际配置；不存在的对象不会产生序列。
