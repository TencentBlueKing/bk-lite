# JVM-JMX 监控接入指南

本能力通过 JVM-JMX 采集器连接标准 JMX/RMI 服务，再由 Telegraf 从采集器本地 `/metrics` 端点拉取指标。

## 前置要求

- 目标 Java 应用已启用远程 JMX/RMI；JMX Registry 与 RMI Server 端口均已固定并允许采集节点访问。
- `java.rmi.server.hostname` 必须是采集节点可达的目标地址。
- 如目标启用 JMX 认证，准备可读取 `java.lang`、`java.nio` 等标准 MBean 的账号和密码；未启用认证时两项均留空。
- 在采集节点上准备一个未占用的本地监听端口。该端口用于采集器暴露 `/metrics`，不是目标 JMX 端口。
- 当前规则只采集模板白名单内的标准 JVM MBean，不会自动采集业务自定义 MBean。

## 接入步骤

1. 从实际采集节点验证目标 JMX/RMI 地址、固定端口和认证信息。
2. 在接入页面按需填写用户名、密码，填写标准 JMX Service URL，并设置采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写未占用的监听端口、JMX URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

先验证目标端口可达：

```bash
nc -vz app.example.com 9010
```

对应的标准 JMX/RMI URL 可写为：

```text
service:jmx:rmi:///jndi/rmi://app.example.com:9010/jmxrmi
```

再使用 `jconsole`、`jmc` 或其他 JMX 客户端，从同一采集节点连接该 URL 并读取标准 MBean。Jolokia HTTP URL 不适用于本能力。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | 启用 JMX 认证时填写；否则留空。 |
| 密码 | 否 | 与 JMX 用户名配套；否则留空。 |
| JMX URL | 是 | 标准 JMX Service URL。 |
| 监听端口 | 是 | 采集器在所选节点本地暴露 `/metrics` 的端口；同一节点的实例不可冲突。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行采集器且能够访问目标 JMX/RMI 的节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，可在采集节点按实际监听端口验证本地端点，例如：

```bash
curl --fail --silent --show-error "http://127.0.0.1:9404/metrics"
```

随后在平台确认以下指标可查询：

- `jmx_scrape_error_gauge`
- `jvm_memory_usage_used_value`
- `jvm_threads_count_value`
- `jvm_gc_collectiontime_seconds_value`

## 常见问题

### JMX 端口可连接但采集失败

- 检查 `java.rmi.server.hostname` 是否可从采集节点解析和访问。
- 固定 `com.sun.management.jmxremote.rmi.port`，避免 Registry 连接成功后回连随机端口失败。
- 使用相同 JMX URL 从采集节点重试，不要只在目标主机本地验证。

### 认证失败或只有部分指标

- 未启用认证时，用户名和密码应同时留空。
- 启用认证时，确认账号可读取模板白名单涉及的标准 MBean。
- 自定义 MBean 不在当前规则范围内，应使用对应能力或另行扩展采集规则。

### 本地端点不可访问

- 检查监听端口是否被其他进程或其他监控实例占用。
- 核对采集器进程参数、生成配置和日志中的实际错误。
