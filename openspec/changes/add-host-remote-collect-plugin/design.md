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
