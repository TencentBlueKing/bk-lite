# Windows 控制器远程安装

Status: implemented

## Problem Statement

Windows 控制器当前只能由用户下载 GUI 安装器后登录主机手动安装。节点管理的“远程安装”任务虽然允许接收 Windows 节点，但实际复用了 Linux SSH 命令执行链路，无法正确连接 WinRM，也会让旧版 PowerShell 的 TLS 下载能力成为兼容性风险。

## Solution

Windows 远程安装采用“Ansible Executor 负责 WinRM 编排，原生 Go bootstrap 负责安装”的两段式链路：

1. Server 创建与目标主机、安装包和云区域绑定的短期安装会话。
2. Server 在目标云区域选择一个 `ansibleexecutor_linux` 状态正常的容器节点。
3. Ansible Executor 从 Server NATS Object Store 获取 Windows x86_64 bootstrap，并通过 WinRM 复制到目标主机临时目录。
4. Executor 把安装会话 URL 写入临时文件，以 `argv` 调用 bootstrap 的 `--url-file` 参数，不把会话放入命令行。
5. Go bootstrap 使用自身 HTTP/TLS 与 NATS 客户端获取配置和控制器包，在 staging 目录完成有界解压和校验后切换安装目录并注册服务。
   Server 会话校验当前 `execution_id + attempt` 租约并签发不可延长的执行截止时间；同一安装目录同时使用操作系统文件锁和原子持久化的单调 fencing 记录，bootstrap 在切换目录前再次校验截止时间，拒绝超时、旧任务或重复任务修改安装目录。
6. 新服务启动失败时恢复原目录和原服务；若服务管理器连续拒绝停止失败的新服务，则不得冒险替换其在用目录，应保留原目录备份并返回不可自动重试的人工恢复状态；成功切换保留 `cache`、`logs`、`generated` 运行数据。
7. bootstrap 将与 stdout 相同的结构化事件实时发布到 `installer.progress.<execution_id>`；Server 消费实时事件，并对 Ansible 终态 stdout 回放按事件内容去重。
8. Ansible `always` 与 Server 侧兜底清理共同删除临时会话文件和 bootstrap；最终成功仍以 Sidecar 回连为准。

这条链路不依赖 PowerShell 的 SSL/TLS 下载能力。Ansible Windows 模块自身仍通过 Windows PowerShell/WinRM 运行模块包装代码，所以这不是“目标机完全不需要 PowerShell”；第一版兼容性基线是 Windows 10 / Windows Server 2016、PowerShell 5.1 或更高版本，执行 bootstrap 前显式预检。安装器的网络下载和 TLS 校验由 Go 实现。

## Compatibility And Security Decisions

- 第一版只支持 Windows x86_64，与现有 Windows Controller 包能力一致。
- 第一版固定使用 HTTPS/5986、NTLM，并校验服务端证书；HTTP、Basic、Kerberos、CredSSP 和关闭证书校验暂不开放。
- 自签名 WinRM 证书必须通过 Ansible Executor 的受控 CA 信任配置解决，不提供跳过校验开关。
- Windows 远程安装会话和会话返回的 Server URL 必须为 HTTPS；bootstrap 拒绝 HTTP 和 HTTPS 降级重定向。
- Windows 远程安装只接受密码凭据，不接受 SSH 私钥。
- 密码继续使用现有 AES 字段暂存，并在单节点任务结束后清空。
- 安装会话 URL 通过权限受限的 Ansible vars 文件传递，不进入 Executor 进程参数；相关任务启用 `no_log`，任务结束后删除远端会话文件。
- Executor 恢复执行所需的敏感载荷使用版本化 Fernet 密文持久化，优先使用 `ANSIBLE_PAYLOAD_ENCRYPTION_KEY`，未配置时沿用部署注入的 NATS 密码派生密钥。
- 控制器包下载上限为 4 GiB、解压上限为 8 GiB/100000 个文件；超过边界时在停止旧服务前失败。
- Ansible Executor 必须与目标节点同云区域且 `ansibleexecutor_linux` 采集器健康；找不到时快速失败，不跨区域兜底。
- `ansible.windows` 固定为 3.7.0，与仓库现有 `ansible-core==2.18.6` 组合构建，避免部署时自动获取不兼容的新版本。
- 实时事件 subject 只接受由 Server 生成的 32 位小写十六进制 execution ID；安装器 NATS 用户仅需 `installer.progress.>` 发布权限，发布失败降级到终态 stdout，不阻断安装。
- Windows 远程安装会话只下发专用 `NATS_INSTALLER_USERNAME/PASSWORD`，且要求 `NATS_PROTOCOL=tls`；不得回退管理员账号或通过明文 NATS 传输凭据。Windows GUI 手动安装保留原有兼容策略。

## Component Boundary

该能力不是只修改节点管理 App：

- `server/apps/node_mgmt`：API 参数、任务编排、Executor 选择、安装会话和状态收敛。
- `agents/ansible-executor`：WinRM 与 Windows 文件分发运行时，并固定 collection 版本。
- `agents/sidecar-installer`：生成无 GUI 的 Windows bootstrap，完成实际下载和安装。
- `web/src/app/node-manager`：开放 Windows 远程安装入口并收集主机与凭据；固定 WinRM 安全参数不向用户暴露。

不新增独立 WinRM 服务；Server 只调用现有 Ansible Executor RPC，从而复用凭据转 inventory、异步任务查询、NATS 文件分发和 Windows 模块能力。

## Operational Requirements

面向运维发布和流水线改造的完整步骤见
[`docs/operations/windows-controller-remote-install-release.md`](../../../docs/operations/windows-controller-remote-install-release.md)。

发布前必须：

1. 构建 `agents/sidecar-installer` 的 release artifacts。
2. 将 `dist/windows/x86_64/bklite-controller-bootstrap.exe` 通过 `installer_init --variant bootstrap` 上传到 `installer/windows/x86_64/bklite-controller-bootstrap.exe`。
3. 重新构建并发布 Ansible Executor，使其包含固定版本的 `ansible.windows`、`pywinrm` 与载荷加密依赖。
4. 执行 NodeMgmt 数据库迁移。
5. 确认每个需要 Windows 远程安装的云区域至少有一个健康 Ansible Executor。
6. 在目标 Windows 主机预配置 WinRM listener、防火墙、认证方式与证书信任。
7. 为安装器 NATS 用户配置 `installer.progress.>` 发布权限，并允许 Server 账号订阅。
8. 为 Windows 远程安装配置 `NATS_PROTOCOL=tls`、可信服务端证书和专用安装器账号；明文 NATS 或管理员账号回退会快速失败。

## Acceptance Criteria

- Windows 在控制器安装页可选择远程安装，默认账号为 Administrator；5986、HTTPS、NTLM 和证书校验作为固定安全基线隐藏传递。
- Windows 任务不会调用现有 SSH 执行方法。
- bootstrap 下发失败、WinRM 连接失败、安装失败或回连超时均进入现有节点任务错误/超时状态。
- bootstrap 输出的 `BKINSTALL_EVENT` 在 Ansible 返回前实时进入现有安装进度模型；终态 stdout 补偿不丢失失败事件，也不重复步骤。
- 执行结束后目标临时目录不存在会话 URL 文件和本次 bootstrap 文件。
- 新包校验失败不得停止旧服务；新服务启动失败必须恢复旧目录和旧服务。仅当无法确认失败的新服务已经停止时，允许安全降级为保留原目录备份并明确标记“需要人工恢复”，不得继续自动重试或强行覆盖在用目录。
- 下载和解压超过资源边界时快速失败，不修改现有安装。
- Linux 远程安装入口、认证和执行链路与 Windows 手动 GUI 安装行为保持不变；共享安装引擎统一执行下载和解压资源边界。

## Out Of Scope

- 自动开启或修改目标 Windows 的 WinRM、防火墙、证书及本地安全策略。
- Windows ARM64。
- 无 WinRM 环境下的 SMB/PsExec/DCOM fallback。
- Windows 远程卸载、升级和控制器日常操作链路改造。
