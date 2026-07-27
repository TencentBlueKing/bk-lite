# Windows 控制器远程安装发布 Runbook

本文面向负责 BK-Lite 构建、镜像发布和环境初始化的运维同学，说明 Windows 控制器远程安装上线后，发布流水线必须增加的产物、镜像、迁移和初始化步骤。

## 1. 发布变更摘要

本功能新增一个独立发布产物：

| 用途 | 产物 | 发布位置 |
|---|---|---|
| Windows 手动安装 | `bklite-controller-installer.exe` | `installer/windows/x86_64/bklite-controller-installer.exe` |
| **Windows 远程安装** | **`bklite-controller-bootstrap.exe`** | **`installer/windows/x86_64/bklite-controller-bootstrap.exe`** |
| Linux 安装 | `bklite-controller-installer` | `installer/linux/<arch>/bklite-controller-installer` |

`bklite-controller-bootstrap.exe` 是无 GUI 的原生安装程序。NodeMgmt 通过云区域内的 Ansible Executor 将它临时分发到目标 Windows 主机，bootstrap 再获取安装会话、下载控制器包并完成事务安装。它不是 Ansible Executor 镜像中的文件，也不能用 Windows GUI 安装器替代。

## 2. 流水线必须改造的内容

发布流水线必须完成以下三项，缺少任意一项都不能开放 Windows 远程安装：

1. 安装器构建任务新增 `bklite-controller-bootstrap.exe` 的归档和对象存储初始化。
2. 重新构建并发布 Ansible Executor 镜像，使镜像包含固定版本的 WinRM 依赖。
3. Server 发布时执行 NodeMgmt 数据库迁移。
4. 安装器专用 NATS 用户允许读取安装包对象，并允许发布 `installer.progress.>`；Server 用户保持对该 subject 的订阅权限。

建议顺序：构建全部产物和镜像 → 上传 bootstrap → 先滚动发布并验证各云区域 Ansible Executor → 执行数据库迁移 → 发布 Server/Web → 执行验收。新版 Executor 与 bootstrap 先上线可兼容旧 Server；反向顺序会在滚动窗口内触发模块或参数不匹配。

bootstrap 初始化和 Ansible Executor 可用性都是运行期依赖，不应放进 Server 容器启动阶段等待或重试；初始化失败时应终止发布流水线并保留原始错误。

## 3. 构建并归档新增产物

在仓库的 `agents/sidecar-installer` 目录执行：

```bash
make release-artifacts
```

流水线需要归档并发布以下 Windows x86_64 文件：

```text
dist/windows/x86_64/bklite-controller-installer.exe
dist/windows/x86_64/bklite-controller-bootstrap.exe
```

新增产物的预期路径必须是：

```text
agents/sidecar-installer/dist/windows/x86_64/bklite-controller-bootstrap.exe
```

不要归档或发布内部中间文件 `setup-worker.exe`。建议流水线记录 bootstrap 的文件大小和 SHA-256，并确保文件非空；生成的二进制文件不提交到 Git。

`make release-artifacts` 是两个 Windows 产物的原子构建入口；`nsis` 目标会显式先生成图标和原生 worker，流水线不要从历史工作区直接调用 `makensis setup.nsi`，以免把过期 worker 嵌入 GUI 安装器。

当前只支持 Windows x86_64，不要生成或上传 Windows ARM64 bootstrap。

## 4. 初始化对象存储

在具备正式环境配置和对象存储访问权限的 Server 运行环境中执行：

```bash
python manage.py installer_init \
  --os windows \
  --cpu_architecture x86_64 \
  --variant bootstrap \
  --file_path /path/to/dist/windows/x86_64/bklite-controller-bootstrap.exe
```

命令会覆盖 latest 对象：

```text
installer/windows/x86_64/bklite-controller-bootstrap.exe
```

流水线必须将命令失败视为发布失败，不得忽略退出码。上传完成后应校验对象存在、大小非零，并将本次构建记录的 SHA-256 与下载对象进行比对；至少要保留上一版本 bootstrap，以便回滚时重新上传。

该初始化与原 Windows GUI 安装器初始化是两个独立命令，不能互相替代：

```bash
# 原有手动安装器
python manage.py installer_init \
  --os windows \
  --cpu_architecture x86_64 \
  --file_path /path/to/dist/windows/x86_64/bklite-controller-installer.exe

# 新增远程安装 bootstrap
python manage.py installer_init \
  --os windows \
  --cpu_architecture x86_64 \
  --variant bootstrap \
  --file_path /path/to/dist/windows/x86_64/bklite-controller-bootstrap.exe
```

## 5. 构建并发布 Ansible Executor 镜像

在 `agents/ansible-executor` 目录构建镜像：

```bash
make build
```

流水线可按现有镜像仓库和版本规范替换镜像名称及 tag。新镜像必须包含：

- `ansible-core==2.18.6`
- `ansible.windows==3.7.0`
- `pywinrm==0.5.0`
- `cryptography==46.0.5`

不要继续复用旧 Ansible Executor 镜像。旧镜像可能缺少 WinRM collection、Windows 文件分发能力或执行载荷加密依赖。

建议为所有需要 Windows 远程安装的云区域滚动更新 Ansible Executor。更新完成后，NodeMgmt 必须能找到至少一个状态正常、collector ID 为 `ansibleexecutor_linux` 的 Executor。

### 执行载荷加密密钥

推荐通过密文环境变量为同一 Executor 部署单元注入稳定密钥：

```text
ANSIBLE_PAYLOAD_ENCRYPTION_KEY=<由密钥管理系统注入的随机密钥>
```

同一任务可能被不同副本接管时，各副本必须使用相同密钥。未显式配置时程序会兼容性回退到 NATS 密码派生密钥，但不建议将此作为长期生产配置。轮换密钥前应确保没有排队或执行中的 Ansible 任务，否则旧的未完成任务载荷将无法解密。

## 6. Server 数据库迁移

本次新增迁移：

```text
server/apps/node_mgmt/migrations/0037_controllertasknode_winrm_fields.py
server/apps/node_mgmt/migrations/0039_merge_cloudregion_and_winrm.py
```

按现有发布流程执行：

```bash
python manage.py migrate --no-input
```

迁移仅增加 WinRM 配置字段并合并迁移分支，不删除已有字段。不要只发布 Server 代码而跳过迁移，否则创建或执行控制器安装任务时会发生数据库字段错误。

## 7. 目标环境前置条件

目标 Windows 主机必须满足：

- Windows 10 或 Windows Server 2016 及以上版本。
- PowerShell 5.1 或更高版本。
- 已配置 HTTPS WinRM listener，端口固定为 5986。
- 使用 NTLM 认证。
- WinRM 服务端证书可被 Ansible Executor 所在环境信任。
- 云区域 `NODE_SERVER_URL` 必须使用受信任证书的 `https://` 地址；Windows 远程 bootstrap 会拒绝 HTTP、HTTPS 降级重定向以及会话返回的非 HTTPS Server URL。
- 防火墙和网络策略允许云区域 Ansible Executor 访问目标主机 TCP/5986。
- 使用具备安装 Windows 服务和写入 `C:\fusion-collectors` 权限的管理员账号。

当前稳定支持面不包括 HTTP/5985、Basic、Kerberos、CredSSP、跳过证书校验和 Windows ARM64。流水线或环境模板不要暴露这些组合。

### NATS 最小权限

安装会话返回的 `NATS_INSTALLER_USERNAME/PASSWORD` 除 Object Store 下载权限外，还需要：

```text
publish: installer.progress.>
```

Server 使用的 NATS 账号需要：

```text
subscribe: installer.progress.>
```

Windows 远程安装还要求云区域配置 `NATS_PROTOCOL=tls`，并使用受信任的 NATS
服务端证书。该模式不会回退到 `NATS_ADMIN_USERNAME/PASSWORD`，也不会接受
`nats://` 明文地址；未满足时任务会在下载控制器包前快速失败。Windows GUI
手动安装仍沿用既有兼容策略。

bootstrap 只接受 `installer.progress.<32 位小写十六进制 execution_id>`，实时发布失败会自动降级为 Ansible 终态 stdout 回放，不会让安装失败；但页面将无法实时显示下载和解压过程。生产验收必须覆盖实时进度，不能只验证最终成功。

## 8. 发布验收清单

发布完成后逐项确认：

- [ ] 构建日志中同时存在 Windows GUI installer 和 Windows remote bootstrap。
- [ ] 对象存储存在 `installer/windows/x86_64/bklite-controller-bootstrap.exe`，大小和 SHA-256 与本次构建一致。
- [ ] Ansible Executor 镜像为本次构建版本，并包含固定版本的 `ansible.windows`、`pywinrm` 和 `cryptography`。
- [ ] 所需云区域至少有一个健康的 Ansible Executor。
- [ ] 所需云区域已配置 `NATS_PROTOCOL=tls`、可信 NATS 证书和专用 `NATS_INSTALLER_USERNAME/PASSWORD`。
- [ ] NodeMgmt 的 `0037`、`0038`、`0039` 迁移均已应用。
- [ ] Windows 控制器安装页面显示远程安装，账号默认值为 Administrator；页面不暴露固定安全参数，并实际使用 5986、HTTPS、NTLM 和证书校验。
- [ ] 安装执行期间，页面能在 Ansible 任务结束前持续看到下载、解压和服务切换进度，最终回放不产生重复步骤。
- [ ] 使用测试 Windows 主机完成一次全新远程安装。
- [ ] 对已安装主机执行一次升级，确认 `cache`、`logs`、`generated` 被保留。
- [ ] 使用不受信任证书测试一次，确认连接被拒绝。
- [ ] 模拟新服务注册失败，确认旧安装和旧服务恢复。
- [ ] 确认目标机 `C:\Windows\Temp` 中本次 bootstrap 和 session 临时文件已清理。
- [ ] 原 Linux 远程安装和 Windows 手动安装各完成一次冒烟验证。

## 9. 常见失败与定位

| 现象 | 优先检查 |
|---|---|
| 文件分发阶段提示对象不存在 | bootstrap 是否执行了 `installer_init --variant bootstrap`，对象路径和架构是否正确 |
| 找不到健康 Executor | 目标云区域是否部署并上报了新版 Ansible Executor |
| WinRM 连接失败 | TCP/5986、防火墙、HTTPS listener、NTLM、账号权限 |
| 证书校验失败 | 服务端证书链、名称匹配和 Executor 容器 CA 信任 |
| 提示 PowerShell 或 Windows 版本不支持 | 目标机是否满足 Windows 10/Server 2016、PowerShell 5.1+ |
| Executor 启动时提示载荷加密密钥缺失 | 检查 `ANSIBLE_PAYLOAD_ENCRYPTION_KEY` 或 NATS 密码注入 |
| 安装最终成功但页面中途没有实时进度 | 检查安装器 NATS 用户对 `installer.progress.>` 的 publish 权限，以及 Server 用户的 subscribe 权限 |
| Server 报 WinRM 字段不存在 | 检查 NodeMgmt 数据库迁移是否完成 |

## 10. 回滚

应用回滚时：

1. 回滚 Server/Web 和 Ansible Executor 镜像到上一发布版本。
2. 如需恢复对象，使用上一版本 `bklite-controller-bootstrap.exe` 再次执行 `installer_init --variant bootstrap`。
3. 新增数据库字段为向后兼容的增量字段，应用回滚时通常不需要反向迁移；避免在紧急回滚中删除字段。
4. 已上传但未被旧版本引用的 bootstrap 对象可以保留，不影响 Linux 安装或 Windows 手动安装。

单台 Windows 主机安装失败时，bootstrap 会在新服务无法注册时恢复旧安装目录和旧服务。若 Windows 服务管理器连续拒绝停止失败的新服务，任务会以 `manual_recovery_required` 失败并保留 `.bklite-backup`；此状态不可直接自动重试，应先保留现场、人工停止服务并核对旧备份完整性，再恢复或重试。强行替换仍被进程占用的目录不属于安全回滚。
新服务已成功启动但旧备份清理失败时，安装仍按成功处理，并尝试将旧备份改名为 `.bklite-backup-retained-<时间戳>`；运维可在确认新服务稳定后清理该保留目录。
安装目录旁的空文件 `C:\fusion-collectors.bklite-install.lock` 是跨进程安装锁载体，文件存在不表示任务仍在运行；是否占用由操作系统文件锁决定，不要在安装执行期间手工删除。
`C:\fusion-collectors.bklite-install.fence` 以临时文件落盘并原子替换，保存最近一次远程安装的任务节点与 attempt。bootstrap 在任何备份清理/恢复前，以及正常激活或中断恢复的停止服务前后，都会通过 HTTPS 向 Server 重新校验当前租约；停止后的校验失败会重启操作前服务且不切换目录。fence 与本地截止时间是附加防线。该文件不是临时文件，正常运维和重试时不得删除。仅在确认 Server 数据库已回退且当前没有安装任务后，才可按人工恢复流程一并核对。
