# AIX 主机远程采集接入指南

本插件由 **Linux 采集节点** 通过 SSH 以 `/usr/bin/ksh -c` 执行平台提供的原始 ksh，采集 AIX 7.2/7.3（POWER8+）主机指标。用户 **不必** 在 AIX 上安装 Splunk Add-on for Unix and Linux、node_exporter、Telegraf 或开放 `:9100`。

## 前置要求

- 采集节点能 SSH 访问目标 AIX 主机（默认端口 22）。
- 目标为 AIX 7.2 或 7.3。脚本会跳过当前系统没有的命令（例如部分环境无 `svmon`），不要按 5.x/6.x 使用。
- 监控账号需要执行：`uptime`、`vmstat`、`svmon`、`lsps`、`mpstat`、`lparstat`、`df`、`iostat`、`ps`、`ifconfig`、`netstat`、`oslevel`。
- 防火墙只需放行采集节点到 AIX 的 SSH；不要为 `:9100` 开口。

## 接入步骤

1. 选择一台能访问该 AIX 的 Linux 采集节点。
2. 填写主机 IP、用户名（默认 `root`）、SSH 认证方式（密码或 SSH 密钥）和采集间隔（默认 60 秒）。
3. 保存后等待至少一个采集周期。每次采集都会从采集节点 SSH 执行 ksh，不会在 AIX 上常驻脚本。

重新保存实例会 **更新已有子配置**，不会再堆一个新的 uuid。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 目标主机IP | 是 | AIX 主机地址。 |
| 用户名 | 是 | SSH 用户，默认 `root`。 |
| SSH认证方式 | 是 | 密码或 SSH 密钥。 |
| 密码 / SSH私钥 | 视认证方式 | 凭据加密保存，日志不会打印私钥。 |
| 端口 | 否 | SSH 端口，默认 22。 |
| 采集间隔 | 是 | 默认 60 秒。 |
| 节点 | 是 | 执行 SSH 的 Linux 采集节点。 |

## 接入后验证

保存并等待一个采集周期后，确认可查询 `cpu_usage_total`、`mem_used_percent`、`disk_used_percent`、`system_load1`。仪表盘复用主机（Host）仪表盘。

部署后请在控制台执行 `plugin_init`（或 `batch_init`）导入本插件定义。

## 常见问题

### 命令缺失

AIX 7.x 会跳过当前不存在的命令（例如 `svmon`），对应指标为 0 或缺测，不影响其余指标。

### 认证失败

核对采集节点到 AIX 的 SSH 连通性、用户名和认证方式。不要把 Linux Host Remote 的 WinRM 字段用在 AIX 上。
