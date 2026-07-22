# ActiveMQ 监控接入指南

本插件通过 Telegraf `inputs.activemq` 周期性调用 ActiveMQ WebConsole 的 Console API，采集队列 / 主题 / 订阅者的状态指标，底层走 HTTP Basic Auth。请确认 ActiveMQ 已开启 WebConsole（默认 `http://<host>:8161`），并准备好只读监控账号。

## 前置要求

- 目标 ActiveMQ 服务已启动，WebConsole 默认端口 `8161`。
- 采集节点到 ActiveMQ 主机网络可达（含安全组 / 防火墙放通对应端口）。
- 已准备好具有 WebConsole 登录权限的监控账号（默认管理员 `admin/admin`，生产建议改为只读账号）。
- ActiveMQ 启动时已开启 WebConsole 的 `admin` webadmin 根路径（`webadmin = "admin"`，插件默认）。

> Telegraf 采集 `activemq_queues`、`activemq_topics`、`activemq_subscribers` 三张指标表，分别带 `name`、`source`、`port`、`client_id` 等维度。

## 推荐账号权限

ActiveMQ WebConsole 自身使用基础认证（`users`/`groups`/`login.config` 中的角色）。监控账号只需可登录 WebConsole、无需管理权限：

```text
# $ACTIVEMQ_HOME/conf/credentials.properties 或 users.properties
monitor=monitor_pwd
```

```text
# $ACTIVEMQ_HOME/conf/groups.properties
monitor=readonly
```

`readonly` 角色通常只能浏览页面与触发 Console API，已能满足采集需求；不要把 `admin` 角色下放给监控账号。

## 接入步骤

1. 在浏览器或命令行验证 WebConsole 可访问：

   ```bash
   curl -u monitor:monitor_pwd http://<host>:8161/admin/
   ```

2. 在监控接入页填写 URL（默认 `http://<host>:8161`）、用户名、密码、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

WebConsole HTTP 可达性：

```bash
curl -u <user>:<pwd> http://<host>:8161/admin/xml/queues.jsp
```

返回 200 + ActiveMQ XML 即视为可达。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | ActiveMQ WebConsole 地址，例如 `http://10.0.0.5:8161` |
| 用户名 | 是 | WebConsole 登录账号 |
| 密码 | 是 | 对应账号密码，注意不要带入首尾空格 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 ActiveMQ 服务和 WebConsole 已启动，端口 `8161` 可达。
- 在采集节点用 `curl` + 账号密码直接访问 `/admin/` 验证。
- 等待至少一个采集间隔后再查看。
- 检查节点上 Telegraf / 采集任务是否正常运行。

### 2. 认证失败

- 核对用户名密码首尾是否带空格、是否在 `credentials.properties` 同步生效（ActiveMQ 默认缓存用户配置，修改后必须重启）。
- 确认账号已在 `groups.properties` 中授权可登录 `admin`。
- 若启用了 JAAS，账号要同时在 `login.config` 注册。

### 3. 部分指标缺失

- `activemq_subscribers` 依赖 `client_id`，若客户端使用匿名连接将不会上报该指标。
- `activemq_queues` 维度 `name` 与队列同名，队列被删除后该标签会消失，属正常现象。
- WebConsole 的 `webadmin` 根路径非默认 `admin` 时，请修改 Telegraf 配置的 `webadmin` 字段。