# HAProxy 监控接入指南

本插件通过 Telegraf `inputs.haproxy` 周期性抓取 HAProxy 暴露的统计端点，采集 `proxy` / `sv` / 状态码 / 连接 / 字节 / 速率等指标。统计端点可为 HTTP stats 页面或 unix socket；当前 UI 默认走 HTTP 页面（`http://<host>:<port>/<path>;csv`）。Telegraf 在 v1.21+ 支持将 username / password 拆出 URL，避免特殊字符在 userinfo 段被 `net/url.Parse` 破坏，请使用「Stats 地址 + 用户名 + 密码」三个独立字段填写。

## 前置要求

- 目标 HAProxy 已启动并暴露 stats 端点（`stats enable` 或 `stats uri /haproxy?stats`，常用 `http://<ip>:1024/haproxy?stats` 或 `:1936`）。
- 采集节点到 HAProxy stats 端口网络可达（含安全组 / 防火墙放通）。
- 若 stats 页面启用 Basic Auth，准备好只读账号。
- 当前模板 `keep_field_names = true`，保留 HAProxy 原始字段名（`pxname` / `svname` 等不会被替换为 `proxy` / `sv`）。

> Telegraf `inputs.haproxy` 的 `servers` 支持 http(s)、tcp、unix socket。HTTP 形式若账号带特殊字符，请单独填写 username / password（不要把账密塞到 URL userinfo，否则可能触发 401）。

## 推荐账号权限

HAProxy stats 页面通过 `stats auth <user>:<pass>` 或 `userlist` 控制。建议监控账号只读：

```haproxy
userlist monitor-users
    user monitor-user insecure-password "monitor-pwd"

frontend stats
    bind *:8404
    stats enable
    stats uri /haproxy?stats
    stats auth monitor-user:monitor-pwd
    stats refresh 10s
    acl auth_ok http_auth(monitor-users)
    http-request auth unless auth_ok
```

监控账号只需能 GET stats 页面，不参与流量调度。

## 接入步骤

1. 在浏览器或命令行验证 stats 端点可达：

   ```bash
   curl -u monitor-user:monitor-pwd "http://<host>:8404/haproxy?stats;csv"
   ```

2. 在监控接入页填写「Stats 地址」（`http://<host>:<port>/<path>`，不要带 userinfo）、可选的「用户名」「密码」、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、Stats 地址、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

stats 端点可达性（带账密时需 -u）：

```bash
curl -u <user>:<pwd> "http://<host>:8404/haproxy?stats;csv"
```

返回 CSV 多行 `pxname,svname,...` 即视为正常。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| Stats 地址 | 是 | HAProxy stats 端点 URL，例如 `http://10.0.0.5:8404/haproxy?stats`，不要带 userinfo |
| 用户名 | 否 | stats 页面 Basic Auth 用户名，未启用认证则留空 |
| 密码 | 否 | stats 页面 Basic Auth 密码，未启用认证则留空 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 Stats 地址自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 Stats 地址格式正确，能在采集节点用 `curl` 拉到 `;csv` 输出。
- 如未启用 Basic Auth，请勿填写账密。
- 等待至少一个采集间隔后再查看。

### 2. 认证失败 / 401

- 账号密码含特殊字符（如 `@` `/` `:` `#`）时务必拆出 userinfo（不要拼到 URL 中），Telegraf 在 v1.21+ 会通过 `username` / `password` 字段发 `Authorization` 头。
- 确认 `stats auth` 已正确配置且匹配 `userlist` / `user` 段。

### 3. 字段名奇怪

- 当前模板设置了 `keep_field_names = true`，所以你会看到 HAProxy 原始字段名 `pxname` / `svname` / `hrsp_2xx` 等；如果想用 `proxy` / `sv` / `http_response.2xx` 等归一化名，把该字段改为 `false` 即可。