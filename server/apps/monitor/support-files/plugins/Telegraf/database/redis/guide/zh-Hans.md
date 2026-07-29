# Redis 监控接入指南

## 前置要求

- 目标实例已启动 Redis 服务，默认可访问 `6379` 端口。
- 采集节点到 Redis 地址网络可达（含安全组 / 防火墙放通）。
- 已准备具备 INFO 命令查询权限的账号（仅 Redis 6+ 启用 ACL 时才需要用户名）。
- 若 Redis 设置了 `requirepass`，请准备好对应的连接密码；未启用认证时可留空。
- 监控采集通过 Telegraf `inputs.redis` 插件发起，地址形如 `tcp://<host>:<port>`，指标来自 `INFO` 命令。

## 推荐账号权限

账号至少能执行：

- `INFO`（默认 `INFO server`、`INFO clients`、`INFO memory` 等子命令）

若未启用 ACL / `requirepass`，可使用空用户名空密码接入；生产环境建议使用专用只读监控账号，避免直接使用 root 或具备 `CONFIG`、`SHUTDOWN` 等高权限命令的账号。

## 接入步骤

1. 在采集节点上确认可访问目标 Redis（见下方接入前校验）。
2. 在监控对象接入页填写主机、端口、用户名（可选）、密码（可选）和采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、主机、端口、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

无认证（若环境允许）可执行：

```bash
redis-cli -h <host> -p <port> INFO server
```

带密码：

```bash
redis-cli -h <host> -p <port> -a <password> INFO server
```

Redis 6+ 启用 ACL 时带用户名：

```bash
redis-cli -h <host> -p <port> --user <username> -a <password> INFO server
```

满足以下条件可认为端点基本可用：

- 命令成功返回，且包含 `redis_version`、`uptime_in_seconds` 等字段
- 端口放通、网络可达，且认证信息（若启用）正确

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | 仅 Redis 6+ 启用 ACL 时填写；未启用 ACL 可留空 |
| 密码 | 否 | Redis 设置 `requirepass` 时填写对应密码，未启用认证可留空 |
| 主机 | 是 | Redis 服务所在主机地址（采集目标，非探针节点） |
| 端口 | 是 | Redis 服务端口，默认 `6379` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 采集节点 |
| 实例名称 | 是 | 平台内展示的实例名 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 核对主机地址与端口是否正确，协议默认 `tcp://`。
- 在采集节点上重新执行上述 `redis-cli` 命令，确认不是仅控制台可达。
- 等待至少一个采集间隔后再查看。
- 检查节点上 Telegraf / 采集任务是否正常运行。

### 2. 认证失败（NOAUTH / WRONGPASS）

- 确认密码无首尾空格与特殊字符转义问题。
- 若 Redis 6+ 启用了 ACL，确认用户名与密码组合正确，且账号至少具备 `INFO` 权限。
- 若未启用认证，确认页面密码字段为空、Redis 配置未设置 `requirepass`。

### 3. 仅部分指标缺失

- `inputs.redis` 默认依赖 `INFO` 命令返回；自定义指标需确认 Redis 版本支持。
- 权限不足时可能出现基础指标正常但部分子命令失败，请分别验证 `INFO server`、`INFO clients`、`INFO memory` 等子命令。
- ACL 模式下账号权限不足时，仅暴露与权限匹配的字段。
