# Solaris主机远程采集

这是 Host 对象下的 Solaris 远程采集。Linux 采集节点按采集间隔 SSH 到 Solaris，执行系统命令。x86 与 SPARC 共用本插件，架构由 `uname -p` 自动识别。目标主机无需安装采集器。无需在表单上选择版本。

采集内容：CPU、负载、内存与交换区、磁盘容量与 inode、磁盘读写与忙碌、网卡、运行时长、操作系统版本。不采集硬件清单、lastlog、lsof 和连接表。

## 怎么用

1. 选择能访问该 Solaris 的 Linux 采集节点。
2. 填写目标主机 IP、SSH 用户名（如 root）、密码或私钥，以及采集间隔。
3. 保存，等一个采集周期，在 Host 里看数据。

## 表单字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 目标主机IP | 是 | Solaris 地址。 |
| 用户名 | 是 | SSH 用户名，例如 `root`。 |
| SSH认证方式 | 是 | 密码或 SSH 密钥。 |
| 密码 / SSH私钥 | 视认证方式 | 选密码则填密码；选密钥则填私钥，口令可空。 |
| 端口 | 否 | 默认 22。 |
| 采集间隔 | 是 | 默认 60 秒。 |
| 节点 | 是 | 执行采集的 Linux 节点。 |

目标主机需能执行 `mpstat`/`sar`、`vmstat`/`prtconf`/`swap`、`df`、`iostat`、`kstat`/`dlstat`/`netstat`、`uname`。缺某条命令时跳过对应指标，其余仍上报。

部署后若控制台还没有本插件，执行 `plugin_init`。

脚本 JSON 与 Prometheus 文本对照见采集脚本旁的 `scripts/solaris/samples/`。
