# Nginx 监控接入指南

本插件通过 Telegraf `inputs.nginx` 周期性拉取 Nginx 的 `ngx_http_stub_status_module` 输出（常用 `/stub_status` 或 `/server_status`），采集连接 / 请求 / 读写状态指标。该模块只能用于开源版 Nginx；Nginx Plus 需用对应的 `inputs.nginx_plus` 或 `inputs.nginx_upstream_check`。

## 前置要求

- 目标 Nginx 服务已启动，且编译时包含 `ngx_http_stub_status_module`（可用 `nginx -V 2>&1 | grep -o stub_status` 验证）。
- 在 Nginx 中暴露 stub_status 端点，例如：

  ```nginx
  server {
      listen 127.0.0.1:80;
      location = /stub_status {
          stub_status;
          access_log off;
          allow 127.0.0.1;
          deny all;
      }
  }
  ```

- 采集节点到 Nginx stub_status 端口网络可达（含安全组 / 防火墙放通）。

> Telegraf `inputs.nginx` 仅采集 7 个核心字段：`accepts`、`active`、`handled`、`requests`、`reading`、`waiting`、`writing`，并以 `port` / `server` 为维度。

## 推荐账号权限

stub_status 端点不需要账号；如果公网必须开放，建议仅监听内网或加 IP 白名单：

```nginx
location = /stub_status {
    stub_status;
    access_log off;
    allow 10.0.0.0/24;
    deny all;
}
```

## 接入步骤

1. 在采集节点验证 stub_status 端点：

   ```bash
   curl http://<host>/stub_status
   ```

   返回包含 `Active connections:`、`accepts handled requests`、`Reading/Writing/Waiting` 等行即可。

2. 在监控接入页填写 URL（默认 `http://<host>/stub_status`）、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

stub_status 端点可达性：

```bash
curl http://<host>/stub_status
```

正常返回 200 + 4-5 行文本。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Nginx stub_status 端点 URL，例如 `http://10.0.0.5/stub_status` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 Nginx 已加载 `stub_status` 模块（`nginx -V 2>&1 | grep stub_status`）。
- 在采集节点用 `curl` 直接访问 `/stub_status` 看是否能拉到 `Active connections:` 文本。
- 等待至少一个采集间隔后再查看。

### 2. 403 / Forbidden

- stub_status 默认建议仅监听 `127.0.0.1`；远程采集时必须把监听 IP 改为 `0.0.0.0` 或对应网卡 IP，并加上 `allow` 白名单。
- 如果 Nginx 上有 `auth_basic`，需在 `inputs.nginx` 加 `username` / `password`（当前模板未启用）。

### 3. 仅采集到 7 个字段

- 这是 stub_status 模块的设计，只暴露 7 个核心指标；如需 `connections_accepted`、`connections_active` 等更细维度，请升级到 Nginx Plus 并改用 `inputs.nginx_plus`。
- 没有 stub_status 模块的 Nginx（如部分发行版裁剪）需重新编译带 `--with-http_stub_status_module`。