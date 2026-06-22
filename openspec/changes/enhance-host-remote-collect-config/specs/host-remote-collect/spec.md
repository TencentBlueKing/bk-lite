## MODIFIED Requirements

### Requirement: Server 侧注册 Telegraf http 类型主机插件
Server monitor 模块 SHALL provide a Telegraf http host remote collection plugin whose configuration form supports OS-specific credential and protocol options without relying on Job target credentials.

#### Scenario: 用户通过前端配置 Linux 密码采集
- **WHEN** 用户选择 os_type 为 linux，auth_type 为 password，填写 host、username、password、port 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 Linux SSH 密码采集所需字段，metrics_modules 由所选模块渲染生成

#### Scenario: 用户通过前端配置 Linux 密钥采集
- **WHEN** 用户选择 os_type 为 linux，auth_type 为 private_key，填写 host、username、private_key_content、可选 private_key_passphrase、port 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 SSH 私钥采集所需字段，敏感字段使用现有加密/env 占位机制

#### Scenario: 用户通过前端配置 Windows WinRM 采集
- **WHEN** 用户选择 os_type 为 windows，填写 host、username、password、port、winrm_scheme、winrm_transport、winrm_cert_validation 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 Windows WinRM 采集所需字段

#### Scenario: Windows 使用默认 WinRM 配置
- **WHEN** 用户选择 os_type 为 windows 且未显式修改 WinRM 参数
- **THEN** 默认配置为 port=5986、winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false

#### Scenario: Windows 选择 Basic 认证
- **WHEN** 用户选择 winrm_transport 为 basic
- **THEN** 配置表单说明 SHALL 提示目标 Windows 需要开启 Basic 认证，默认 Windows 通常未开启

### Requirement: 异步 Worker 通过 Ansible Executor 执行远程采集
HostCollector Worker SHALL construct Ansible Executor `host_credentials` from monitor-side parameters, including OS-specific credential fields, and SHALL keep Job target credentials independent from monitor credentials.

#### Scenario: Windows WinRM 参数传递
- **WHEN** os_type 为 windows 且请求包含 winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false
- **THEN** Worker 调用 Ansible Executor adhoc 时 host_credentials 包含 connection=winrm、winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false

#### Scenario: Windows 旧配置兼容
- **WHEN** os_type 为 windows 且旧配置未包含 winrm_scheme、winrm_transport 或 winrm_cert_validation
- **THEN** Worker 使用 https、ntlm、false 作为默认值构造 host_credentials

#### Scenario: Linux 私钥凭据传递
- **WHEN** os_type 为 linux 且 auth_type 为 private_key
- **THEN** Worker 调用 Ansible Executor adhoc 时 host_credentials 包含 connection=ssh、private_key_content，并在提供时包含 private_key_passphrase

#### Scenario: Linux 旧配置兼容
- **WHEN** os_type 为 linux 且旧配置未包含 auth_type
- **THEN** Worker 按 password 模式构造 host_credentials

### Requirement: 模块化脚本按需拼接
系统 SHALL support selectable remote host metric modules using UI-controlled values while accepting legacy comma-separated module strings.

#### Scenario: UI 多选模块
- **WHEN** metrics_modules 由表单多选产生为 ["cpu", "mem", "disk"]
- **THEN** Worker SHALL treat it equivalently to "cpu,mem,disk" and only拼接对应模块

#### Scenario: 旧字符串模块
- **WHEN** metrics_modules 为 "cpu,mem,disk,net"
- **THEN** Worker SHALL continue to parse the string and拼接对应模块

### Requirement: 远程主机指标尽量对齐本地 Telegraf Host 指标
Remote host collection SHALL expand metric coverage toward the local Telegraf host plugin and SHALL prefer local Telegraf metric names when the collected value has matching semantics.

#### Scenario: 基础指标对齐
- **WHEN** 用户选择 cpu、mem、disk、net 模块
- **THEN** 输出指标 SHALL include Telegraf-aligned CPU usage, memory, disk, and network metrics where available on the target OS

#### Scenario: 扩展模块采集
- **WHEN** 用户选择 diskio、processes 或 system 模块
- **THEN** Worker SHALL include the corresponding script fragments and emit supported metrics without causing other selected modules to fail when one expanded module is unavailable

#### Scenario: 语义不匹配的 Telegraf 指标
- **WHEN** remote scripts cannot collect a value with the same semantics as a local Telegraf metric, such as a persistent interval-based rate
- **THEN** implementation SHALL avoid misleading metric-name reuse or document the remote-specific semantics in metrics metadata

#### Scenario: GPU 指标
- **WHEN** local Telegraf host plugin includes GPU metrics
- **THEN** remote host collection SHALL NOT require GPU metrics by default because they depend on target-specific tooling
