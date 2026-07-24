# Windows Telegraf 连通性检测修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让监控接入连通性检测根据采集节点操作系统与架构执行正确的 Telegraf 单次采集，消除 Windows 假失败且保持 Linux 行为不变。

**Architecture:** `CollectDetectService` 从 NodeMgmt 查询节点，并复用 `PackageService.resolve_collector_by_architecture` 解析适用 Telegraf `Collector`。`collect_detect_runtime` 只负责根据操作系统、采集器路径、临时文件名和配置内容生成 `(command, shell)`；Linux 使用 sh，Windows 使用 PowerShell 和 Base64 UTF-8 配置写入。

**Tech Stack:** Python 3.12、Django 4.2 ORM、Celery、pytest、PowerShell、Telegraf

## Global Constraints

- 新功能/bugfix 必须先写测试，观察正确 RED 后才能修改生产代码。
- 仅修改监控连通性检测相关文件，不改变正式 Sidecar 采集链路、前端、数据模型或迁移。
- Telegraf 路径必须来自 NodeMgmt `Collector.executable_path`，不得在 Monitor 模块新增 Windows 路径常量。
- Windows 不得回退 Linux 命令；节点、操作系统或采集器无法解析时必须明确失败且不得调用执行器。
- 测试配置仅输出 stdout，不得写入 VictoriaMetrics；敏感值继续通过环境变量传递并脱敏。
- 禁止原生 SQL，仅使用 Django ORM。

---

### Task 1: 生成跨平台 Telegraf 单次检测命令

**Files:**
- Modify: `server/apps/monitor/services/collect_detect_runtime.py:1-59`
- Test: `server/apps/monitor/tests/test_collect_detect_service.py:1-185`

**Interfaces:**
- Consumes: `operating_system: str`、`executable_path: str`、`config_file_name: str`、`config_content: str`
- Produces: `build_telegraf_detect_execution(...) -> tuple[str, str]`，第二项严格为 `sh` 或 `powershell`

- [ ] **Step 1: 在运行时测试中声明期望 API 并覆盖 Windows 行为**

将测试导入改为 `build_telegraf_detect_execution`，用下列测试替换只验证 Linux 固定路径的 `test_build_telegraf_once_command_uses_temp_config_and_cleanup`，并补充 Windows 测试：

```python
def test_build_telegraf_detect_execution_keeps_linux_behavior():
    command, shell = build_telegraf_detect_execution(
        operating_system="linux",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        config_file_name="bklite-detect.toml",
        config_content="[[inputs.cpu]]\n",
    )

    assert shell == "sh"
    assert "/opt/fusion-collectors/bin/telegraf --once --config /tmp/bklite-detect.toml" in command
    assert "rm -f /tmp/bklite-detect.toml" in command


def test_build_telegraf_detect_execution_uses_powershell_on_windows():
    command, shell = build_telegraf_detect_execution(
        operating_system="windows",
        executable_path=r"C:\fusion-collectors\bin\telegraf.exe",
        config_file_name="bklite-detect.toml",
        config_content="[[inputs.win_perf_counters]]\n",
    )

    assert shell == "powershell"
    assert "$env:TEMP" in command
    assert r"C:\fusion-collectors\bin\telegraf.exe" in command
    assert "--once --config $configPath" in command
    assert "FromBase64String" in command
    assert "WriteAllBytes" in command
    assert "finally" in command
    assert "Remove-Item" in command
    assert "/tmp" not in command
    assert "trap" not in command
    assert "rm -f" not in command


def test_build_telegraf_detect_execution_rejects_unknown_operating_system():
    with pytest.raises(ValueError, match="不支持的节点操作系统: darwin"):
        build_telegraf_detect_execution(
            operating_system="darwin",
            executable_path="/opt/telegraf",
            config_file_name="bklite-detect.toml",
            config_content="[[inputs.cpu]]\n",
        )
```

- [ ] **Step 2: 运行两个测试并确认 RED 原因正确**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py \
  -k 'build_telegraf_detect_execution' -vv
```

Expected: FAIL/collection error，原因是 `build_telegraf_detect_execution` 尚不存在，而不是测试环境或数据库错误。

- [ ] **Step 3: 实现最小跨平台命令构造器**

在 `collect_detect_runtime.py` 中引入 `base64`，删除仅服务旧 Linux 固定入口的 `build_telegraf_once_command` 和 `build_write_config_and_telegraf_command`，新增：

```python
def _quote_powershell_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_telegraf_detect_execution(
    operating_system: str,
    executable_path: str,
    config_file_name: str,
    config_content: str,
) -> tuple[str, str]:
    if operating_system == "linux":
        config_path = f"/tmp/{config_file_name}"
        quoted_path = shlex.quote(config_path)
        quoted_telegraf = shlex.quote(executable_path)
        command = (
            "set -e\n"
            f"trap 'rm -f {quoted_path}' EXIT\n"
            f"cat > {quoted_path} <<'BK_LITE_TELEGRAF_PREFLIGHT_EOF'\n"
            f"{config_content}\n"
            "BK_LITE_TELEGRAF_PREFLIGHT_EOF\n"
            f"{quoted_telegraf} --once --config {quoted_path}"
        )
        return command, "sh"

    if operating_system == "windows":
        encoded_content = base64.b64encode(config_content.encode("utf-8")).decode("ascii")
        quoted_name = _quote_powershell_literal(config_file_name)
        quoted_telegraf = _quote_powershell_literal(executable_path)
        command = (
            "$ErrorActionPreference = 'Stop'\n"
            f"$configPath = Join-Path $env:TEMP {quoted_name}\n"
            "$telegrafExitCode = 1\n"
            "try {\n"
            f"  [IO.File]::WriteAllBytes($configPath, [Convert]::FromBase64String('{encoded_content}'))\n"
            f"  & {quoted_telegraf} --once --config $configPath\n"
            "  $telegrafExitCode = $LASTEXITCODE\n"
            "} finally {\n"
            "  Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue\n"
            "}\n"
            "exit $telegrafExitCode"
        )
        return command, "powershell"

    raise ValueError(f"不支持的节点操作系统: {operating_system}")
```

- [ ] **Step 4: 运行运行时测试并确认 GREEN**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py \
  -k 'build_telegraf_detect_execution or render_preflight or sanitize_execution_result' -vv
```

Expected: PASS；Windows 命令不含 Linux 路径或 Shell 语法，Linux 原行为仍通过。

- [ ] **Step 5: 提交运行时构造器**

```bash
git add server/apps/monitor/services/collect_detect_runtime.py \
  server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "fix: 生成跨平台 Telegraf 检测命令"
```

### Task 2: 根据节点解析并执行适用的 Telegraf

**Files:**
- Modify: `server/apps/monitor/services/collect_detect.py:7-124`
- Modify: `server/apps/monitor/tests/test_collect_detect_service.py:1-428`

**Interfaces:**
- Consumes: `Node.objects.filter(id=task.node_id)`、`PackageService.resolve_collector_by_architecture(os, "Telegraf", arch)`、Task 1 的 `build_telegraf_detect_execution`
- Produces: `CollectDetectService._resolve_telegraf_runtime(node_id) -> tuple[str, str]`，返回 `(operating_system, executable_path)`

- [ ] **Step 1: 增加真实 Node/Collector 测试数据 helper**

在测试文件中导入 `CloudRegion`、`Collector`、`Node`，新增：

```python
def create_collect_detect_node(
    *,
    node_id: str,
    operating_system: str,
    executable_path: str,
    create_collector: bool = True,
):
    cloud_region, _ = CloudRegion.objects.get_or_create(id=1, defaults={"name": "collect-detect-test"})
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip="127.0.0.1",
        operating_system=operating_system,
        cpu_architecture="x86_64",
        collector_configuration_directory=(
            r"C:\fusion-collectors\etc\telegraf.d"
            if operating_system == "windows"
            else "/etc/telegraf/telegraf.d"
        ),
        cloud_region=cloud_region,
    )
    if create_collector:
        Collector.objects.create(
            id=f"telegraf-{operating_system}-collect-detect",
            name="Telegraf",
            service_type="exec",
            node_operating_system=operating_system,
            cpu_architecture="x86_64",
            executable_path=executable_path,
            execute_parameters="--config %s",
        )
    return node


def create_collect_detect_case(*, node_id: str, collect_type: str = "cpu"):
    plugin = MonitorPlugin.objects.create(
        name=f"{collect_type}-{node_id}",
        collector="Telegraf",
        collect_type=collect_type,
        support_collect_detect=True,
    )
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type=collect_type,
        config_type=collect_type,
        file_type="toml",
        content=f"[[inputs.{collect_type}]]\n",
    )
    return CollectDetectTask.objects.create(
        status="pending",
        phase="validate",
        monitor_plugin_id=plugin.id,
        monitor_object_id=1,
        collector="Telegraf",
        collect_type=collect_type,
        node_id=node_id,
        request_fingerprint=f"fp-{node_id}",
        created_by="admin",
        organization=3,
    )
```

在现有三个 `run_task` 正向测试中分别先创建 Linux 节点和 Linux Telegraf，以适配节点解析后的真实前置条件。

- [ ] **Step 2: 新增 Windows 执行与缺失采集器测试**

复用现有插件、模板、任务与 `FakeExecutor` 结构，新增核心断言：

```python
@pytest.mark.django_db
def test_run_collect_detect_task_uses_windows_collector_and_powershell(monkeypatch):
    create_collect_detect_node(
        node_id="node-win",
        operating_system="windows",
        executable_path=r"C:\fusion-collectors\bin\telegraf.exe",
    )
    task = create_collect_detect_case(node_id="node-win")
    executed = {}

    class FakeExecutor:
        def __init__(self, node_id):
            executed["node_id"] = node_id

        def execute_local(self, command, timeout=60, shell=None, env=None):
            executed.update(command=command, shell=shell, env=env)
            return {"success": True, "result": "win_cpu value=1", "error": ""}

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)
    result = CollectDetectService.run_task(task.id, {"instance": {}, "env": {}, "timeout": 30})

    assert result["success"] is True
    assert executed["node_id"] == "node-win"
    assert executed["shell"] == "powershell"
    assert r"C:\fusion-collectors\bin\telegraf.exe" in executed["command"]
    assert "/opt/fusion-collectors/bin/telegraf" not in executed["command"]


@pytest.mark.django_db
def test_run_collect_detect_task_fails_when_windows_collector_is_missing(monkeypatch):
    create_collect_detect_node(
        node_id="node-win-missing",
        operating_system="windows",
        executable_path=r"C:\fusion-collectors\bin\telegraf.exe",
        create_collector=False,
    )
    task = create_collect_detect_case(node_id="node-win-missing")
    executor_called = False

    class FakeExecutor:
        def __init__(self, node_id):
            nonlocal executor_called
            executor_called = True

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)
    result = CollectDetectService.run_task(task.id, {"instance": {}, "env": {}})

    assert result["success"] is False
    assert "未找到适用的 Telegraf 采集器" in result["stderr"]
    assert executor_called is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("node_id", "operating_system", "expected_error"),
    [
        ("node-missing", None, "采集节点不存在"),
        ("node-unsupported", "darwin", "不支持的节点操作系统: darwin"),
    ],
)
def test_run_collect_detect_task_rejects_missing_or_unsupported_node(
    monkeypatch,
    node_id,
    operating_system,
    expected_error,
):
    if operating_system:
        create_collect_detect_node(
            node_id=node_id,
            operating_system=operating_system,
            executable_path="/opt/telegraf",
            create_collector=False,
        )
    task = create_collect_detect_case(node_id=node_id)
    executor_called = False

    class FakeExecutor:
        def __init__(self, executor_node_id):
            nonlocal executor_called
            executor_called = True

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)
    result = CollectDetectService.run_task(task.id, {"instance": {}, "env": {}})

    assert result["success"] is False
    assert expected_error in result["stderr"]
    assert executor_called is False
```

- [ ] **Step 3: 运行新增服务测试并确认 RED 原因正确**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py \
  -k 'windows_collector or missing_or_unsupported_node or executes_telegraf_once' -vv
```

Expected: Windows 测试 FAIL，因为当前服务不查询 Node/Collector 且仍固定 `shell="sh"`；Linux 正向测试在补 fixture 后继续揭示尚未接入新运行时 API。不得接受因测试数据缺字段导致的 ERROR。

- [ ] **Step 4: 实现节点与采集器解析并接入跨平台构造器**

在 `collect_detect.py` 中导入 `NodeConstants`、`Node`、`PackageService` 和 Task 1 的构造器，实现：

```python
@staticmethod
def _resolve_telegraf_runtime(node_id):
    node = Node.objects.filter(id=node_id).first()
    if not node:
        raise ValueError("采集节点不存在")
    if node.operating_system not in {NodeConstants.LINUX_OS, NodeConstants.WINDOWS_OS}:
        raise ValueError(f"不支持的节点操作系统: {node.operating_system}")

    collector = PackageService.resolve_collector_by_architecture(
        node.operating_system,
        "Telegraf",
        node.cpu_architecture,
    )
    if not collector:
        raise ValueError("未找到适用的 Telegraf 采集器")
    return node.operating_system, collector.executable_path
```

在 `run_task` 中用以下数据流替换固定路径与固定 Shell：

```python
operating_system, executable_path = cls._resolve_telegraf_runtime(task.node_id)
config_file_name = f"bklite-telegraf-detect-{task.id}-{uuid.uuid4().hex}.toml"
command, shell = build_telegraf_detect_execution(
    operating_system=operating_system,
    executable_path=executable_path,
    config_file_name=config_file_name,
    config_content=config_content,
)
raw_result = Executor(task.node_id).execute_local(
    command,
    timeout=int(runtime_payload.get("timeout") or 60),
    shell=shell,
    env=env,
)
```

- [ ] **Step 5: 运行完整专项测试并确认 GREEN**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py -vv
```

Expected: 全部 PASS；Windows 使用 PowerShell，Linux 使用 sh，缺失采集器不调用执行器。

- [ ] **Step 6: 提交节点感知执行修复**

```bash
git add server/apps/monitor/services/collect_detect.py \
  server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "fix: 按节点系统执行 Telegraf 连通性检测"
```

### Task 3: 回归、格式与问题收口

**Files:**
- Verify: `server/apps/monitor/services/collect_detect.py`
- Verify: `server/apps/monitor/services/collect_detect_runtime.py`
- Verify: `server/apps/monitor/tests/test_collect_detect_service.py`

**Interfaces:**
- Consumes: Task 1、Task 2 的最终实现
- Produces: 可复核的测试、格式、静态检查结果和 projectmem #0114 收口记录

- [ ] **Step 1: 运行专项测试及 Django 检查**

```bash
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py -q
cd server && uv run python manage.py check
```

Expected: 专项测试全部 PASS；Django system check 返回 0 且无新增错误。

- [ ] **Step 2: 仅检查触及文件的格式与静态问题**

```bash
cd server && uvx --from black==23.1.0 black --check \
  apps/monitor/services/collect_detect.py \
  apps/monitor/services/collect_detect_runtime.py \
  apps/monitor/tests/test_collect_detect_service.py
cd server && uvx --from flake8==7.1.1 flake8 \
  apps/monitor/services/collect_detect.py \
  apps/monitor/services/collect_detect_runtime.py \
  apps/monitor/tests/test_collect_detect_service.py
```

Expected: Black 返回 `3 files would be left unchanged`；flake8 返回 0。若测试文件存在与本次无关的既有告警，必须确认其不在本次新增行并如实记录，禁止扩大格式化范围。

- [ ] **Step 3: 检查差异与变更行覆盖率**

```bash
git diff --check
cd server && uv run pytest apps/monitor/tests/test_collect_detect_service.py \
  --cov=apps.monitor.services.collect_detect \
  --cov=apps.monitor.services.collect_detect_runtime \
  --cov-report=term-missing
```

Expected: `git diff --check` 返回 0；两个触及服务文件合计覆盖率不低于 75%，Windows/Linux/错误分支均被执行。

- [ ] **Step 4: 记录验证并关闭 projectmem 问题**

先调用 `record_attempt(summary, outcome="worked", issue_id="0114")`，写明专项测试、Django check、格式和静态检查结果；仅在所有验证通过后调用 `record_fix(summary, issue_id="0114")` 关闭问题。

- [ ] **Step 5: 提交验证性调整（仅当 Step 1-3 产生必要变更）**

```bash
git add server/apps/monitor/services/collect_detect.py \
  server/apps/monitor/services/collect_detect_runtime.py \
  server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "test: 验证 Windows 连通性检测兼容性"
```

若没有文件变化则不创建空提交。
