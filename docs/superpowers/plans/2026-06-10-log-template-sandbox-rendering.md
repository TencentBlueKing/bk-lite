# Log Template Sandbox Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix log collector templates that fail under the strict Jinja sandbox because they call `.split(',')` directly.

**Architecture:** Keep the existing `StrictSandboxedEnvironment` security boundary unchanged. Add focused real-template rendering tests for the affected collector templates, then replace direct string method calls in those templates with the already-registered `split` filter. Validate the final state with the target pytest file and a grep check that no Jinja template in `server/apps/log/support-files/plugins` still uses `.split(`.

**Tech Stack:** Python 3.12, Django 4.2, pytest, Jinja2 sandbox templates, YAML/TOML collector configuration templates.

---

### Task 1: Add RED Tests For Sandbox-Compatible Template Splitting

**Files:**
- Create: `server/apps/log/tests/test_log_template_sandbox_rendering.py`
- Read: `server/apps/log/utils/plugin_controller.py`
- Read: `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`
- Read: `server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2`
- Read: `server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2`

- [ ] **Step 1: Create the failing test file**

Create `server/apps/log/tests/test_log_template_sandbox_rendering.py` with this exact content:

```python
from pathlib import Path

import yaml

from apps.log.utils.plugin_controller import Controller


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins"


def render_plugin_template(plugin_path: str, template_name: str, context: dict) -> str:
    return Controller({}).render_template(str(PLUGIN_ROOT / plugin_path), template_name, context)


def test_vector_docker_template_renders_container_filter_lists():
    rendered = render_plugin_template(
        "Vector/docker",
        "docker.child.toml.j2",
        {
            "instance_id": "docker-1",
            "config_id": "CFG1",
            "endpoint": "unix:///var/run/docker.sock",
            "enable_container_filter": True,
            "container_name_contains": "nginx,api",
            "container_name_exclude": "vector,logspout",
            "enable_multiline": False,
            "NATS_PROTOCOL": "nats",
        },
    )

    assert 'include_containers = ["nginx", "api"]' in rendered
    assert 'exclude_containers = ["vector", "logspout"]' in rendered


def test_packetbeat_http_template_renders_string_ports_as_number_list():
    rendered = render_plugin_template(
        "Packetbeat/http",
        "http.child.yaml.j2",
        {
            "instance_id": "packetbeat-http-1",
            "ports": "80,8080,8000",
            "capture_body": False,
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["type"] == "http"
    assert data[0]["ports"] == [80, 8080, 8000]


def test_auditbeat_file_integrity_template_renders_default_monitor_paths():
    rendered = render_plugin_template(
        "Auditbeat/file_integrity",
        "file_integrity.child.yaml.j2",
        {
            "instance_id": "auditbeat-file-integrity-1",
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["module"] == "file_integrity"
    assert data[0]["paths"] == ["/etc/passwd", "/etc/shadow", "/etc/sudoers"]


def test_auditbeat_file_integrity_template_renders_exclude_path_string():
    rendered = render_plugin_template(
        "Auditbeat/file_integrity",
        "file_integrity.child.yaml.j2",
        {
            "instance_id": "auditbeat-file-integrity-1",
            "monitor_paths": "/var/log/app.log",
            "exclude_paths": "/tmp,/var/tmp",
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["paths"] == ["/var/log/app.log"]
    assert data[0]["exclude_files"] == ["/tmp", "/var/tmp"]
```

- [ ] **Step 2: Run the new test file and verify RED**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py -q
```

Expected: tests fail because the current templates call direct string methods under the strict sandbox. The failure output must include `jinja2.exceptions.SecurityError: Undefined is not safely callable` and point to one of these template lines:

```text
Vector/docker/docker.child.toml.j2, line 16
Packetbeat/http/http.child.yaml.j2, line 6
Auditbeat/file_integrity/file_integrity.child.yaml.j2, line 10
```

Do not modify production templates until this RED run has been observed.

### Task 2: Fix Vector Docker Template Splitting

**Files:**
- Modify: `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`
- Test: `server/apps/log/tests/test_log_template_sandbox_rendering.py`

- [ ] **Step 1: Replace direct `.split()` calls in the Docker template**

In `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`, replace line 16 with:

```jinja2
include_containers = [{{ _container_name_contains | split(',') | map('trim') | reject('equalto', '') | map('tojson') | join(', ') }}]
```

Replace line 19 with:

```jinja2
exclude_containers = [{{ _container_name_exclude | split(',') | map('trim') | reject('equalto', '') | map('tojson') | join(', ') }}]
```

Leave the rest of the template unchanged.

- [ ] **Step 2: Run the Docker-specific test and verify GREEN for this behavior**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py::test_vector_docker_template_renders_container_filter_lists -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Confirm the remaining target tests still reproduce their current failures**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py -q
```

Expected: the Docker test passes, while Packetbeat HTTP and Auditbeat tests still fail with `SecurityError: Undefined is not safely callable`.

### Task 3: Fix Packetbeat HTTP Template Splitting

**Files:**
- Modify: `server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2`
- Test: `server/apps/log/tests/test_log_template_sandbox_rendering.py`

- [ ] **Step 1: Replace direct `.split()` call in the Packetbeat HTTP template**

In `server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2`, replace line 6 with:

```jinja2
  ports: {{ _ports | split(',') | map('trim') | map('int') | list | to_json }}
```

Leave the non-string branch on line 8 unchanged:

```jinja2
  ports: {{ _ports | to_json }}
```

- [ ] **Step 2: Run the Packetbeat-specific test and verify GREEN for this behavior**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py::test_packetbeat_http_template_renders_string_ports_as_number_list -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run the target test file and verify only Auditbeat remains RED**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py -q
```

Expected: Docker and Packetbeat tests pass. The Auditbeat tests still fail with `SecurityError: Undefined is not safely callable`.

### Task 4: Fix Auditbeat File Integrity Template Splitting

**Files:**
- Modify: `server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2`
- Test: `server/apps/log/tests/test_log_template_sandbox_rendering.py`

- [ ] **Step 1: Replace direct `.split()` calls in the Auditbeat template**

In `server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2`, replace line 10 with:

```jinja2
    {% for path in _monitor_paths | split(',') | map('trim') | reject('equalto', '') %}
```

Replace line 32 with:

```jinja2
    {% for path in _exclude_paths | split(',') | map('trim') | reject('equalto', '') %}
```

Leave the list-input branches unchanged:

```jinja2
    {% for path in _monitor_paths %}
```

```jinja2
    {% for path in _exclude_paths %}
```

- [ ] **Step 2: Run the Auditbeat-specific tests and verify GREEN for this behavior**

Run:

```bash
cd server && uv run pytest \
  apps/log/tests/test_log_template_sandbox_rendering.py::test_auditbeat_file_integrity_template_renders_default_monitor_paths \
  apps/log/tests/test_log_template_sandbox_rendering.py::test_auditbeat_file_integrity_template_renders_exclude_path_string \
  -q
```

Expected:

```text
2 passed
```

- [ ] **Step 3: Run the full target test file and verify GREEN**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py -q
```

Expected:

```text
4 passed
```

### Task 5: Final Verification And Commit

**Files:**
- Modify: `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`
- Modify: `server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2`
- Modify: `server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2`
- Create: `server/apps/log/tests/test_log_template_sandbox_rendering.py`

- [ ] **Step 1: Verify no log plugin Jinja template still calls `.split()` directly**

Run:

```bash
rg "\.split\(" server/apps/log/support-files/plugins
```

Expected: no output and exit code `1`.

If output remains, inspect each hit. Only Jinja template method calls under `server/apps/log/support-files/plugins` are in scope for this plan.

- [ ] **Step 2: Run the target regression tests**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 3: Run the closest existing log template regression tests**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_packetbeat_network_merge.py apps/log/tests/test_collector_logstash_retry_defaults.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Review the final diff**

Run:

```bash
git diff -- server/apps/log/tests/test_log_template_sandbox_rendering.py \
  server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2 \
  server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2 \
  server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2
```

Expected: diff contains only the new regression test file and the five template replacements from `.split(',')` to `| split(',')`.

- [ ] **Step 5: Commit the implementation**

Run:

```bash
git add \
  server/apps/log/tests/test_log_template_sandbox_rendering.py \
  server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2 \
  server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2 \
  server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2
git commit -m "fix: make log templates sandbox-compatible"
```

Expected: commit succeeds and includes only the implementation files listed in this task.
