# AIX 主机采集接入指南（驻留 ksh）

本插件由平台把 **同一份原始 ksh** 安装到 AIX 主机（优先注册 SRC 子系统 `bklite_osmon`，否则写入带标记的 crontab），再由 **Linux 采集节点** SSH 执行 `/usr/bin/ksh -c '/opt/bk-lite/aix/os_monitor.ksh'`。AIX 不是 bk-lite Node，不要在 AIX 上安装 Telegraf、node_exporter 或开放 `:9100`。用户不必安装 Splunk Add-on。

重新保存实例会 **更新已有子配置**，不会再堆一个新的 uuid。

## 前置要求

- 采集节点能 SSH 访问目标 AIX 主机（默认端口 22），并有权限写入 `/opt/bk-lite/aix/`。
- 目标为 AIX 7.2 或 7.3（POWER8+）。脚本自动跳过缺失命令，不要按 5.x/6.x 使用。
- 监控账号需要执行：`uptime`、`vmstat`、`svmon`、`lsps`、`mpstat`、`lparstat`、`df`、`iostat`、`ps`、`ifconfig`、`netstat`、`oslevel`。SRC 安装还需要 `mkssys`/`lssrc`；否则回退 cron。
- 防火墙只需放行 SSH，不要为 `:9100` 开口。

## 接入步骤

1. 选择一台能访问该 AIX 的 Linux 采集节点。
2. 填写主机 IP、用户名（默认 `root`）、SSH 认证方式（密码或 SSH 密钥）和采集间隔（默认 60 秒）。
3. 保存后平台会把 ksh 安装到 `/opt/bk-lite/aix/os_monitor.ksh`，再按间隔 SSH 执行该脚本。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 目标主机IP | 是 | AIX 主机地址。 |
| 用户名 | 是 | SSH 用户，默认 `root`。 |
| SSH认证方式 | 是 | 密码或 SSH 密钥。 |
| 密码 / SSH私钥 | 视认证方式 | 凭据加密保存，日志不会打印私钥。 |
| 端口 | 否 | SSH 端口，默认 22。 |
| 采集间隔 | 是 | 默认 60 秒。 |
| 节点 | 是 | 执行 SSH 与文件下发的 Linux 采集节点。 |

## 接入后验证

确认 AIX 上存在 `/opt/bk-lite/aix/os_monitor.ksh`，并在一个采集周期后查询 `cpu_usage_total`、`mem_used_percent`、`disk_used_percent`。仪表盘复用主机（Host）仪表盘。

部署后请在控制台执行 `plugin_init`（或 `batch_init`）导入本插件定义。
