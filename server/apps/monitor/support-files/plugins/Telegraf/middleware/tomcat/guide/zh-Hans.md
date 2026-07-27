# Tomcat 监控接入指南

本插件通过 Telegraf `inputs.tomcat` 周期性拉取 Tomcat Manager 的 status 页面（`/manager/status/all?XML=true`），采集 JVM 内存 / 内存池 / 连接器（connector）等运行时指标。该接口需要 Manager 角色账号（`manager-gui` 或 `manager-jmx`），生产环境建议使用单独的只读账号。

## 前置要求

- 目标 Tomcat 服务已启动，Manager 已开启且对外开放：

  ```xml
  <!-- conf/tomcat-users.xml -->
  <role rolename="manager-gui"/>
  <user username="monitor" password="monitor-pwd" roles="manager-gui"/>
  ```

- status 接口启用（Tomcat 默认在 Host 容器中加载 `Status` servlet）。

- 在采集节点验证 Manager status 端点：

  ```bash
  curl -u monitor:monitor-pwd "http://<host>:8080/manager/status/all?XML=true"
  ```

  返回 200 + XML 文本即视为正常。

> Telegraf 输出三张表：`tomcat_jvm_memory`、`tomcat_jvm_memorypool`、`tomcat_connector`，并以 `source` / `name` / `type` 为维度。

## 推荐账号权限

Tomcat Manager 通过 `conf/tomcat-users.xml` 控制。建议监控账号只授予 `manager-gui` 角色（或更严格的 `manager-status`），不授予 `manager-script` / `manager-jmx` / `admin-gui` 等可写角色：

```xml
<role rolename="manager-gui"/>
<role rolename="manager-status"/>
<user username="monitor" password="monitor-pwd" roles="manager-status"/>
```

Tomcat 7+ 引入了 RemoteAddrValve，可限制 Manager 远程访问来源 IP。建议仅允许采集节点 IP：

```xml
<Context antiResourceLocking="false" privileged="true">
    <Valve className="org.apache.catalina.valves.RemoteAddrValve"
           allow="10\.0\.0\.\d+\.\d+"/>
</Context>
```

## 接入步骤

1. 在监控接入页填写 URL（默认 `http://<host>:8080/manager/status/all?XML=true`，必须带 `?XML=true`）、用户名、密码、采集间隔（默认 `60s`）。
2. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
3. 点击「确认」保存配置，等待至少一个采集周期。
4. 到资产或指标页确认实例已上报数据。

## 接入前校验

Manager status 可达性：

```bash
curl -u <user>:<pwd> "http://<host>:8080/manager/status/all?XML=true"
```

返回 200 + XML 即视为正常。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Tomcat Manager status 端点 URL，必须含 `?XML=true`，例如 `http://10.0.0.5:8080/manager/status/all?XML=true` |
| 用户名 | 是 | Manager 登录账号，建议 `manager-status` 角色 |
| 密码 | 是 | 对应账号密码 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 URL 末尾是否带 `?XML=true`，否则 Telegraf 拉取 HTML 失败。
- 确认 Manager 已在 `tomcat-users.xml` 中启用且 RemoteAddrValve 没有拦截采集节点 IP。
- 在采集节点用 `curl` 直接验证 `/manager/status/all?XML=true` 返回 200 + XML。
- 等待至少一个采集间隔后再查看。

### 2. 认证失败 / 403

- Tomcat 9+ 默认 Manager 仅允许 `127.0.0.1` 与 `::1` 访问，需要在 `webapps/manager/META-INF/context.xml` 中去掉 RemoteAddrValve 或改为白名单。
- 账号必须具有 `manager-gui` / `manager-status` 角色，仅 `admin-gui` 不足。

### 3. 部分指标缺失

- `tomcat_connector` 只列当前 server.xml 中配置的 connector；新增 connector 后需重启 Tomcat。
- `tomcat_jvm_memorypool` 的 `CodeCache`、`Metaspace` 等内存池取决于 JVM 类型（HotSpot / OpenJ9）；非 HotSpot 会有不同维度。
- 通过 AJP / HTTPS connector 暴露的指标也包含在 `tomcat_connector`，可按 `name` 维度区分。