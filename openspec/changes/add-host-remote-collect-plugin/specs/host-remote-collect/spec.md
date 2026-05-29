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
