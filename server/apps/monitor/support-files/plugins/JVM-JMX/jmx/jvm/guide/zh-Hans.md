# JVM-JMX 监控接入指南

## 前置要求

- 目标 Java 应用已开启远程 JMX/RMI。
- 采集节点已安装 JVM-JMX 采集器，并且能够访问目标 JMX 端口。
- JMX Registry 端口和 RMI Server 端口应固定并在防火墙、安全组中放通。
- `java.rmi.server.hostname` 必须设置为采集节点能够访问的目标地址，不能使用仅目标主机本地可达的地址。
- 如启用了 JMX 认证，需准备只读监控账号及密码。
- 采集节点上需预留一个未被占用的监听端口，用于 JVM-JMX 采集器在本地暴露 Prometheus `/metrics`。

JVM 启动参数示例：

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<目标主机可达地址>
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

上述示例关闭了认证和 SSL，仅适合受控测试环境。生产环境应按 Java 官方 JMX 安全机制启用认证，并限制 JMX 端口的访问来源。

## 接入步骤

1. 在采集节点上确认目标 JMX 端口可达，并使用 JMX 客户端验证连接地址。
2. 在监控接入页面选择 `JVM` 插件。
3. 如目标 Java 应用开启了 JMX 认证，填写用户名和密码；否则留空。
4. 设置采集间隔，默认 `60` 秒。
5. 在监控对象表格中选择采集节点，填写监听端口和 JMX URL，并设置实例名称及可选分组。
6. 保存配置后等待至少一个采集周期，再到实例或指标页面检查数据。

## 接入前校验

先从实际采集节点检查目标 JMX 端口：

```bash
nc -vz <target-host> 9010
```

标准 JMX/RMI URL 示例：

```text
service:jmx:rmi:///jndi/rmi://<target-host>:9010/jmxrmi
```

建议再使用 `jconsole`、`jmc` 或其他 JMX 客户端连接同一个 URL。能够成功连接并读取 `java.lang`、`java.nio` 域中的 MBean，才表示地址、RMI 回连、认证和网络配置基本可用。

> 本插件连接标准 JMX/RMI，不使用 Jolokia HTTP 地址。请勿填写 `http://<host>:<port>/jolokia`。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | 开启 JMX 认证时填写；未开启认证时留空。 |
| 密码 | 否 | JMX 监控账号的密码；与用户名配套使用。 |
| JMX URL | 是 | 标准 JMX Service URL，例如 `service:jmx:rmi:///jndi/rmi://10.0.0.12:9010/jmxrmi`。 |
| 监听端口 | 是 | JVM-JMX 采集器在所选采集节点上暴露 `/metrics` 的本地端口，不是目标 Java 应用的 JMX 端口；同一节点上的不同实例不能使用相同端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行 JVM-JMX 采集器的节点，必须能访问目标 JMX/RMI 地址。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

首次接入时，监听端口和 JMX URL 在监控对象表格中填写；编辑已有配置时，页面会回显对应的采集配置字段。

## 接入后验证

保存配置并等待至少一个采集周期后，按以下顺序检查：

1. 确认 JVM-JMX 采集器进程已在所选节点启动，且监听端口未发生冲突。
2. 在采集节点本地访问 `http://127.0.0.1:<监听端口>/metrics`，确认能看到 `jmx_` 或 `jvm_` 指标。
3. 在平台中确认 `jmx_scrape_error_gauge` 为 `0`。
4. 确认至少能查询到以下 JVM 指标：
   - `jvm_memory_usage_used_value`
   - `jvm_threads_count_value`
   - `jvm_gc_collectiontime_seconds_value`

当前采集规则覆盖 JVM 内存、线程、操作系统、Buffer Pool、垃圾回收和 Memory Pool 等标准 MBean。未在采集白名单中的业务自定义 MBean 不会自动上报。

## 常见问题

### 1. JMX 端口可连接，但采集仍然失败

- 检查 `java.rmi.server.hostname` 是否为采集节点可达的 IP 或域名。
- JMX/RMI 可能先连接 Registry 端口，再回连另一个随机端口；应通过 `com.sun.management.jmxremote.rmi.port` 固定 RMI Server 端口并放通。
- 使用 JMX 客户端从采集节点重试同一个 URL，不能只在目标主机本地验证。

### 2. 返回认证失败

- 确认目标 JVM 是否启用了 `com.sun.management.jmxremote.authenticate`。
- 检查用户名、密码以及 JMX password/access 文件权限。
- 未启用认证时，用户名和密码应同时留空。

### 3. JVM-JMX 采集器无法启动或本地 `/metrics` 不可访问

- 检查所填监听端口是否已被其他进程或其他 JVM 监控实例占用。
- 确认所选节点已安装 JVM-JMX 采集器及 Java 运行环境。
- 查看采集器进程参数和日志，确认配置文件已正确生成并加载。

### 4. `jmx_scrape_error_gauge` 非 0 或只有部分指标

- 检查目标 JVM 版本是否提供当前规则使用的标准 MBean。
- 确认监控账号有权读取 `java.lang` 和 `java.nio` 域。
- 自定义应用 MBean、Tomcat 线程池等不属于 JVM 通用采集范围，需要使用对应监控能力或扩展采集规则。
