# Historical Superpowers change: 2026-07-01-telegraf-preflight-collect-detect

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-01-telegraf-preflight-collect-detect.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pre-onboarding Telegraf collection detection workflow that runs `telegraf --once` on the selected target node through NATS Executor without creating formal monitor instances or sending metrics to the production pipeline.

**Architecture:** Add an explicit plugin capability flag, a short-lived monitor-side detection task model, a renderer that reuses existing monitor plugin templates but swaps outputs to local stdout, and an executor runtime request that can safely create temporary files and inject process environment variables. The web auto-onboarding table creates and polls detection tasks per row, discarding stale results by fingerprint.

**Tech Stack:** Django 4.2, DRF, Celery, Django ORM, Python `toml`, Go NATS Executor, Next.js 16, React 19, TypeScript, Ant Design.

---

## File Structure

- Modify `server/apps/monitor/models/plugin.py`: add `MonitorPlugin.support_collect_detect`.
- Create `server/apps/monitor/models/collect_detect.py`: store async detection task state and sanitized execution result.
- Modify `server/apps/monitor/models/__init__.py`: export the new model.
- Create `server/apps/monitor/migrations/0038_collect_detect.py`: add model and plugin capability field.
- Modify `server/apps/monitor/serializers/plugin.py`: expose `support_collect_detect` as read-only for built-in capability display.
- Create `server/apps/monitor/constants/collect_detect.py`: define statuses, phases, limits, and supported output fields.
- Create `server/apps/monitor/services/collect_detect/runtime.py`: render temporary Telegraf config, replace outputs, build env, redact output, parse metrics.
- Create `server/apps/monitor/services/collect_detect/service.py`: validate request, create tasks, dispatch Celery, serialize results.
- Create `server/apps/monitor/tasks/collect_detect.py`: execute detection tasks asynchronously.
- Modify `server/apps/monitor/views/node_mgmt.py`: add `collect_detect`, `collect_detect_result`, and `collect_detect_batch_status` actions.
- Modify `server/apps/rpc/executor.py`: add a method for local execution with env and temporary files.
- Modify `agents/nats-executor/local/entity.go`: expose JSON fields for env, temporary files, stdout/stderr, exit code, and duration.
- Modify `agents/nats-executor/local/executor.go`: create temporary files, inject env into the child process, capture structured output, and clean up.
- Modify `web/src/app/monitor/api/integration.ts`: add detect APIs.
- Modify `web/src/app/monitor/types/integration.ts`: add detect request/result row state types.
- Modify `web/src/app/monitor/(pages)/integration/list/detail/configure/automatic.tsx`: add row detection buttons, polling, status column, and stale fingerprint handling.
- Modify `web/src/app/monitor/locales/zh.json` and `web/src/app/monitor/locales/en.json`: add UI labels.
- Test files:
  - `server/apps/monitor/tests/test_collect_detect_service.py`
  - `server/apps/monitor/tests/test_collect_detect_api.py`
  - `agents/nats-executor/local/executor_runtime_test.go`
  - `web/scripts/monitor-collect-detect-logic-test.ts`

---

### Task 1: Add Capability And Detection Task Models

**Files:**
- Modify: `server/apps/monitor/models/plugin.py`
- Create: `server/apps/monitor/models/collect_detect.py`
- Modify: `server/apps/monitor/models/__init__.py`
- Create: `server/apps/monitor/migrations/0038_collect_detect.py`
- Modify: `server/apps/monitor/serializers/plugin.py`
- Test: `server/apps/monitor/tests/test_collect_detect_service.py`

- [ ] **Step 1: Write failing model and serializer tests**

Add these tests to `server/apps/monitor/tests/test_collect_detect_service.py`:

```python
import pytest

from apps.monitor.models import CollectDetectTask, MonitorObject, MonitorPlugin
from apps.monitor.serializers.plugin import MonitorPluginSerializer


@pytest.mark.django_db
def test_monitor_plugin_defaults_collect_detect_disabled():
    monitor_object = MonitorObject.objects.create(name="Host", type_id=1)
    plugin = MonitorPlugin.objects.create(
        name="Host(Telegraf)",
        collector="Telegraf",
        collect_type="host",
    )
    plugin.monitor_object.add(monitor_object)

    assert plugin.support_collect_detect is False


@pytest.mark.django_db
def test_monitor_plugin_serializer_exposes_collect_detect_capability():
    plugin = MonitorPlugin.objects.create(
        name="Ping(Telegraf)",
        collector="Telegraf",
        collect_type="ping",
        support_collect_detect=True,
    )

    data = MonitorPluginSerializer(plugin).data

    assert data["support_collect_detect"] is True


@pytest.mark.django_db
def test_collect_detect_task_stores_sanitized_execution_message():
    task = CollectDetectTask.objects.create(
        status="failed",
        phase="execute_once",
        monitor_plugin_id=1,
        monitor_object_id=2,
        collector="Telegraf",
        collect_type="snmp",
        node_id="node-1",
        instance_key="row-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
        result={
            "summary": "SNMP authentication failed",
            "stdout": "",
            "stderr": "authentication failed",
            "exit_code": 1,
            "duration_ms": 352,
        },
    )

    task.refresh_from_db()

    assert task.status == "failed"
    assert task.phase == "execute_once"
    assert task.result["stderr"] == "authentication failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py -v
```

Expected: fail because `CollectDetectTask` and `support_collect_detect` do not exist.

- [ ] **Step 3: Add models and migration**

Add to `server/apps/monitor/models/plugin.py` inside `MonitorPlugin`:

```python
support_collect_detect = models.BooleanField(default=False, verbose_name="是否支持接入前采集检测")
```

Create `server/apps/monitor/models/collect_detect.py`:

```python
from django.db import models

from apps.core.models.time_info import TimeInfo


class CollectDetectTask(TimeInfo):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    )

    PHASE_CHOICES = (
        ("validate", "Validate"),
        ("render_config", "Render Config"),
        ("prepare_runtime", "Prepare Runtime"),
        ("execute_once", "Execute Once"),
        ("parse_output", "Parse Output"),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="检测状态")
    phase = models.CharField(max_length=40, choices=PHASE_CHOICES, default="validate", verbose_name="检测阶段")
    monitor_plugin_id = models.IntegerField(verbose_name="监控插件ID")
    monitor_object_id = models.IntegerField(verbose_name="监控对象ID")
    collector = models.CharField(max_length=100, verbose_name="采集器")
    collect_type = models.CharField(max_length=50, verbose_name="采集类型")
    node_id = models.CharField(max_length=100, verbose_name="节点ID")
    instance_key = models.CharField(max_length=100, blank=True, default="", verbose_name="实例行标识")
    request_fingerprint = models.CharField(max_length=64, verbose_name="请求指纹")
    created_by = models.CharField(max_length=150, verbose_name="发起人")
    organization = models.IntegerField(verbose_name="组织ID")
    request_snapshot = models.JSONField(default=dict, verbose_name="脱敏请求快照")
    result = models.JSONField(default=dict, verbose_name="检测结果")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        verbose_name = "采集检测任务"
        verbose_name_plural = "采集检测任务"
        indexes = [
            models.Index(fields=["created_by", "organization", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["request_fingerprint"]),
        ]
```

Modify `server/apps/monitor/models/__init__.py`:

```python
from apps.monitor.models.collect_detect import *
```

Create `server/apps/monitor/migrations/0038_collect_detect.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0037_monitoralert_notice_logs"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorplugin",
            name="support_collect_detect",
            field=models.BooleanField(default=False, verbose_name="是否支持接入前采集检测"),
        ),
        migrations.CreateModel(
            name="CollectDetectTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("success", "Success"), ("failed", "Failed")], default="pending", max_length=20, verbose_name="检测状态")),
                ("phase", models.CharField(choices=[("validate", "Validate"), ("render_config", "Render Config"), ("prepare_runtime", "Prepare Runtime"), ("execute_once", "Execute Once"), ("parse_output", "Parse Output")], default="validate", max_length=40, verbose_name="检测阶段")),
                ("monitor_plugin_id", models.IntegerField(verbose_name="监控插件ID")),
                ("monitor_object_id", models.IntegerField(verbose_name="监控对象ID")),
                ("collector", models.CharField(max_length=100, verbose_name="采集器")),
                ("collect_type", models.CharField(max_length=50, verbose_name="采集类型")),
                ("node_id", models.CharField(max_length=100, verbose_name="节点ID")),
                ("instance_key", models.CharField(blank=True, default="", max_length=100, verbose_name="实例行标识")),
                ("request_fingerprint", models.CharField(max_length=64, verbose_name="请求指纹")),
                ("created_by", models.CharField(max_length=150, verbose_name="发起人")),
                ("organization", models.IntegerField(verbose_name="组织ID")),
                ("request_snapshot", models.JSONField(default=dict, verbose_name="脱敏请求快照")),
                ("result", models.JSONField(default=dict, verbose_name="检测结果")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
            ],
            options={
                "verbose_name": "采集检测任务",
                "verbose_name_plural": "采集检测任务",
            },
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(fields=["created_by", "organization", "created_at"], name="monitor_col_created_9fb2bd_idx"),
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(fields=["status", "created_at"], name="monitor_col_status_f81402_idx"),
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(fields=["request_fingerprint"], name="monitor_col_request_37ac79_idx"),
        ),
    ]
```

Modify `server/apps/monitor/serializers/plugin.py`:

```python
support_collect_detect = serializers.BooleanField(read_only=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_monitor_plugin_defaults_collect_detect_disabled apps/monitor/tests/test_collect_detect_service.py::test_monitor_plugin_serializer_exposes_collect_detect_capability apps/monitor/tests/test_collect_detect_service.py::test_collect_detect_task_stores_sanitized_execution_message -v
```

Expected: all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/apps/monitor/models/plugin.py server/apps/monitor/models/collect_detect.py server/apps/monitor/models/__init__.py server/apps/monitor/migrations/0038_collect_detect.py server/apps/monitor/serializers/plugin.py server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "feat(monitor): add collect detect task model"
```

---

### Task 2: Extend NATS Executor Runtime Execution

**Files:**
- Modify: `agents/nats-executor/local/entity.go`
- Modify: `agents/nats-executor/local/executor.go`
- Test: `agents/nats-executor/local/executor_runtime_test.go`

- [ ] **Step 1: Write failing Go tests**

Create `agents/nats-executor/local/executor_runtime_test.go`:

```go
package local

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestExecuteInjectsEnvironmentFromJSONRequest(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell env syntax differs on Windows")
	}

	response := Execute(ExecuteRequest{
		Command:        "printf \"$BKLITE_DETECT_SECRET\"",
		ExecuteTimeout: 5,
		Shell:          "sh",
		Env: map[string]string{
			"BKLITE_DETECT_SECRET": "secret-value",
		},
	}, "instance-env")

	if !response.Success {
		t.Fatalf("expected success, got: %+v", response)
	}
	if response.Stdout != "secret-value" {
		t.Fatalf("expected env value in stdout, got: %+v", response)
	}
}

func TestExecuteCreatesAndCleansTemporaryFiles(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell path syntax differs on Windows")
	}

	tempDir := t.TempDir()
	tempPath := filepath.Join(tempDir, "detect.conf")
	response := Execute(ExecuteRequest{
		Command:        "cat " + tempPath,
		ExecuteTimeout: 5,
		Shell:          "sh",
		TempFiles: []TempFile{
			{
				Path:    tempPath,
				Content: "config-content",
				Mode:    0600,
			},
		},
	}, "instance-temp")

	if !response.Success {
		t.Fatalf("expected success, got: %+v", response)
	}
	if response.Stdout != "config-content" {
		t.Fatalf("unexpected stdout: %+v", response)
	}
	if _, err := os.Stat(tempPath); !os.IsNotExist(err) {
		t.Fatalf("expected temp file cleanup, stat err=%v", err)
	}
}

func TestExecuteReturnsStructuredStderrAndExitCode(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell stderr syntax differs on Windows")
	}

	response := Execute(ExecuteRequest{
		Command:        "printf bad >&2; exit 8",
		ExecuteTimeout: 5,
		Shell:          "sh",
	}, "instance-exit")

	if response.Success {
		t.Fatal("expected failure")
	}
	if response.ExitCode != 8 {
		t.Fatalf("expected exit code 8, got: %+v", response)
	}
	if !strings.Contains(response.Stderr, "bad") {
		t.Fatalf("expected stderr to be captured, got: %+v", response)
	}
	if response.DurationMs <= 0 {
		t.Fatalf("expected duration to be set, got: %+v", response)
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd agents/nats-executor
go test ./local -run 'TestExecute(InjectsEnvironmentFromJSONRequest|CreatesAndCleansTemporaryFiles|ReturnsStructuredStderrAndExitCode)' -v
```

Expected: fail because `TempFile`, `TempFiles`, `Stdout`, `Stderr`, `ExitCode`, and `DurationMs` are missing or not populated.

- [ ] **Step 3: Add request and response fields**

Modify `agents/nats-executor/local/entity.go`:

```go
type TempFile struct {
	Path    string `json:"path"`
	Content string `json:"content"`
	Mode    uint32 `json:"mode,omitempty"`
}

type ExecuteRequest struct {
	Command        string            `json:"command"`
	ExecuteTimeout int               `json:"execute_timeout"`
	Shell          string            `json:"shell,omitempty"`
	Env            map[string]string `json:"env,omitempty"`
	TempFiles      []TempFile        `json:"temp_files,omitempty"`
	LogCommand     string            `json:"-"`
	LogContext     string            `json:"-"`
	ExecutionID    string            `json:"execution_id,omitempty"`
	StreamLogs     bool              `json:"stream_logs,omitempty"`
	StreamLogTopic string            `json:"stream_log_topic,omitempty"`
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	Stdout     string `json:"stdout,omitempty"`
	Stderr     string `json:"stderr,omitempty"`
	ExitCode   int    `json:"exit_code,omitempty"`
	DurationMs int64  `json:"duration_ms,omitempty"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Code       string `json:"code,omitempty"`
	Error      string `json:"error,omitempty"`
}
```

- [ ] **Step 4: Implement temporary files and structured output**

Modify `agents/nats-executor/local/executor.go` by adding helpers near `invalidExecuteResponse`:

```go
func prepareTempFiles(files []TempFile) ([]string, error) {
	created := make([]string, 0, len(files))
	for _, file := range files {
		path := strings.TrimSpace(file.Path)
		if path == "" {
			cleanupTempFiles(created)
			return nil, fmt.Errorf("temp file path is required")
		}
		mode := os.FileMode(file.Mode)
		if mode == 0 {
			mode = 0600
		}
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			cleanupTempFiles(created)
			return nil, err
		}
		if err := os.WriteFile(path, []byte(file.Content), mode); err != nil {
			cleanupTempFiles(created)
			return nil, err
		}
		created = append(created, path)
	}
	return created, nil
}

func cleanupTempFiles(paths []string) {
	for _, path := range paths {
		if strings.TrimSpace(path) == "" {
			continue
		}
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			logger.Warnf("[Local Execute] failed to remove temp file %s: %v", path, err)
		}
	}
}
```

Add `path/filepath` to imports.

At the start of `Execute` after shell validation:

```go
createdTempFiles, tempErr := prepareTempFiles(req.TempFiles)
if tempErr != nil {
	message := fmt.Sprintf("failed to prepare temp files: %v", tempErr)
	return ExecuteResponse{
		Output:     message,
		InstanceId: instanceId,
		Success:    false,
		Code:       utils.ErrorCodeExecutionFailure,
		Error:      message,
	}
}
defer cleanupTempFiles(createdTempFiles)
```

After `snapshot := outputCapture.Snapshot()`, build individual streams:

```go
stdoutText := decodeExecuteOutput(snapshot.Stdout, shell)
stderrText := decodeExecuteOutput(snapshot.Stderr, shell)
```

Set response fields:

```go
response := ExecuteResponse{
	Output:     decodedOutput,
	Stdout:     stdoutText,
	Stderr:     stderrText,
	ExitCode:   exitCode,
	DurationMs: duration.Milliseconds(),
	InstanceId: instanceId,
	Success:    err == nil && ctx.Err() != context.DeadlineExceeded,
}
```

- [ ] **Step 5: Run Go tests**

Run:

```bash
cd agents/nats-executor
go test ./local ./utils -v
```

Expected: tests pass.

- [ ] **Step 6: Commit**

```bash
git add agents/nats-executor/local/entity.go agents/nats-executor/local/executor.go agents/nats-executor/local/executor_runtime_test.go agents/nats-executor/utils/shared_output_capture.go agents/nats-executor/utils/shared_output_capture_test.go
git commit -m "feat(nats-executor): support env and temp files for local execute"
```

---

### Task 3: Add Python Executor Runtime Wrapper

**Files:**
- Modify: `server/apps/rpc/executor.py`
- Test: `server/apps/monitor/tests/test_collect_detect_service.py`

- [ ] **Step 1: Write failing wrapper test**

Append to `server/apps/monitor/tests/test_collect_detect_service.py`:

```python
def test_executor_runtime_wrapper_sends_env_and_temp_files(monkeypatch):
    from apps.rpc.executor import Executor

    captured = {}

    class FakeClient:
        def run(self, instance_id, request_data, _timeout=None):
            captured["instance_id"] = instance_id
            captured["request_data"] = request_data
            captured["timeout"] = _timeout
            return {"success": True, "stdout": "metric value=1", "stderr": "", "exit_code": 0}

    executor = Executor("node-1")
    executor.local_client = FakeClient()

    result = executor.execute_local_runtime(
        command="telegraf --once --config /tmp/detect.conf",
        timeout=60,
        shell="sh",
        env={"DB_PASSWORD": "secret"},
        temp_files=[{"path": "/tmp/detect.conf", "content": "[[inputs.cpu]]", "mode": 384}],
    )

    assert result["success"] is True
    assert captured["instance_id"] == "node-1"
    assert captured["timeout"] == 60
    assert captured["request_data"]["env"] == {"DB_PASSWORD": "secret"}
    assert captured["request_data"]["temp_files"][0]["path"] == "/tmp/detect.conf"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_executor_runtime_wrapper_sends_env_and_temp_files -v
```

Expected: fail because `execute_local_runtime` does not exist.

- [ ] **Step 3: Implement wrapper**

Add to `server/apps/rpc/executor.py` inside `Executor`:

```python
    def execute_local_runtime(self, command, timeout=60, shell=None, env=None, temp_files=None):
        """
        执行本地命令，并允许以 JSON 形式传递进程环境变量与临时文件。
        用于受控检测场景，避免把凭据拼进 shell 命令字符串。
        """
        request_data = {
            "command": command,
            "execute_timeout": timeout,
            "env": env or {},
            "temp_files": temp_files or [],
        }
        if shell:
            request_data["shell"] = shell
        return self.local_client.run(self.instance_id, request_data, _timeout=timeout)
```

- [ ] **Step 4: Run wrapper test**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_executor_runtime_wrapper_sends_env_and_temp_files -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add server/apps/rpc/executor.py server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "feat(monitor): add executor runtime wrapper"
```

---

### Task 4: Build Detect Runtime Utilities

**Files:**
- Create: `server/apps/monitor/constants/collect_detect.py`
- Create: `server/apps/monitor/services/collect_detect/__init__.py`
- Create: `server/apps/monitor/services/collect_detect/runtime.py`
- Test: `server/apps/monitor/tests/test_collect_detect_service.py`

- [ ] **Step 1: Write failing runtime utility tests**

Append to `server/apps/monitor/tests/test_collect_detect_service.py`:

```python
def test_replace_outputs_preserves_inputs_and_writes_stdout_output():
    from apps.monitor.services.collect_detect.runtime import build_detect_telegraf_config

    source = '''
[[inputs.cpu]]
  percpu = true

[[outputs.nats]]
  servers = ["nats://prod:4222"]
  password = "${NATS_PASSWORD}"
'''

    rendered = build_detect_telegraf_config(source)

    assert "[[inputs.cpu]]" in rendered
    assert "[[outputs.nats]]" not in rendered
    assert "[[outputs.file]]" in rendered
    assert 'files = ["stdout"]' in rendered
    assert 'data_format = "influx"' in rendered


def test_redact_execution_message_masks_sensitive_values():
    from apps.monitor.services.collect_detect.runtime import redact_execution_message

    text = 'password = "abc"\ntoken=xyz\ncommunity = "public"\nnormal = "ok"'

    redacted = redact_execution_message(text)

    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert "public" not in redacted
    assert 'normal = "ok"' in redacted


def test_parse_influx_output_counts_metrics():
    from apps.monitor.services.collect_detect.runtime import parse_influx_metrics

    result = parse_influx_metrics("cpu,host=a usage=1 1\nmem used=2 2\n")

    assert result["metric_count"] == 2
    assert result["sample_metrics"] == ["cpu", "mem"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_replace_outputs_preserves_inputs_and_writes_stdout_output apps/monitor/tests/test_collect_detect_service.py::test_redact_execution_message_masks_sensitive_values apps/monitor/tests/test_collect_detect_service.py::test_parse_influx_output_counts_metrics -v
```

Expected: fail because runtime utilities do not exist.

- [ ] **Step 3: Add constants**

Create `server/apps/monitor/constants/collect_detect.py`:

```python
COLLECT_DETECT_TIMEOUT_SECONDS = 60
COLLECT_DETECT_RESULT_RETENTION_HOURS = 24
COLLECT_DETECT_OUTPUT_LIMIT = 20000
COLLECT_DETECT_BATCH_CONCURRENCY = 3

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

PHASE_VALIDATE = "validate"
PHASE_RENDER_CONFIG = "render_config"
PHASE_PREPARE_RUNTIME = "prepare_runtime"
PHASE_EXECUTE_ONCE = "execute_once"
PHASE_PARSE_OUTPUT = "parse_output"

SENSITIVE_KEYWORDS = (
    "password",
    "token",
    "secret",
    "private_key",
    "community",
    "passphrase",
)
```

Create `server/apps/monitor/services/collect_detect/__init__.py`:

```python
```

- [ ] **Step 4: Implement runtime utilities**

Create `server/apps/monitor/services/collect_detect/runtime.py`:

```python
import hashlib
import json
import re
from collections import OrderedDict

import toml

from apps.monitor.constants.collect_detect import COLLECT_DETECT_OUTPUT_LIMIT, SENSITIVE_KEYWORDS


def stable_fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_detect_telegraf_config(config_text: str) -> str:
    parsed = toml.loads(config_text or "")
    parsed.pop("outputs", None)
    outputs = parsed.setdefault("outputs", OrderedDict())
    outputs["file"] = [
        {
            "files": ["stdout"],
            "data_format": "influx",
        }
    ]
    return toml.dumps(parsed)


def redact_execution_message(value: str, limit: int = COLLECT_DETECT_OUTPUT_LIMIT) -> str:
    text = str(value or "")
    for keyword in SENSITIVE_KEYWORDS:
        text = re.sub(
            rf"(?i)({re.escape(keyword)}\\s*[=:]\\s*)(\"[^\"]*\"|'[^']*'|[^\\s,]+)",
            rf"\\1******",
            text,
        )
    if len(text) > limit:
        return text[:limit] + "\n...[truncated]"
    return text


def parse_influx_metrics(output: str) -> dict:
    names = []
    seen = set()
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        head = line.split(" ", 1)[0]
        metric = head.split(",", 1)[0]
        if not metric:
            continue
        if metric not in seen:
            seen.add(metric)
            names.append(metric)
    return {
        "metric_count": len([line for line in str(output or "").splitlines() if line.strip() and not line.strip().startswith("#")]),
        "sample_metrics": names[:10],
    }
```

- [ ] **Step 5: Run runtime tests**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_replace_outputs_preserves_inputs_and_writes_stdout_output apps/monitor/tests/test_collect_detect_service.py::test_redact_execution_message_masks_sensitive_values apps/monitor/tests/test_collect_detect_service.py::test_parse_influx_output_counts_metrics -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add server/apps/monitor/constants/collect_detect.py server/apps/monitor/services/collect_detect/__init__.py server/apps/monitor/services/collect_detect/runtime.py server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "feat(monitor): add collect detect runtime utilities"
```

---

### Task 5: Implement Detection Service And Celery Task

**Files:**
- Create: `server/apps/monitor/services/collect_detect/service.py`
- Create: `server/apps/monitor/tasks/collect_detect.py`
- Modify: `server/apps/monitor/tasks/__init__.py`
- Test: `server/apps/monitor/tests/test_collect_detect_service.py`

- [ ] **Step 1: Write failing service tests**

Append to `server/apps/monitor/tests/test_collect_detect_service.py`:

```python
import types

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException


@pytest.mark.django_db
def test_create_detect_task_rejects_plugin_without_capability(monkeypatch):
    from apps.monitor.services.collect_detect.service import CollectDetectService

    plugin = MonitorPlugin.objects.create(
        name="Exporter Plugin",
        collector="Telegraf",
        collect_type="exporter",
        support_collect_detect=False,
    )

    with pytest.raises(BaseAppException, match="不支持采集检测"):
        CollectDetectService.create_tasks(
            {
                "monitor_plugin_id": plugin.id,
                "monitor_object_id": 1,
                "collector": "Telegraf",
                "collect_type": "exporter",
                "configs": [],
                "instances": [{"key": "row-1", "node_ids": ["node-1"], "instance_name": "demo"}],
            },
            {
                "username": "admin",
                "domain": "default",
                "current_team": 1,
                "include_children": False,
                "is_superuser": True,
                "group_list": [],
            },
        )


@pytest.mark.django_db
def test_create_detect_task_persists_fingerprint_and_dispatches(monkeypatch):
    from apps.monitor.models import CollectDetectTask
    from apps.monitor.services.collect_detect.service import CollectDetectService

    plugin = MonitorPlugin.objects.create(
        name="Ping Plugin",
        collector="Telegraf",
        collect_type="ping",
        support_collect_detect=True,
    )
    dispatched = []
    monkeypatch.setattr(
        "apps.monitor.services.collect_detect.service.run_collect_detect_task.delay",
        lambda task_id, runtime_payload: dispatched.append((task_id, runtime_payload)),
    )
    monkeypatch.setattr(
        "apps.monitor.services.collect_detect.service.InstanceConfigService._validate_instances_with_plugin_selector",
        lambda instances, monitor_plugin_id, actor_context: None,
    )
    monkeypatch.setattr(
        "apps.monitor.services.collect_detect.service.InstanceConfigService._sanitize_instances_for_onboarding",
        lambda instances, actor_context: instances,
    )

    result = CollectDetectService.create_tasks(
        {
            "monitor_plugin_id": plugin.id,
            "monitor_object_id": 1,
            "collector": "Telegraf",
            "collect_type": "ping",
            "configs": [{"type": "ping"}],
            "instances": [{"key": "row-1", "node_ids": ["node-1"], "instance_name": "demo"}],
        },
        {
            "username": "admin",
            "domain": "default",
            "current_team": 1,
            "include_children": False,
            "is_superuser": True,
            "group_list": [],
        },
    )

    task = CollectDetectTask.objects.get(id=result["tasks"][0]["id"])
    assert task.request_fingerprint
    assert task.node_id == "node-1"
    assert dispatched[0][0] == task.id
    assert dispatched[0][1]["instances"][0]["instance_name"] == "demo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py::test_create_detect_task_rejects_plugin_without_capability apps/monitor/tests/test_collect_detect_service.py::test_create_detect_task_persists_fingerprint_and_dispatches -v
```

Expected: fail because `CollectDetectService` does not exist.

- [ ] **Step 3: Implement service**

Create `server/apps/monitor/services/collect_detect/service.py`:

```python
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.collect_detect import PHASE_VALIDATE, STATUS_FAILED, STATUS_PENDING
from apps.monitor.models import CollectDetectTask, MonitorPlugin
from apps.monitor.services.collect_detect.runtime import redact_execution_message, stable_fingerprint
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.tasks.collect_detect import run_collect_detect_task


class CollectDetectService:
    @staticmethod
    def _plugin_or_error(plugin_id):
        plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
        if not plugin:
            raise BaseAppException("监控插件不存在")
        if not plugin.support_collect_detect:
            raise BaseAppException("当前插件不支持采集检测")
        if plugin.collector != "Telegraf":
            raise BaseAppException("仅 Telegraf 插件支持采集检测")
        return plugin

    @staticmethod
    def _sanitize_snapshot(payload):
        def scrub(value):
            if isinstance(value, dict):
                clean = {}
                for key, item in value.items():
                    if any(token in str(key).lower() for token in ("password", "token", "secret", "private_key", "community")):
                        clean[key] = "******"
                    else:
                        clean[key] = scrub(item)
                return clean
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        return scrub(payload)

    @classmethod
    def create_tasks(cls, payload, actor_context):
        plugin_id = payload.get("monitor_plugin_id")
        plugin = cls._plugin_or_error(plugin_id)
        instances = payload.get("instances") or []
        if not instances:
            raise BaseAppException("缺少检测实例")

        sanitized_instances = InstanceConfigService._sanitize_instances_for_onboarding(instances, actor_context)
        InstanceConfigService._validate_instances_with_plugin_selector(sanitized_instances, plugin_id, actor_context)

        tasks = []
        for instance in sanitized_instances:
            node_ids = instance.get("node_ids") or []
            if len(node_ids) != 1:
                raise BaseAppException("采集检测每个实例必须选择一个采集节点")
            node_id = str(node_ids[0])
            fingerprint_payload = {
                "monitor_plugin_id": plugin_id,
                "monitor_object_id": payload.get("monitor_object_id"),
                "collector": payload.get("collector"),
                "collect_type": payload.get("collect_type"),
                "configs": payload.get("configs") or [],
                "instance": instance,
            }
            task = CollectDetectTask.objects.create(
                status=STATUS_PENDING,
                phase=PHASE_VALIDATE,
                monitor_plugin_id=plugin.id,
                monitor_object_id=int(payload.get("monitor_object_id") or 0),
                collector=payload.get("collector") or plugin.collector,
                collect_type=payload.get("collect_type") or plugin.collect_type,
                node_id=node_id,
                instance_key=str(instance.get("key") or instance.get("instance_id") or ""),
                request_fingerprint=stable_fingerprint(fingerprint_payload),
                created_by=actor_context["username"],
                organization=int(actor_context["current_team"]),
                request_snapshot=cls._sanitize_snapshot(fingerprint_payload),
            )
            runtime_payload = {
                "monitor_plugin_id": plugin.id,
                "monitor_object_id": payload.get("monitor_object_id"),
                "collector": payload.get("collector") or plugin.collector,
                "collect_type": payload.get("collect_type") or plugin.collect_type,
                "configs": payload.get("configs") or [],
                "instances": [instance],
            }
            run_collect_detect_task.delay(task.id, runtime_payload)
            tasks.append({"id": task.id, "request_fingerprint": task.request_fingerprint, "instance_key": task.instance_key})

        return {"tasks": tasks}

    @staticmethod
    def serialize_task(task):
        return {
            "id": task.id,
            "status": task.status,
            "phase": task.phase,
            "request_fingerprint": task.request_fingerprint,
            "instance_key": task.instance_key,
            "error_message": task.error_message,
            "result": task.result,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    @staticmethod
    def mark_failed(task, phase, message, result=None):
        task.status = STATUS_FAILED
        task.phase = phase
        task.error_message = redact_execution_message(message)
        task.result = result or {}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "phase", "error_message", "result", "finished_at", "updated_at"])
```

- [ ] **Step 4: Implement Celery task**

Create `server/apps/monitor/tasks/collect_detect.py`:

```python
import posixpath
import uuid

from celery import shared_task
from django.utils import timezone

from apps.monitor.constants.collect_detect import (
    COLLECT_DETECT_TIMEOUT_SECONDS,
    PHASE_EXECUTE_ONCE,
    PHASE_PARSE_OUTPUT,
    PHASE_PREPARE_RUNTIME,
    PHASE_RENDER_CONFIG,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCESS,
)
from apps.monitor.models import CollectDetectTask
from apps.monitor.services.collect_detect.runtime import (
    build_detect_telegraf_config,
    parse_influx_metrics,
    redact_execution_message,
)
from apps.monitor.utils.plugin_controller import Controller
from apps.rpc.executor import Executor


@shared_task
def run_collect_detect_task(task_id, runtime_payload):
    task = CollectDetectTask.objects.filter(id=task_id).first()
    if not task:
        return

    task.status = STATUS_RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at", "updated_at"])

    try:
        task.phase = PHASE_RENDER_CONFIG
        task.save(update_fields=["phase", "updated_at"])
        if not runtime_payload:
            raise ValueError("缺少检测运行参数")
        controller_data = {
            "monitor_plugin_id": task.monitor_plugin_id,
            "collector": task.collector,
            "collect_type": task.collect_type,
            "configs": runtime_payload["configs"],
            "instances": runtime_payload["instances"],
        }
        config_infos = Controller(controller_data).format_configs()
        if not config_infos:
            raise ValueError("没有可检测的采集配置")
        controller = Controller(controller_data)
        templates_by_type = controller.get_templates_by_collector(task.collector, task.collect_type)
        rendered_parts = []
        env = {}
        for config_info in config_infos:
            templates = templates_by_type.get(config_info.get("type")) or []
            if not templates:
                raise ValueError(f"未找到采集模板: {config_info.get('type')}")
            env.update({key[4:]: value for key, value in config_info.items() if str(key).startswith("ENV_")})
            for template in templates:
                if template["config_type"] != "child":
                    continue
                rendered_parts.append(
                    controller.render_template(
                        template["content"],
                        {
                            **config_info,
                            "config_id": uuid.uuid4().hex.upper(),
                            "plugin_id": task.monitor_plugin_id,
                            "monitor_plugin_id": task.monitor_plugin_id,
                        },
                        escape_toml_strings=template["file_type"] == "toml",
                    )
                )
        if not rendered_parts:
            raise ValueError("没有可检测的 Telegraf 子配置")
        detect_config = build_detect_telegraf_config("\n".join(rendered_parts))

        task.phase = PHASE_PREPARE_RUNTIME
        task.save(update_fields=["phase", "updated_at"])
        temp_path = posixpath.join("/tmp", f"bklite-telegraf-detect-{uuid.uuid4().hex}.conf")
        command = f"telegraf --once --config {temp_path}"

        task.phase = PHASE_EXECUTE_ONCE
        task.save(update_fields=["phase", "updated_at"])
        response = Executor(task.node_id).execute_local_runtime(
            command=command,
            timeout=COLLECT_DETECT_TIMEOUT_SECONDS,
            shell="sh",
            env=env,
            temp_files=[{"path": temp_path, "content": detect_config, "mode": 384}],
        )

        stdout = redact_execution_message(response.get("stdout") or response.get("result") or "")
        stderr = redact_execution_message(response.get("stderr") or "")
        result = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": response.get("exit_code"),
            "duration_ms": response.get("duration_ms"),
        }
        if not response.get("success"):
            task.status = STATUS_FAILED
            task.error_message = stderr or redact_execution_message(response.get("error") or "telegraf --once 执行失败")
            task.result = result
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_message", "result", "finished_at", "updated_at"])
            return

        task.phase = PHASE_PARSE_OUTPUT
        task.save(update_fields=["phase", "updated_at"])
        metric_result = parse_influx_metrics(stdout)
        result.update(metric_result)
        if metric_result["metric_count"] <= 0:
            task.status = STATUS_FAILED
            task.error_message = "未采集到可解析指标"
        else:
            task.status = STATUS_SUCCESS
            task.error_message = ""
        task.result = result
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "phase", "error_message", "result", "finished_at", "updated_at"])
    except Exception as exc:
        task.status = STATUS_FAILED
        task.error_message = redact_execution_message(str(exc))
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
```

- [ ] **Step 5: Run service tests**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py -v
```

Expected: model, utility, wrapper, and service tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/apps/monitor/services/collect_detect/service.py server/apps/monitor/tasks/collect_detect.py server/apps/monitor/tasks/__init__.py server/apps/monitor/tests/test_collect_detect_service.py
git commit -m "feat(monitor): create collect detect tasks"
```

---

### Task 6: Add Detection API

**Files:**
- Modify: `server/apps/monitor/views/node_mgmt.py`
- Test: `server/apps/monitor/tests/test_collect_detect_api.py`

- [ ] **Step 1: Write failing API tests**

Create `server/apps/monitor/tests/test_collect_detect_api.py`:

```python
import types

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.monitor.models import CollectDetectTask
from apps.monitor.views.node_mgmt import NodeMgmtView


class DummyUser:
    username = "admin"
    domain = "default"
    is_superuser = True
    group_list = []


@pytest.mark.django_db
def test_collect_detect_action_returns_created_tasks(monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.views.node_mgmt.CollectDetectService.create_tasks",
        lambda payload, actor_context: {"tasks": [{"id": 1, "request_fingerprint": "fp", "instance_key": "row-1"}]},
    )

    factory = APIRequestFactory()
    request = factory.post(
        "/monitor/api/node_mgmt/collect_detect/",
        {
            "monitor_plugin_id": 1,
            "monitor_object_id": 1,
            "collector": "Telegraf",
            "collect_type": "ping",
            "configs": [],
            "instances": [{"key": "row-1", "node_ids": ["node-1"]}],
        },
        format="json",
        HTTP_COOKIE="current_team=1",
    )
    force_authenticate(request, user=DummyUser())
    request.COOKIES["current_team"] = "1"

    response = NodeMgmtView.as_view({"post": "collect_detect"})(request)

    assert response.data["result"] is True
    assert response.data["data"]["tasks"][0]["request_fingerprint"] == "fp"


@pytest.mark.django_db
def test_collect_detect_batch_status_filters_to_current_actor(monkeypatch):
    task = CollectDetectTask.objects.create(
        status="success",
        phase="parse_output",
        monitor_plugin_id=1,
        monitor_object_id=1,
        collector="Telegraf",
        collect_type="ping",
        node_id="node-1",
        instance_key="row-1",
        request_fingerprint="fp",
        created_by="admin",
        organization=1,
        result={"metric_count": 1},
    )

    factory = APIRequestFactory()
    request = factory.post(
        "/monitor/api/node_mgmt/collect_detect/batch_status/",
        {"task_ids": [task.id]},
        format="json",
        HTTP_COOKIE="current_team=1",
    )
    force_authenticate(request, user=DummyUser())
    request.COOKIES["current_team"] = "1"

    response = NodeMgmtView.as_view({"post": "collect_detect_batch_status"})(request)

    assert response.data["result"] is True
    assert response.data["data"]["tasks"][0]["id"] == task.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_api.py -v
```

Expected: fail because API actions do not exist.

- [ ] **Step 3: Add API actions**

Modify imports in `server/apps/monitor/views/node_mgmt.py`:

```python
from apps.monitor.models import CollectDetectTask
from apps.monitor.services.collect_detect.service import CollectDetectService
```

Add methods to `NodeMgmtView`:

```python
    @action(methods=["post"], detail=False, url_path="collect_detect")
    def collect_detect(self, request):
        actor_context = _build_actor_context(request)
        data = CollectDetectService.create_tasks(request.data, actor_context)
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path=r"collect_detect/(?P<task_id>[^/.]+)")
    def collect_detect_result(self, request, task_id=None):
        actor_context = _build_actor_context(request)
        task = CollectDetectTask.objects.filter(
            id=task_id,
            created_by=actor_context["username"],
            organization=actor_context["current_team"],
        ).first()
        if not task:
            raise BaseAppException("检测任务不存在")
        return WebUtils.response_success(CollectDetectService.serialize_task(task))

    @action(methods=["post"], detail=False, url_path="collect_detect/batch_status")
    def collect_detect_batch_status(self, request):
        actor_context = _build_actor_context(request)
        task_ids = request.data.get("task_ids") or []
        tasks = CollectDetectTask.objects.filter(
            id__in=task_ids,
            created_by=actor_context["username"],
            organization=actor_context["current_team"],
        ).order_by("id")
        return WebUtils.response_success({"tasks": [CollectDetectService.serialize_task(task) for task in tasks]})
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_api.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add server/apps/monitor/views/node_mgmt.py server/apps/monitor/tests/test_collect_detect_api.py
git commit -m "feat(monitor): expose collect detect api"
```

---

### Task 7: Add Web Detection UI

**Files:**
- Modify: `web/src/app/monitor/api/integration.ts`
- Modify: `web/src/app/monitor/types/integration.ts`
- Modify: `web/src/app/monitor/(pages)/integration/list/detail/configure/automatic.tsx`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`
- Create: `web/src/app/monitor/(pages)/integration/list/detail/configure/automaticCollectDetect.ts`
- Create: `web/scripts/monitor-collect-detect-logic-test.ts`

- [ ] **Step 1: Write failing frontend behavior test**

Create `web/scripts/monitor-collect-detect-logic-test.ts`:

```typescript
import {
  buildCollectDetectFingerprint,
  shouldDiscardDetectResult,
} from '../src/app/monitor/(pages)/integration/list/detail/configure/automaticCollectDetect';
import assert from 'node:assert/strict';

const input = {
  monitor_plugin_id: 1,
  monitor_object_id: 2,
  collector: 'Telegraf',
  collect_type: 'ping',
  configs: [{ type: 'ping', interval: 10 }],
  instance: { key: 'row-1', node_ids: ['node-1'], instance_name: 'demo' },
};

assert.equal(
  buildCollectDetectFingerprint(input),
  buildCollectDetectFingerprint({ ...input }),
  'same payload should produce same fingerprint'
);

assert.equal(
  shouldDiscardDetectResult(
    { request_fingerprint: 'old' },
    { detect_fingerprint: 'new' }
  ),
  true,
  'stale result should be discarded'
);

console.log('monitor collect detect logic tests passed');
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web
pnpm exec tsx scripts/monitor-collect-detect-logic-test.ts
```

Expected: fail because `automaticCollectDetect.ts` does not exist.

- [ ] **Step 3: Add API and types**

Modify `web/src/app/monitor/types/integration.ts`:

```typescript
export type CollectDetectStatus = 'pending' | 'running' | 'success' | 'failed';

export interface CollectDetectTaskResult {
  id: number;
  status: CollectDetectStatus;
  phase: string;
  request_fingerprint: string;
  instance_key: string;
  error_message?: string;
  result?: {
    stdout?: string;
    stderr?: string;
    exit_code?: number;
    duration_ms?: number;
    metric_count?: number;
    sample_metrics?: string[];
  };
}

export interface CollectDetectRowState {
  detect_task_id?: number;
  detect_status?: CollectDetectStatus | 'untested';
  detect_fingerprint?: string;
  detect_error?: string;
  detect_result?: CollectDetectTaskResult['result'];
}
```

Modify `web/src/app/monitor/api/integration.ts`:

```typescript
      createCollectDetectTask: async (data: NodeConfigParam) => {
        return await post('/monitor/api/node_mgmt/collect_detect/', data);
      },
      getCollectDetectBatchStatus: async (data: { task_ids: number[] }) => {
        return await post('/monitor/api/node_mgmt/collect_detect/batch_status/', data);
      },
```

- [ ] **Step 4: Add frontend helper**

Create `web/src/app/monitor/(pages)/integration/list/detail/configure/automaticCollectDetect.ts`:

```typescript
import { CollectDetectTaskResult, IntegrationMonitoredObject } from '@/app/monitor/types/integration';

export const buildCollectDetectFingerprint = (input: Record<string, unknown>): string => {
  const normalize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === 'object') {
      return Object.keys(value as Record<string, unknown>)
        .sort()
        .reduce((acc, key) => {
          acc[key] = normalize((value as Record<string, unknown>)[key]);
          return acc;
        }, {} as Record<string, unknown>);
    }
    return value;
  };
  const stable = JSON.stringify(normalize(input));
  let hash = 0;
  for (let index = 0; index < stable.length; index += 1) {
    hash = (hash * 31 + stable.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16);
};

export const shouldDiscardDetectResult = (
  result: Pick<CollectDetectTaskResult, 'request_fingerprint'>,
  row: IntegrationMonitoredObject
): boolean => {
  return Boolean(row.detect_fingerprint && result.request_fingerprint !== row.detect_fingerprint);
};
```

- [ ] **Step 5: Add row status and buttons**

Modify `automatic.tsx`:

```typescript
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { buildCollectDetectFingerprint, shouldDiscardDetectResult } from './automaticCollectDetect';
```

Extend `useIntegrationApi()` destructuring:

```typescript
const { getMonitorNodeList, updateNodeChildConfig, createCollectDetectTask, getCollectDetectBatchStatus } = useIntegrationApi();
```

Add helper inside component:

```typescript
const buildDetectPayload = (rows: IntegrationMonitoredObject[]) => {
  const values = form.getFieldsValue();
  const row = cloneDeep(values);
  delete row.nodes;
  const params = configsInfo?.getParams?.(row, { dataSource: rows, nodeList, objectId }) || {};
  params.monitor_object_id = Number(objectId);
  params.monitor_plugin_id = Number(pluginId);
  return params;
};

const handleDetectRow = async (record: IntegrationMonitoredObject) => {
  const params = buildDetectPayload([record]);
  const fingerprint = buildCollectDetectFingerprint({
    monitor_plugin_id: Number(pluginId),
    monitor_object_id: Number(objectId),
    collector: params.collector,
    collect_type: params.collect_type,
    configs: params.configs,
    instance: params.instances?.[0],
  });
  setDataSource((prev) =>
    prev.map((item) =>
      item.key === record.key
        ? { ...item, detect_status: 'pending', detect_fingerprint: fingerprint }
        : item
    )
  );
  const response = await createCollectDetectTask(params);
  const task = response.tasks?.[0];
  if (!task) return;
  setDataSource((prev) =>
    prev.map((item) =>
      item.key === record.key
        ? { ...item, detect_task_id: task.id, detect_status: 'running', detect_fingerprint: task.request_fingerprint }
        : item
    )
  );
};
```

Add polling `useEffect`:

```typescript
useEffect(() => {
  const runningTaskIds = dataSource
    .filter((row) => row.detect_task_id && ['pending', 'running'].includes(String(row.detect_status)))
    .map((row) => Number(row.detect_task_id));
  if (!runningTaskIds.length) return;

  const timer = window.setTimeout(async () => {
    const response = await getCollectDetectBatchStatus({ task_ids: runningTaskIds });
    const results = response.tasks || [];
    setDataSource((prev) =>
      prev.map((row) => {
        const result = results.find((item: any) => item.id === row.detect_task_id);
        if (!result || shouldDiscardDetectResult(result, row)) return row;
        return {
          ...row,
          detect_status: result.status,
          detect_error: result.error_message,
          detect_result: result.result,
        };
      })
    );
  }, 2000);

  return () => window.clearTimeout(timer);
}, [dataSource, getCollectDetectBatchStatus]);
```

Add a status column before action:

```typescript
const detectColumn = {
  title: t('monitor.integrations.detectStatus'),
  key: 'detect_status',
  width: 180,
  render: (_: any, record: IntegrationMonitoredObject) => {
    if (record.detect_status === 'running' || record.detect_status === 'pending') {
      return <span><LoadingOutlined className="mr-[6px]" />{t('monitor.integrations.detecting')}</span>;
    }
    if (record.detect_status === 'success') {
      return <span className="text-green-600"><CheckCircleOutlined className="mr-[6px]" />{t('common.success')}</span>;
    }
    if (record.detect_status === 'failed') {
      return <span className="text-red-600"><CloseCircleOutlined className="mr-[6px]" />{record.detect_error || t('common.failed')}</span>;
    }
    return <span className="text-gray-400">{t('monitor.integrations.untested')}</span>;
  },
};
```

Add the button in `actionColumn`:

```tsx
<Button
  type="link"
  className="mr-[10px]"
  icon={<ExperimentOutlined />}
  onClick={() => handleDetectRow(record)}
>
  {t('monitor.integrations.collectDetect')}
</Button>
```

Return columns:

```typescript
return [...dataColumns, detectColumn, actionColumn];
```

Reset stale state in `onTableDataChange`:

```typescript
const onTableDataChange = (data: IntegrationMonitoredObject[]) => {
  setDataSource(data.map((row) => ({
    ...row,
    detect_status: row.detect_status === 'running' ? row.detect_status : 'untested',
    detect_error: undefined,
    detect_result: undefined,
  })));
};
```

- [ ] **Step 6: Add locales**

Add to `web/src/app/monitor/locales/zh.json` under `monitor.integrations`:

```json
"collectDetect": "采集检测",
"detectStatus": "检测状态",
"detecting": "检测中",
"untested": "未测试",
"detectAll": "检测全部"
```

Add to `web/src/app/monitor/locales/en.json` under `monitor.integrations`:

```json
"collectDetect": "Detect",
"detectStatus": "Detect Status",
"detecting": "Detecting",
"untested": "Untested",
"detectAll": "Detect All"
```

- [ ] **Step 7: Run frontend checks**

Run:

```bash
cd web
pnpm exec tsx scripts/monitor-collect-detect-logic-test.ts
pnpm lint && pnpm type-check
```

Expected: all commands pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/monitor/api/integration.ts web/src/app/monitor/types/integration.ts 'web/src/app/monitor/(pages)/integration/list/detail/configure/automatic.tsx' 'web/src/app/monitor/(pages)/integration/list/detail/configure/automaticCollectDetect.ts' web/scripts/monitor-collect-detect-logic-test.ts web/src/app/monitor/locales/zh.json web/src/app/monitor/locales/en.json
git commit -m "feat(web): add preflight collect detect controls"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Verify all files touched in previous tasks.

- [ ] **Step 1: Run backend monitor tests**

Run:

```bash
cd server
uv run pytest apps/monitor/tests/test_collect_detect_service.py apps/monitor/tests/test_collect_detect_api.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run NATS Executor tests**

Run:

```bash
cd agents/nats-executor
go test ./local ./utils -v
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd web
pnpm lint && pnpm type-check
```

Expected: both commands pass.

- [ ] **Step 4: Inspect diff for security regressions**

Run:

```bash
git diff --stat HEAD~7..HEAD
git diff HEAD~7..HEAD -- server/apps/monitor/services/collect_detect server/apps/rpc/executor.py agents/nats-executor/local web/src/app/monitor
```

Check that:

- no formal `MonitorInstance`, `CollectConfig`, `CollectorConfiguration`, or `ChildConfig` is created in detection flow;
- no production `outputs.nats`, `outputs.influxdb`, or `outputs.kafka` remains in detection config;
- credentials are passed through `env`, not shell command text;
- stdout/stderr are redacted before storage and API response;
- unsupported plugins are rejected server-side.

- [ ] **Step 5: Commit final fixes if needed**

If verification required small fixes:

```bash
git add <changed-files>
git commit -m "fix(monitor): harden collect detect verification"
```

If no fixes were needed, do not create an empty commit.

## specs: 2026-07-01-telegraf-preflight-collect-detect-design.md

## 背景

监控实例接入前，用户需要确认当前表单配置在目标采集节点上具备实际采集能力。第一版检测只覆盖纯 Telegraf 插件：目标节点已安装 Telegraf，采集由 Telegraf `inputs.*` 直接完成，不依赖额外 exporter、JMX agent、Stargazer remote 或其他伴生探针。

检测必须走真实目标节点链路：后端创建检测任务，通过目标节点上的 NATS Executor 调用本机 `telegraf --once`。检测禁止真实上报，不创建正式监控实例和正式采集配置。

## 目标

- 在自动接入表单的实例行右侧提供检测入口，并支持“检测全部”。
- 复用正式采集的模板渲染和环境变量合并语义，让检测结果可信。
- 禁止检测样本进入正式 NATS、VictoriaMetrics 或其他生产指标链路。
- 返回 `telegraf --once` 的执行消息，帮助用户排查模板、凭据、网络、目标服务和 Telegraf 配置问题。
- 只对声明支持检测的纯 Telegraf 插件展示检测入口；不支持的插件前端不展示按钮，后端也拒绝绕过调用。

## 非目标

- 不支持依赖 exporter、JMX agent、Host Remote、Stargazer remote 或其他外部探针的插件检测。
- 不创建 `MonitorInstance`、`CollectConfig`、`CollectorConfiguration`、`ChildConfig`。
- 不将检测样本写入正式指标库。
- 不在第一版实现高级报表、历史趋势或跨页面结果中心。

## 用户体验

在自动接入表单中，每个实例行展示检测按钮；页面顶部或表格工具区提供“检测全部”。检测入口仅在当前插件支持采集检测时展示。

实例行状态为：

- `未测试`：初始状态，或用户修改了影响采集的字段后重置。
- `检测中`：后端任务已创建或正在执行。
- `成功`：`telegraf --once` 成功结束，并产生至少一条可解析指标。
- `失败`：任一阶段失败，或命令成功但未产生可解析指标。

行内展示简短状态和失败摘要；详情面板展示脱敏、截断后的执行消息，包括 `stdout`、`stderr`、`exit_code`、`duration` 和失败阶段。失败时优先展示 stderr；成功但无指标时展示 stdout/stderr 以便判断原因。

用户修改实例行、节点、全局配置、凭据、采集模块或 interval 后，该行状态重置为 `未测试`。

## 支持范围

新增插件能力标识，例如 `support_collect_detect`。第一版默认不支持，只有确认过的纯 Telegraf 插件显式开启。

前端根据插件能力决定是否展示检测按钮；后端根据同一能力做二次校验。绕过前端调用不支持插件时，后端返回“不支持采集检测”，不创建任务，不执行命令。

## 数据流

1. 前端使用当前接入表单同构数据发起检测请求：
   - `monitor_plugin_id`
   - `monitor_object_id`
   - `collector`
   - `collect_type`
   - `configs`
   - 当前实例行，或“检测全部”对应的多行实例
2. 后端创建异步检测任务，记录发起人、组织、插件、节点、实例行标识和 `request_fingerprint`。
3. 后端复用现有接入路径的校验：
   - 用户和组织上下文
   - 节点权限
   - 插件 `node_selector`
   - 插件检测能力
   - 必填参数
4. 后端复用插件模板查询、`Controller.format_configs()` 和 `Controller.render_template()` 生成临时 Telegraf 配置片段。
5. 后端按真实 sidecar 语义合并运行时变量：
   - 云区域普通变量
   - 云区域敏感变量
   - 主配置 env
   - 子配置 env
   - 模板产生的 `ENV_*` 变量
6. 后端构造检测版 Telegraf 配置：保留真实 `inputs.*`、`processors.*`、`aggregators.*`，移除或替换正式 `outputs.*`，追加本地输出到 stdout 或临时文件。
7. 后端通过目标节点 NATS Executor 执行本机 `telegraf --once --config <临时配置文件>`。
8. Executor 在目标机创建临时配置文件，以进程环境变量注入凭据，执行完成后删除临时文件。
9. 后端解析输出，保存脱敏结果，前端轮询并更新实例行状态。

## 临时配置与环境变量

Telegraf `--once` 不能直接接收整份配置作为变量，仍需通过 `--config <path>` 读取配置文件。配置文件中可以保留 `${VAR}` 形式引用，由 Telegraf 在解析前读取进程环境变量替换。

检测任务在目标节点创建临时配置文件，敏感值不写入临时配置文件。密码、token、private key、community 等特殊凭据只作为本次 `telegraf --once` 子进程环境变量注入，不入库、不回显、不拼接到 shell 命令字符串。

临时配置文件使用唯一文件名，执行完成后删除。失败路径也要尽力清理；清理失败记录内部日志，不把敏感路径或凭据暴露给用户。

## 禁止真实上报

检测任务不得沿用正式 `outputs.nats`、`outputs.influxdb`、`outputs.kafka` 等输出配置。后端构造检测配置时必须移除或禁用所有正式输出，并追加受控本地输出。

本地输出用于解析检测结果，不进入正式指标链路。成功标准是 `telegraf --once` 返回成功且输出中存在至少一条可解析指标。

## 异步任务

检测采用异步任务模型。单行点击创建单个任务；“检测全部”对当前表格中支持检测且参数完整的行批量创建任务。

建议第一版默认单任务超时 60 秒。“检测全部”有限并发，例如同一用户同一页面最多 3 个实例并行；后端保留全局并发保护，超过限制时排队或拒绝新增任务。

任务结果短期保存，例如 24 小时，只服务页面轮询和排障，不进入正式监控历史。

## 状态与错误阶段

任务记录失败阶段：

- `validate`：参数、权限、节点选择、插件能力校验失败。
- `render_config`：模板渲染或 env 构造失败。
- `prepare_runtime`：目标机创建临时配置文件失败，或 Telegraf 不存在。
- `execute_once`：`telegraf --once` 返回非 0、超时、目标采集失败。
- `parse_output`：命令成功但没有可解析指标。

用户可见错误信息必须可行动，例如“目标节点执行超时”“Telegraf 不存在”“SNMP 认证失败”“未采集到指标”“Telegraf 配置解析失败”。后端保留原始执行消息的脱敏截断版本，供详情查看。

## 结果绑定

前端和后端共同使用 `request_fingerprint` 绑定检测结果。fingerprint 由插件 ID、全局配置、实例行字段、节点 ID、采集模块和影响模板/env 的字段计算。

前端收到任务结果时，如果当前行 fingerprint 已变化，丢弃旧结果并保持 `未测试`。这样用户修改配置后，不会误用旧检测成功状态。

## 权限、审计与安全

检测服务端必须复用接入流程的节点权限和组织范围校验，不能只依赖前端展示逻辑。

检测是目标机命令执行能力，必须设置资源边界：

- 命令超时。
- 输出大小上限。
- 临时文件唯一命名和执行后清理。
- “检测全部”并发限制。
- 服务端全局并发保护。

审计记录发起人、组织、插件、节点、实例标识、任务结果和失败阶段，不记录敏感字段值。执行消息展示前必须脱敏并截断，覆盖 password、token、secret、private_key、community 等常见键值。

## 接口草案

后端新增检测相关接口，路径可挂在 `monitor/api/node_mgmt/` 下：

- `POST collect_detect/`：创建单行或批量检测任务。
- `GET collect_detect/{task_id}/`：查询任务状态和结果。
- `POST collect_detect/batch_status/`：批量查询任务状态，供页面轮询。

请求体复用自动接入保存参数结构，额外携带行标识或检测范围。响应返回任务 ID、状态、失败阶段、摘要、指标数量、样例指标名和脱敏执行消息。

## 验收场景

1. 支持检测的纯 Telegraf 插件在实例行展示检测按钮，不支持插件不展示。
2. 单行检测成功时，后端不创建任何正式实例或采集配置，正式指标链路无检测样本。
3. `telegraf --once` 失败时，前端可查看脱敏后的 stdout/stderr/exit_code/duration。
4. 用户修改实例行或全局配置后，旧检测结果不再显示为当前配置成功。
5. 绕过前端调用不支持插件时，后端拒绝执行。
6. 无节点权限、节点不匹配插件 selector、Telegraf 不存在、命令超时、输出无指标等路径都有明确状态和错误阶段。
7. “检测全部”只检测支持且参数完整的行，并受并发限制。

## 待实现要点

- 新增插件检测能力字段及初始化策略。
- 新增检测任务模型、服务和 API。
- 抽取临时配置渲染服务，复用正式接入模板逻辑但不落正式配置。
- 为 NATS Executor 增加安全的“临时文件 + 进程环境变量 + 命令执行 + 清理”执行能力，避免凭据进入命令字符串。
- 前端自动接入表格新增行级检测状态、检测按钮、检测全部和结果详情。
- 增加后端单测覆盖权限、能力判断、输出替换、脱敏、fingerprint 和任务状态。
