## 1. Stargazer - Ansible RPC 封装

- [x] 1.1 新增 `agents/stargazer/core/ansible_rpc.py`，封装 Ansible Executor adhoc NATS RPC 调用（subject 构造、payload 格式、超时处理）

## 2. Stargazer - 采集脚本

- [x] 2.1 新增 `agents/stargazer/tasks/collectors/scripts/linux/header.sh` 和 `footer.sh`（JSON 输出框架）
- [x] 2.2 新增 `agents/stargazer/tasks/collectors/scripts/linux/cpu.sh`（CPU 使用率、核数、负载）
- [x] 2.3 新增 `agents/stargazer/tasks/collectors/scripts/linux/mem.sh`（内存总量、使用、可用、swap）
- [x] 2.4 新增 `agents/stargazer/tasks/collectors/scripts/linux/disk.sh`（磁盘分区使用率）
- [x] 2.5 新增 `agents/stargazer/tasks/collectors/scripts/linux/net.sh`（网卡流量、错误数）
- [x] 2.6 新增 `agents/stargazer/tasks/collectors/scripts/windows/header.ps1` 和 `footer.ps1`
- [x] 2.7 新增 `agents/stargazer/tasks/collectors/scripts/windows/cpu.ps1`（Get-WmiObject Win32_Processor，fallback Get-CimInstance）
- [x] 2.8 新增 `agents/stargazer/tasks/collectors/scripts/windows/mem.ps1`（Get-WmiObject Win32_OperatingSystem）
- [x] 2.9 新增 `agents/stargazer/tasks/collectors/scripts/windows/disk.ps1`（Get-WmiObject Win32_LogicalDisk）
- [x] 2.10 新增 `agents/stargazer/tasks/collectors/scripts/windows/net.ps1`（Get-WmiObject Win32_NetworkAdapterConfiguration + PerfRawData）

## 3. Stargazer - HostCollector

- [x] 3.1 新增 `agents/stargazer/tasks/collectors/host_collector.py`，实现脚本拼接逻辑（根据 os_type + metrics_modules 组装完整脚本）
- [x] 3.2 实现 Ansible adhoc 调用（根据 os_type 选择 shell/win_shell module 和 ssh/winrm connection）
- [x] 3.3 实现结果解析（JSON stdout → Prometheus metrics 格式化）
- [x] 3.4 实现数据推送（复用现有 NATS → VM 推送链路）

## 4. Stargazer - API 路由与 Worker 注册

- [x] 4.1 在 `agents/stargazer/api/monitor.py` 新增 `/host/metrics` 路由（解析 headers、参数校验、enqueue_collect_task、返回 accepted 响应）
- [x] 4.2 在 `agents/stargazer/core/worker.py` 中注册 host 类型任务路由（`monitor_type == "host"` → `collect_host_metrics_task`）
- [x] 4.3 新增 `agents/stargazer/tasks/handlers/monitor_handler.py` 中 `collect_host_metrics_task` 函数

## 5. Server - Monitor 插件模板

- [x] 5.1 新增 `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`（目标 IP、OS 类型、凭据、端口、采集模块选择表单）
- [x] 5.2 新增 `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`（Telegraf http input 子配置模板，含 headers 渲染）
- [x] 5.3 新增 `server/apps/monitor/support-files/plugins/Telegraf/http/host/metrics.json`（cpu/mem/disk/net 指标定义）
- [x] 5.4 新增 `server/apps/monitor/support-files/plugins/Telegraf/http/host/policy.json`（基础告警策略模板）
