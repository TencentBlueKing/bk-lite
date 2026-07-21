# Apache 监控接入指南

本插件通过 Telegraf `inputs.apache` 周期性拉取 Apache HTTPD `mod_status` 的可机读页面（默认 `/server-status?auto`），采集 worker 数量、请求速率、字节数、连接状态等运行时指标。前提是 Apache 已开启 `mod_status`，并通过 `ExtendedStatus On` 暴露完整字段。

## 前置要求

- 目标 Apache HTTPD 服务已启动，`mod_status` 已加载（通常随 `status_module` 默认启用）。
- 在 Apache 配置中开启 `ExtendedStatus On`，并对外暴露 `/server-status` 页面，例如：

  ```apache
  <Location "/server-status">
      SetHandler server-status
      Require local
      Require ip 10.0.0.0/24   # 如需远程访问
  </Location>
  ExtendedStatus On
  ```

- 采集节点到 Apache 主机网络可达（含安全组 / 防火墙放通）。
- URL 必须指向 `server-status` 的「可机读」版本，即带 `?auto` 查询串，否则返回 HTML 无法解析。

> Telegraf 默认 URL 为 `http://localhost/server-status?auto`，可一次性拉取全部状态行，并输出 `apache_*` 指标（如 `BusyWorkers`、`ReqPerSec`、`BytesPerSec`、`TotalAccesses`）。

## 推荐账号权限

若 `/server-status` 不需要 Basic Auth（推荐仅监听 `127.0.0.1` 或内网），则无需账号；如必须对公网开放，建议仅加白名单 IP 控制，并在 Apache 侧加 Basic Auth：

```apache
<Location "/server-status">
    SetHandler server-status
    AuthType Basic
    AuthName "Apache Status"
    AuthUserFile "/etc/httpd/conf/.htpasswd"
    Require valid-user
</Location>
```

监控账号建议只读权限（仅能访问 `/server-status`），不授予站点管理权限。

## 接入步骤

1. 在浏览器或命令行验证 `mod_status` 可访问：

   ```bash
   curl http://<host>/server-status?auto
   ```

   返回多行 `Key: Value` 即视为正常。

2. 在监控接入页填写 URL（必须带 `?auto`，例如 `http://10.0.0.5/server-status?auto`）、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

`mod_status` 可访问性（输出至少应包含 `Total Accesses`）：

```bash
curl http://<host>/server-status?auto
```

若返回 HTML 表示缺少 `?auto` 参数，需要修正 Apache 路由或 URL 拼写。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Apache mod_status 的可机读页面 URL，必须含 `?auto`，例如 `http://10.0.0.5/server-status?auto` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 URL 末尾是否带 `?auto`，否则 Telegraf 拉取 HTML 失败。
- 确认 `ExtendedStatus On` 已开启，否则 `BusyWorkers` 等字段会被合并到 0。
- 在采集节点用 `curl` 直接验证 `/server-status?auto` 返回 200 + 可机读文本。
- 等待至少一个采集间隔后再查看。

### 2. 认证失败

- 如果 Apache 配置启用了 Basic Auth，需要把用户名 / 密码填入 UI.json（当前模板默认未启用，如需启用可调整 `inputs.apache` 增加 `username` / `password` 字段）。
- 检查 `AuthUserFile` 路径与 `htpasswd` 是否可读。

### 3. 部分指标缺失

- 未开启 `ExtendedStatus On` 时，`BytesPerReq`、`ReqPerSec`、`Scoreboard` 等字段都会被压缩或丢弃。
- 反向代理（如 Nginx）如果把 `?auto` 查询串过滤掉，URL 退化为 HTML；请让代理直接透传查询串。