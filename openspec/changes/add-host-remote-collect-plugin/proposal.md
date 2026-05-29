## Why

监控模块当前缺少对主机（Linux/Windows）基础指标的远程无代理采集能力。现有主机采集依赖在目标节点安装 NATS Executor，不满足"目标节点零安装"的场景需求。需要通过 Ansible Executor（SSH/WinRM）实现远程主机指标采集，复用现有 NATS 链路将数据推送至 VictoriaMetrics。

## What Changes

- 新增 Stargazer HTTP API `/api/monitor/host/metrics`，接收 Telegraf 定时触发的采集请求
- 新增 Stargazer 异步采集器 `HostCollector`，通过 NATS RPC 调用 Ansible Executor 执行 SSH/WinRM adhoc 命令
- 新增模块化采集脚本（Linux bash / Windows PowerShell），支持按需拼接 cpu、mem、disk、net 模块
- 新增 Stargazer 侧 Ansible Executor NATS RPC 调用封装
- 新增 Server 侧 Monitor 插件模板（Telegraf http 类型），包含 UI.json、host.child.toml.j2、metrics.json、policy.json
- 新增 Stargazer Worker 中 host 类型任务的路由注册

## Capabilities

### New Capabilities
- `host-remote-collect`: 基于 Ansible Executor（SSH/WinRM）的主机远程无代理指标采集能力，支持 CPU/内存/磁盘/网络模块化按需采集

### Modified Capabilities

## Impact

- **Stargazer**: 新增 API 路由、采集器、脚本文件、Ansible RPC 封装、Worker 任务注册
- **Server (monitor app)**: 新增插件模板文件（support-files/plugins/Telegraf/http/host/）
- **依赖**: 需要目标云区域部署 Ansible Executor 实例，目标 Windows 主机需开启 WinRM
- **API**: 新增 Stargazer HTTP 端点，不影响现有接口
