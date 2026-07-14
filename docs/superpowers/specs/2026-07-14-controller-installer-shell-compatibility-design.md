# 控制器安装 Shell 兼容性设计

## 背景

Linux 控制器自动安装当前把 bootstrap 命令包装为 `sh -lc "..."`。`-l` 会让目标机加载 `/etc/profile`，而 `/etc/profile` 通常继续加载 `/etc/profile.d/*.sh`。当这些脚本包含 Bash 专属语法时，`dash`、BusyBox `ash` 等 `sh` 实现会在 bootstrap 下载前退出。

当前动态 bootstrap 又通过 `curl ... | bash -s` 执行，因此外层使用 `sh`、内层固定使用 Bash，兼容性契约不一致；直接把外层改为 `bash -c` 仍无法支持仅提供 POSIX `sh` 的精简系统。

## 目标

- 自动安装不再启动登录 Shell，不读取目标机 `/etc/profile` 或 `/etc/profile.d/*`。
- 同时支持仅提供 `sh`、仅提供 Bash，以及两者都存在的 Linux 环境。
- 下载失败和脚本执行失败都必须返回非零状态，不能被 Shell 管道掩盖。
- 保留现有架构识别、root/免密 sudo 判断、安装事件、流式日志和并发控制行为。
- 所有插入 Shell 命令的动态值都经过 Shell 安全转义。

## 非目标

- 不增加 `wget` 等第二下载器；目标机仍需提供 `curl`。
- 不改变现有 TLS 策略、安装令牌协议、安装目录和安装器二进制格式。
- 不扩展到非 POSIX 风格的 SSH 登录 Shell（如 fish/csh）；支持范围为 `sh` 或 Bash 登录环境。
- 不重构控制器安装任务、NATS executor 或安装进度模型。

## 方案比较

### 方案 A：改为 `bash -c`

改动最少，也能避开登录 profile，但仍硬依赖 Bash，无法覆盖仅有 `sh` 的精简系统。

### 方案 B：POSIX bootstrap + Shell 探测（采用）

bootstrap 使用 POSIX 语法；运行时优先选择 `sh`，不存在时回退 Bash。先下载脚本到权限受限的临时文件，再交给选定的 Shell 执行。该方案同时避免登录 profile 和管道错误吞没，兼容性边界清晰。

### 方案 C：分别维护 Bash/sh 两套脚本

能够针对不同 Shell 优化，但会产生行为分叉和双份测试，超出最小修复范围。

## 详细设计

### 1. 远程命令不再使用登录 Shell

删除 Linux 自动安装任务中的 `sh -lc` 包装。命令仍由 SSH executor 发送给目标用户的非登录命令环境执行，不主动加载系统 profile。

生成的命令只使用 POSIX Shell 语法，并按以下顺序选择 bootstrap 运行器：

1. `command -v sh` 成功时使用 `sh`；
2. 否则 `command -v bash` 成功时使用 Bash；
3. 两者都不存在时输出明确错误并返回非零状态。

bootstrap 本身保持 POSIX 子集，因此被 Bash 执行时行为一致。

### 2. 先下载、再执行

不再使用 `curl ... | shell`。远程命令执行以下步骤：

1. 使用 `umask 077` 限制临时文件权限；
2. 通过 `mktemp` 创建 bootstrap 临时文件；
3. 注册退出和常见终止信号的清理动作；
4. 使用 `curl -fsSLk` 下载脚本，HTTP 或网络失败立即返回非零状态；
5. 用选定的 Shell 执行临时脚本；
6. 保留脚本退出码并清理临时文件。

这避免 POSIX `sh` 缺少 `pipefail` 时，下载端失败却被管道末端成功状态覆盖。

### 3. 动态 bootstrap 改为 POSIX

服务端 `linux_bootstrap` 返回的脚本调整为：

- shebang 使用 `#!/bin/sh`；
- `set -euo pipefail` 改为 `set -eu`；
- trap 使用 POSIX 信号编号/名称形式，不依赖 Bash 的 `EXIT` 语义；
- 其余架构识别、下载安装器和启动安装器逻辑保持不变。

仓库中的静态 `agents/sidecar-installer/bootstrap.sh` 已使用 `#!/bin/sh` 和 `set -eu`，动态脚本与其兼容性方向保持一致。

### 4. Shell 安全转义

bootstrap URL、安装目录、安装器文件名等动态值通过 Python `shlex.quote` 生成 Shell 字面量，不再依赖手写单双引号拼接。测试覆盖空格、单引号等边界字符。

## 错误处理

- 缺少 `sh` 和 Bash：输出 `controller installation requires sh or bash` 并失败。
- `mktemp` 失败：立即失败，不执行下载。
- `curl` 不存在、网络失败或 HTTP 非成功状态：立即失败，不执行下载内容。
- bootstrap 返回非零状态：原样向上传递退出码，继续由现有 executor 和安装任务记录失败。
- 无论成功或失败，外层 bootstrap 临时脚本都应清理。

## 测试设计

遵循 TDD，先补失败测试，再实现最小改动。

### 服务层命令生成测试

- 自动安装命令不包含 `sh -lc`、`bash -lc` 或其他登录 Shell 参数。
- 命令包含 `sh` 优先、Bash 回退和无可用 Shell 的明确错误。
- 命令使用临时文件下载，不包含 `curl | sh` 或 `curl | bash`。
- 安装路径和文件名含空格、单引号时仍能正确生成和解析。

### bootstrap 接口测试

- 返回脚本以 `#!/bin/sh` 开头。
- 脚本不包含 `pipefail` 或其他 Bash 专属语法。
- 脚本通过 `sh -n` 语法检查。
- 架构归一化、预期架构校验、下载 URL 和安装器启动参数保持现有行为。

### 行为测试

- PATH 中同时存在 sh/Bash 时优先使用 sh。
- PATH 中仅暴露 Bash 时能够执行 POSIX bootstrap。
- PATH 中仅暴露 sh 时能够执行 POSIX bootstrap。
- 下载失败时不执行 bootstrap，命令返回非零状态。
- bootstrap 执行失败时保留其非零退出码并清理临时文件。

## 验收标准

- 目标机存在不兼容的 `/etc/profile.d/date-format.sh` 时，自动安装不再读取该文件。
- 仅有 sh 或仅有 Bash 的受测环境均能进入 bootstrap。
- 所有新增专项测试通过。
- `server/apps/node_mgmt` 相关回归测试通过；若全量 `make test` 被既有环境问题阻断，需记录阻断证据并至少完成节点管理聚焦门禁。
