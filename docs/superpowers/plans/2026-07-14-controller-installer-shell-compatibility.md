# 控制器安装 Shell 兼容性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取消 Linux 控制器自动安装对登录 profile 和 Bash 的强依赖，使仅有 sh 或仅有 Bash 的目标机都能可靠执行 bootstrap。

**Architecture:** 所有运行时改动仅位于 `server/`。`InstallerService` 生成 POSIX 兼容的“探测 Shell→下载临时脚本→按权限执行→清理”命令；安装任务直接把该命令交给 SSH executor，不再包 `sh -lc`；动态 bootstrap 接口输出 POSIX sh 脚本。

**Tech Stack:** Python 3.12、Django 4.2、pytest、POSIX Shell、`shlex.quote`

## Global Constraints

- 不修改 `agents/sidecar-installer`、安装器二进制、NATS executor、安装事件和并发控制。
- 自动安装不得启动登录 Shell或读取 `/etc/profile.d/*`。
- 优先使用 sh，缺失时回退 Bash；两者都不存在时明确失败。
- 不使用 `curl | shell`；下载失败和 bootstrap 失败必须保留非零退出码。
- 动态 Shell 值必须通过 `shlex.quote` 转义。
- 新增行为先写失败测试，相关代码覆盖率不低于 75%。

---

## 文件结构

- Modify: `server/apps/node_mgmt/services/installer.py` — 生成 Shell 探测、临时下载、权限执行与清理命令。
- Modify: `server/apps/node_mgmt/tasks/installer.py` — 移除自动安装的登录 Shell 包装。
- Modify: `server/apps/node_mgmt/views/sidecar.py` — 输出 POSIX 动态 bootstrap，并安全转义动态值。
- Modify: `server/apps/node_mgmt/tests/test_b75_installer_service.py` — 命令结构、Shell 回退、下载错误与引用边界测试。
- Modify: `server/apps/node_mgmt/tests/test_architecture_support.py` — 自动安装下发命令与 bootstrap 接口回归测试。

### Task 1: 服务层生成兼容 bootstrap 命令

**Files:**
- Modify: `server/apps/node_mgmt/services/installer.py:1-10,344-369`
- Test: `server/apps/node_mgmt/tests/test_b75_installer_service.py:373-430`

**Interfaces:**
- Consumes: `InstallerSessionService.build_session_config(token) -> dict`
- Produces: `InstallerService.get_linux_bootstrap_command(token: str, install_mode: str) -> str`

- [ ] **Step 1: 写失败测试**

更新 manual/auto 断言，并新增引用边界测试：

```python
assert "sh -lc" not in cmd
assert "bash -lc" not in cmd
assert "command -v sh" in cmd
assert "command -v bash" in cmd
assert "curl -fsSLk" in cmd
assert " -o \"$bootstrap_file\"" in cmd
assert "| bash" not in cmd
assert "| sh" not in cmd
assert "sudo -n \"$bootstrap_shell\" \"$bootstrap_file\"" in auto_cmd
assert "sudo \"$bootstrap_shell\" \"$bootstrap_file\"" in manual_cmd
```

使用包含空格和单引号的 server URL，断言 `shlex.quote` 形式出现在命令中。

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
cd server && uv run pytest apps/node_mgmt/tests/test_b75_installer_service.py -k 'linux_bootstrap_command or get_install_command_linux' -q
```

Expected: FAIL，旧命令仍包含 `curl ... | bash`，且没有 Shell 回退和临时文件。

- [ ] **Step 3: 写最小实现**

在 `installer.py` 导入 `shlex`，让 `get_linux_bootstrap_command` 生成以下 POSIX 语义：

```python
quoted_url = shlex.quote(bootstrap_url)
shell_detection = (
    'if command -v sh >/dev/null 2>&1; then bootstrap_shell="$(command -v sh)"; '
    'elif command -v bash >/dev/null 2>&1; then bootstrap_shell="$(command -v bash)"; '
    "else echo 'Error: controller installation requires sh or bash' >&2; exit 1; fi"
)
download = (
    'umask 077; bootstrap_file="$(mktemp)" || exit 1; '
    'cleanup_bootstrap() { rm -f "$bootstrap_file"; }; '
    'trap cleanup_bootstrap 0 1 2 15; '
    f'curl -fsSLk {quoted_url} -o "$bootstrap_file" || exit 1'
)
```

root 分支直接执行 `"$bootstrap_shell" "$bootstrap_file"`；manual sudo 分支执行 `sudo "$bootstrap_shell" "$bootstrap_file"`；auto sudo 分支先验证 `sudo -n true`，再执行 `sudo -n "$bootstrap_shell" "$bootstrap_file"`。所有分支通过 `bootstrap_status` 保留退出码，最终 `exit "$bootstrap_status"` 触发清理。

- [ ] **Step 4: 运行聚焦测试确认绿灯**

Run: 同 Step 2。

Expected: PASS。

### Task 2: 动态 bootstrap 改为 POSIX sh

**Files:**
- Modify: `server/apps/node_mgmt/views/sidecar.py:1-5,584-631`
- Test: `server/apps/node_mgmt/tests/test_architecture_support.py:2837-2895`

**Interfaces:**
- Consumes: `InstallerSessionService.build_session_config(...)`
- Produces: `GET installer/linux_bootstrap` 的 POSIX Shell 响应

- [ ] **Step 1: 写失败测试**

在现有接口测试增加：

```python
assert content.startswith("#!/bin/sh\n")
assert "set -eu\n" in content
assert "pipefail" not in content
assert "trap cleanup 0 1 2 15" in content
```

把响应写入临时文件并执行：

```python
subprocess.run(["sh", "-n", script_path], check=True)
```

新增包含空格和单引号的 `install_dir`/`filename` fixture，断言变量赋值可被 `sh -n` 解析且值经 `shlex.quote` 保留。

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
cd server && uv run pytest apps/node_mgmt/tests/test_architecture_support.py -k 'open_api_linux_bootstrap' -q
```

Expected: FAIL，响应当前为 `#!/bin/bash` 且包含 `pipefail`。

- [ ] **Step 3: 写最小实现**

在 `sidecar.py` 导入 `shlex`；将脚本头改为：

```sh
#!/bin/sh
set -eu
```

使用 `shlex.quote` 生成 `INSTALL_DIR`、`INSTALLER_NAME`、`EXPECTED_ARCH` 的赋值。URL 拆为经过 quote 的固定前缀与 `"$DETECTED_ARCH"` 拼接，保留架构变量展开。trap 改为 `trap cleanup 0 1 2 15`，其余下载和安装器启动逻辑不变。

- [ ] **Step 4: 运行聚焦测试确认绿灯**

Run: 同 Step 2。

Expected: PASS，且 `sh -n` 返回 0。

### Task 3: 自动安装任务取消登录 Shell

**Files:**
- Modify: `server/apps/node_mgmt/tasks/installer.py:584-623`
- Test: `server/apps/node_mgmt/tests/test_architecture_support.py:1490-1550`

**Interfaces:**
- Consumes: `InstallerService.get_install_command(...) -> str`
- Produces: 传给 `exec_command_to_remote_stream` 的原始兼容命令

- [ ] **Step 1: 写失败测试**

让 `fake_exec_command_to_remote_stream` 捕获第五个位置参数，并断言：

```python
assert streamed_command == "echo install"
assert "sh -lc" not in streamed_command
```

该测试代表带有非 POSIX `date-format()` 的登录 profile 不会被安装任务主动加载。

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
cd server && uv run pytest apps/node_mgmt/tests/test_architecture_support.py::test_install_controller_on_nodes_detects_arch_and_resolves_package -q
```

Expected: FAIL，实际命令为 `sh -lc "echo install"`。

- [ ] **Step 3: 写最小实现**

删除：

```python
if resolved_package.os == NodeConstants.LINUX_OS:
    install_command = f'sh -lc "{install_command}"'
```

不改 SSH executor 参数和流式日志逻辑。

- [ ] **Step 4: 运行聚焦测试确认绿灯**

Run: 同 Step 2。

Expected: PASS。

### Task 4: 回归验证与收口

**Files:**
- Verify: 上述 5 个 server 文件

**Interfaces:**
- Consumes: Tasks 1-3 的完整实现
- Produces: 可交付的测试证据

- [ ] **Step 1: 运行节点管理聚焦回归**

```bash
cd server && uv run pytest \
  apps/node_mgmt/tests/test_b75_installer_service.py \
  apps/node_mgmt/tests/test_architecture_support.py \
  apps/node_mgmt/tests/test_installer_failure_enrichment.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行语法、格式和迁移检查**

```bash
cd server && uv run python manage.py makemigrations --check --dry-run
cd server && uv run black --check \
  apps/node_mgmt/services/installer.py \
  apps/node_mgmt/tasks/installer.py \
  apps/node_mgmt/views/sidecar.py \
  apps/node_mgmt/tests/test_b75_installer_service.py \
  apps/node_mgmt/tests/test_architecture_support.py
cd server && uv run isort --check-only \
  apps/node_mgmt/services/installer.py \
  apps/node_mgmt/tasks/installer.py \
  apps/node_mgmt/views/sidecar.py \
  apps/node_mgmt/tests/test_b75_installer_service.py \
  apps/node_mgmt/tests/test_architecture_support.py
```

Expected: 全部返回 0；若本地依赖缺失，记录完整阻断证据。

- [ ] **Step 3: 运行 Server 门禁**

```bash
cd server && make test
```

Expected: PASS；若被与本改动无关的既有收集错误阻断，保留错误证据并以 Step 1 的聚焦回归作为本次功能验证。

- [ ] **Step 4: 记录 projectmem 并提交实现**

```bash
git add server/apps/node_mgmt/services/installer.py \
  server/apps/node_mgmt/tasks/installer.py \
  server/apps/node_mgmt/views/sidecar.py \
  server/apps/node_mgmt/tests/test_b75_installer_service.py \
  server/apps/node_mgmt/tests/test_architecture_support.py \
  docs/superpowers/plans/2026-07-14-controller-installer-shell-compatibility.md
git commit -m "修复: 提升控制器安装 Shell 兼容性"
```
