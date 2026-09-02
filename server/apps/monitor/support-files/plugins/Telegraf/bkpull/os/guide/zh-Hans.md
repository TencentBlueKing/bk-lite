# Host AIX 监控接入指南

本插件由平台将官方 `node_exporter` 安装到目标 AIX 主机，并由 Linux 采集节点通过 Telegraf Prometheus 拉取 `:9100/metrics`。不要自行从 GitHub 或其他外部源下载或安装 `node_exporter`。

## 前置要求

- 目标主机为 AIX 7.2 / 7.3，架构为 POWER8 及以上的 `ppc64`。
- 采集节点必须是 Linux 节点，且能访问目标主机的 `9100` 端口。
- 保存配置时，平台通过采集节点 SSH（默认 `22`）把官方 `node_exporter` 1.12.1（aix-ppc64）复制到 `/opt/bklite/node_exporter`，并用 SRC 以 root 启动，监听 `0.0.0.0:9100`。
- SSH 账号需要有安装目录写入、`mkssys` / `startsrc` / `stopsrc` 权限；推荐使用 `root`。
- SRC 子系统名固定为 `node_exporter`。子系统已存在时不会重复 `mkssys`，升级会先停止再替换二进制后启动。

## 接入步骤

1. 选择 Linux 采集节点，填写目标 AIX 主机 IP、实例名称和 SSH 认证信息。
2. 确认采集间隔和 `node_exporter` 监听端口（默认 `9100`）。
3. 执行接入前校验：平台会按「复制 → 启动 → 拉取 → 指标」顺序探测，任一步失败即停止。
4. 保存配置。平台会下发 Linux 侧 Telegraf 拉取配置，并在事务提交后安装或更新 AIX 上的 `node_exporter`。仅修改采集间隔时不会重新复制安装包。
5. 等待至少一个采集周期。默认采集间隔为 `60` 秒。

部署后必须执行 `plugin_init`，否则插件元数据不会进入监控对象。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 节点 | 是 | 无 | 执行拉取和远程安装的 Linux 采集节点。 |
| 目标主机IP | 是 | 无 | AIX 主机地址；Linux 采集节点会拉取 `http://<IP>:<端口>/metrics`。 |
| 实例名称 | 是 | 无 | 平台中的展示名称，默认可由目标主机 IP 带出后再调整。 |
| 用户名 | 是 | `root` | SSH 登录用户名，仅用于安装和探测，不会写入拉取配置。 |
| Linux认证方式 | 否 | 密码 | Linux SSH 认证方式。 |
| 密码 | 是 | 无 | SSH/WinRM 登录密码 |
| SSH私钥 | 否 | 无 | Linux SSH 私钥内容，仅认证方式为 SSH密钥 时使用 |
| SSH私钥口令 | 否 | 无 | Linux SSH 私钥口令，可为空 |
| 端口 | 否 | `9100` | `node_exporter` 监听和拉取端口，不是 SSH 端口。SSH 固定使用 `22`。 |
| 采集间隔 | 是 | `60` 秒 | 监控数据的采集时间间隔（单位：秒） |
| 组 | 否 | 无 | 实例所属分组。 |

## 接入后验证

1. 在 AIX 主机上确认 SRC 子系统 `node_exporter` 已运行，并监听 `9100`。
2. 从 Linux 采集节点访问 `http://<目标主机IP>:9100/metrics`，应能看到 `node_cpu_`、`node_memory_`、`node_filesystem_`、`node_load` 和 `node_partition_` 指标。
3. 等待至少一个采集周期后，在主机对象中确认 CPU、内存、磁盘、网络和 LPAR 指标有数据。

## 常见问题

### 保存成功但没有指标

确认 Linux 采集节点到 AIX `9100` 端口可达，且 `plugin_init` 已执行。拉取配置里不应出现 SSH 用户名或密码。

### SRC 启动失败

安装和启动需要 root。确认账号能执行 `mkssys`、`startsrc` 和 `stopsrc`，且 `/opt/bklite/node_exporter` 可写。

### 重复保存出现多个拉取目标

编辑同一实例会更新已有 `bkpull/aix` 子配置，不会新建第二份 `inputs.prometheus`。
