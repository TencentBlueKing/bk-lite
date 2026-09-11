# FreeBSD主机远程采集

这是 Host 对象下的 FreeBSD 远程采集。Linux 采集节点按采集间隔 SSH 到 FreeBSD，执行系统命令。目标主机无需安装采集器。无需在表单上选择版本，版本由 `uname` / `freebsd-version` 自动识别。

采集内容：CPU、负载、内存与交换区、磁盘容量与 inode、磁盘读写与忙碌、网卡、运行时长、操作系统版本。不采集硬件清单、lastlog、lsof 和连接表。

## 怎么用

1. 选择能访问该 FreeBSD 的 Linux 采集节点。
2. 填写目标主机 IP、SSH 用户名（如 root）、密码或私钥，以及采集间隔。
3. 保存，等一个采集周期，在 Host 里看数据。

## 表单字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 目标主机IP | 是 | FreeBSD 地址。 |
| 用户名 | 是 | SSH 用户名，例如 `root`。 |
| SSH认证方式 | 是 | 密码或 SSH 密钥。 |
| 密码 / SSH私钥 | 视认证方式 | 选密码则填密码；选密钥则填私钥，口令可空。 |
| 端口 | 否 | 默认 22。 |
| 采集间隔 | 是 | 默认 60 秒。 |
| 节点 | 是 | 执行采集的 Linux 节点。 |

目标主机需能执行 `sysctl`、`vmstat`、`swapinfo`、`df`、`iostat`、`netstat`、`uname`。缺某条命令时跳过对应指标，其余仍上报。

## 命令与回退

| 指标 | 主命令 | 回退 |
| --- | --- | --- |
| CPU | `sysctl kern.cp_time` 两次采样相减 | `vmstat 1 2` 末行 us/sy。无 Linux 风格 iowait，`cpu_usage_iowait_total` 固定为 0。 |
| 负载 | `sysctl vm.loadavg` | `uptime` 的 load average。 |
| 运行时长 | `sysctl kern.boottime` 与 `date +%s` 相减 | 无。 |
| 内存 | `sysctl hw.physmem` 与 `vm.stats.vm.v_*_count`（active+wired+laundry） | `v_page_count * pagesize` 作总量。 |
| 交换区 | `swapinfo -k` | 无交换设备时总量与空闲为 0。 |
| 磁盘 | `df -kT`（无 Type 时 `df -kP`）与 `df -i` | 跳过 devfs/procfs/fdescfs 等伪文件系统。 |
| 磁盘 IO | `iostat -x -w 1 -c 2` 末次采样（kr/s、kw/s、%b） | `iostat -Ix` 提供 since-boot 累计；无 `-I` 时不上报 total。 |
| 网卡 | `netstat -ibn` 的 `<Link>` 行 | `netstat -ib`。 |
| OS 版本 | `freebsd-version` | `uname -r`；架构来自 `uname -p` / `uname -m`。 |

脚本 JSON 与 Prometheus 文本对照见采集脚本旁的 `scripts/freebsd/samples/`。

部署后若控制台还没有本插件，执行 `plugin_init`。
