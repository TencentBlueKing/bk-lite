# Add Host Remote Collect Plugin

Status: done

## Migration Context

- Legacy source: `openspec/changes/add-host-remote-collect-plugin/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

当前监控模块的主机采集依赖 NATS Executor 部署在目标节点上（通过 `ssh.execute.{node_id}` 进行本地命令执行）。Stargazer 已有完整的异步采集任务体系（任务队列 + Worker + NATS 推送 VM），且已有 VMware/QCloud/OceanStor 等通过 Telegraf http input 触发的监控采集模式。Server 侧 Ansible Executor 支持 SSH 和 WinRM 两种连接方式。

需要在 Stargazer 中新增一条通过 Ansible Executor 远程采集主机指标的链路，复用现有 Telegraf http 触发 + 异步队列 + NATS 推送 VM 的架构模式。

## Goals / Non-Goals

**Goals:**
- 实现 Linux（SSH）和 Windows（WinRM）主机基础指标远程无代理采集
- 支持 cpu/mem/disk/net 模块按需选配，通过脚本拼接实现
- 复用现有 Telegraf http → Stargazer → 异步 Worker → NATS → VM 链路
- Windows 脚本兼容 Server 2003+（优先 Get-WmiObject，fallback Get-CimInstance）

**Non-Goals:**
- 不做进程级监控（后续扩展）
- 不做批量主机单次请求采集（当前一次请求采一台）
- 不在 Stargazer 与目标主机间建立直连（必须经过 Ansible Executor）
- 不新增前端页面，复用现有插件配置 UI 体系

## Decisions

### 1. 采集触发方式：Telegraf http input 定时触发

**选择**：Telegraf `[[inputs.http]]` 定时 GET Stargazer API，Stargazer 入队后立即返回 202。

**备选**：
- Celery beat 定时 → 额外引入调度，与现有 VMware 模式不一致
- Stargazer 内部定时器 → 前端无法配置采集频率

**理由**：与 VMware/QCloud 插件保持一致，采集频率由 Telegraf interval 控制，前端配置体验统一。

### 2. 远程执行通道：Ansible Executor adhoc（非 NATS Executor）

**选择**：通过 NATS RPC 调用 Ansible Executor 的 adhoc 接口，使用 shell/win_shell module。

**备选**：
- NATS Executor（需目标节点安装）→ 违背"零安装"需求
- impacket 直连 WMI/DCOM → 绕开现有架构，端口动态分配难管理

**理由**：Ansible Executor 部署在中控节点，目标节点零安装；WinRM 走标准 5985/5986 端口，防火墙友好。

### 3. 脚本策略：模块化片段拼接

**选择**：按 os_type 维护 header/cpu/mem/disk/net/footer 脚本片段，运行时按用户选择的 modules 拼接成完整脚本一次性执行。

**备选**：
- 每个模块单独执行一次 adhoc → 多次 NATS 往返，延迟翻倍
- 固定全量脚本 → 无法按需裁剪

**理由**：一次 adhoc 调用完成所有采集，减少网络开销；模块化便于后续扩展新指标。

### 4. 脚本输出格式：JSON

**选择**：脚本 stdout 输出标准 JSON，Stargazer Worker 解析后转 Prometheus metrics 推送 VM。

**理由**：JSON 解析可靠，跨平台一致，便于扩展字段。

### 5. ansible_node_id 获取：Telegraf header 注入

**选择**：由 Telegraf 配置模板渲染时注入 `ansible_node_id` header。

**理由**：与 VMware 模式一致（凭据通过 header 传递），部署时云区域信息已知。

### 6. NATS RPC 调用封装

**选择**：在 Stargazer 中新增 `core/ansible_rpc.py`，封装 Ansible Executor adhoc 调用，subject 格式参考 Server 侧 `apps/rpc/ansible.py`。

**理由**：Stargazer 现有 `core/nats_utils.py` 的 `nats_request` 可直接复用，只需构造正确的 subject 和 payload。

## Risks / Trade-offs

- **WinRM 未开启** → 文档明确前置条件，采集失败时返回明确错误信息
- **Ansible adhoc 超时（目标主机网络不通）** → 设置 execute_timeout，Worker 不阻塞
- **脚本兼容性（老版本 Windows）** → Get-WmiObject 优先，try-catch fallback
- **单次采集延迟（SSH/WinRM 建连）** → 可接受范围（秒级），不影响 Telegraf 定时触发
- **Ansible Executor 未部署** → 任务执行失败，NATS 超时，采集指标上报 error 状态

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-29
```

## Capability Deltas

### host-remote-collect

## ADDED Requirements

### Requirement: Stargazer 提供主机指标采集 HTTP API
Stargazer SHALL 提供 `GET /api/monitor/host/metrics` 端点，接收 Telegraf 的定时采集请求，将采集任务入队后立即返回 Prometheus 格式的 accepted 响应。

#### Scenario: 正常触发采集
- **WHEN** Telegraf 发送 GET 请求，headers 包含 host、os_type、username、password、port、metrics_modules 及标准 Tags
- **THEN** Stargazer 将采集任务入队，返回 HTTP 200，body 为 Prometheus 格式文本包含 task_id 和 status="queued"

#### Scenario: 缺少必要参数
- **WHEN** 请求缺少 host 或 username 或 password
- **THEN** 返回 Prometheus 格式 error 指标，不入队任务

### Requirement: 异步 Worker 通过 Ansible Executor 执行远程采集
HostCollector Worker SHALL 根据 os_type 拼接对应脚本，通过 NATS RPC 调用 Ansible Executor adhoc 接口，在目标主机执行采集命令。

#### Scenario: Linux 主机采集
- **WHEN** os_type 为 linux，metrics_modules 为 "cpu,mem,disk,net"
- **THEN** Worker 拼接 bash 脚本（header + cpu + mem + disk + net + footer），通过 Ansible adhoc 以 shell module、connection=ssh 执行，解析 JSON stdout

#### Scenario: Windows 主机采集
- **WHEN** os_type 为 windows，metrics_modules 为 "cpu,mem"
- **THEN** Worker 拼接 PowerShell 脚本（header + cpu + mem + footer），通过 Ansible adhoc 以 win_shell module、connection=winrm 执行，解析 JSON stdout

#### Scenario: Ansible Executor 超时
- **WHEN** NATS RPC 调用 Ansible Executor 超时
- **THEN** Worker 记录错误日志，推送 error 状态指标到 VictoriaMetrics

### Requirement: 模块化脚本按需拼接
系统 SHALL 维护 Linux（bash）和 Windows（PowerShell）两套模块化采集脚本片段（cpu/mem/disk/net），根据请求中 metrics_modules 参数动态拼接。

#### Scenario: 部分模块采集
- **WHEN** metrics_modules 为 "cpu,mem"
- **THEN** 仅拼接 header + cpu 片段 + mem 片段 + footer，不包含 disk 和 net

#### Scenario: 全量模块采集
- **WHEN** metrics_modules 为 "cpu,mem,disk,net"
- **THEN** 拼接 header + cpu + mem + disk + net + footer 全部片段

### Requirement: 脚本输出标准 JSON 格式
采集脚本 SHALL 输出标准 JSON 到 stdout，包含各模块对应的指标数据。HostCollector 解析后转为 Prometheus metrics 格式推送至 VictoriaMetrics。

#### Scenario: Linux 脚本输出
- **WHEN** Linux 脚本执行成功
- **THEN** stdout 输出 JSON 对象，包含 cpu/mem/disk/net 对应的指标字段

#### Scenario: Windows 脚本输出
- **WHEN** Windows 脚本执行成功
- **THEN** stdout 输出与 Linux 结构一致的 JSON 对象

### Requirement: Windows 脚本广泛兼容
Windows 采集脚本 SHALL 优先使用 Get-WmiObject（兼容 Server 2003+），仅在 Get-WmiObject 不可用时 fallback 到 Get-CimInstance。

#### Scenario: 旧版 Windows（Server 2008）
- **WHEN** 目标主机为 Windows Server 2008，仅有 Get-WmiObject
- **THEN** 脚本使用 Get-WmiObject 成功采集指标

#### Scenario: 新版 Windows（Server 2016+）
- **WHEN** 目标主机为 Windows Server 2016，Get-WmiObject 已弃用
- **THEN** 脚本 fallback 到 Get-CimInstance 成功采集指标

### Requirement: Server 侧注册 Telegraf http 类型主机插件
Server monitor 模块 SHALL 新增插件模板（collector=Telegraf, collect_type=http, 对象=host），包含 UI.json（前端配置表单）、host.child.toml.j2（Telegraf 子配置模板）、metrics.json（指标定义）、policy.json（告警策略模板）。

#### Scenario: 用户通过前端配置主机采集
- **WHEN** 用户在监控插件管理中选择"主机"插件，填写目标 IP、OS 类型、凭据、端口、采集模块
- **THEN** 系统生成对应 Telegraf http input 子配置，下发到采集节点

### Requirement: ansible_node_id 通过 Telegraf header 注入
Telegraf 子配置模板 SHALL 将云区域绑定的 Ansible Executor 实例 ID 渲染到 header 中传给 Stargazer。

#### Scenario: 采集请求携带 ansible_node_id
- **WHEN** Telegraf 发送采集请求
- **THEN** 请求 header 中包含 ansible_node_id，值为该云区域对应的 Ansible Executor 实例 ID

## Work Checklist

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
