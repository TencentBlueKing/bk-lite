# License Enterprise Footprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用统一的 enterprise footprint 探测替换 `license_mgmt` 目录存在判断，防止通过删除 `apps/license_mgmt` 绕过企业版许可校验。

**Architecture:** 在 `server/config/components` 下新增一个集中式探测模块，负责扫描 `server/apps/*/enterprise` 并判定哪些 app 仍有有效 enterprise 内容。`app.py`、`extra.py`、`init_realm_resource.py` 全部改为复用这一个结果；只要探测到 enterprise footprint 但缺少 `apps/license_mgmt`，就在启动/初始化早期直接抛错。

**Tech Stack:** Python 3.12, Django 4.2, pytest, importlib reload, pathlib.

---

## File Structure

- Create: `server/config/components/enterprise.py`
  - 放置 enterprise footprint 的扫描、状态对象、错误类型和统一守卫入口。
- Create: `server/apps/core/tests/test_enterprise_footprint.py`
  - 纯单测覆盖：有效文件识别、`__init__.py` 空壳忽略、缺失 `license_mgmt` 时 fail closed、`app.py`/`extra.py` 的接线行为。
- Create: `server/apps/system_mgmt/tests/test_init_realm_resource_license.py`
  - 覆盖 `get_install_apps()` 对统一探测器的复用，以及非法配置时直接失败。
- Modify: `server/config/components/app.py`
  - 改为使用统一探测结果决定是否注入 `apps.license_mgmt` 与两个 license middleware。
- Modify: `server/config/components/extra.py`
  - 改为使用统一探测结果决定是否在显式 `INSTALL_APPS` 中补齐 `license_mgmt`。
- Modify: `server/apps/system_mgmt/management/commands/init_realm_resource.py`
  - 改为使用统一探测结果决定是否把 `license_mgmt` 加入 install app 集合。

## Task 1: 新增集中式 enterprise footprint 探测器

**Files:**
- Create: `server/config/components/enterprise.py`
- Create: `server/apps/core/tests/test_enterprise_footprint.py`

- [ ] **Step 1: 先写 footprint 探测失败用例**

```python
from pathlib import Path

import pytest

from config.components.enterprise import (
    EnterpriseFootprintError,
    detect_enterprise_footprint,
    require_enterprise_license_management,
)


def _write(path: Path, content: str = "x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_enterprise_footprint_counts_resource_files_and_ignores_init_only(tmp_path):
    _write(tmp_path / "apps" / "console_mgmt" / "enterprise" / "__init__.py", "")
    _write(tmp_path / "apps" / "monitor" / "enterprise" / "support-files" / "plugins" / "demo.json", "{}")
    _write(tmp_path / "apps" / "system_mgmt" / "enterprise" / "urls.py", "urlpatterns = []")
    _write(tmp_path / "apps" / "license_mgmt" / "__init__.py", "")

    status = detect_enterprise_footprint(tmp_path)

    assert status.has_enterprise_footprint is True
    assert status.enterprise_apps == ("monitor", "system_mgmt")
    assert status.license_mgmt_present is True
    assert status.should_enable_license_mgmt is True


def test_require_enterprise_license_management_rejects_missing_license_app(tmp_path):
    _write(tmp_path / "apps" / "monitor" / "enterprise" / "language" / "zh-Hans.yaml", "key: value")

    with pytest.raises(EnterpriseFootprintError, match="monitor"):
        require_enterprise_license_management(tmp_path)


def test_require_enterprise_license_management_allows_init_only_enterprise_dirs(tmp_path):
    _write(tmp_path / "apps" / "console_mgmt" / "enterprise" / "__init__.py", "")

    status = require_enterprise_license_management(tmp_path)

    assert status.has_enterprise_footprint is False
    assert status.enterprise_apps == ()
    assert status.license_mgmt_present is False
```

- [ ] **Step 2: 运行测试，确认现在先失败**

Run:

```bash
cd server && uv run pytest apps/core/tests/test_enterprise_footprint.py -k "enterprise_footprint or license_management" -v
```

Expected: FAIL，当前还没有 `config.components.enterprise` 模块。

- [ ] **Step 3: 写最小探测实现**

在 `server/config/components/enterprise.py` 新建集中式探测器：

```python
from dataclasses import dataclass
from pathlib import Path

from config.components.base import BASE_DIR


class EnterpriseFootprintError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnterpriseFootprintStatus:
    enterprise_apps: tuple[str, ...]
    license_mgmt_present: bool

    @property
    def has_enterprise_footprint(self) -> bool:
        return bool(self.enterprise_apps)

    @property
    def should_enable_license_mgmt(self) -> bool:
        return self.has_enterprise_footprint and self.license_mgmt_present


def _project_root(base_dir: str | Path | None = None) -> Path:
    return Path(base_dir or BASE_DIR)


def _apps_dir(base_dir: str | Path | None = None) -> Path:
    return _project_root(base_dir) / "apps"


def _is_ignored_path(path: Path) -> bool:
    return any(part.startswith(".") or part == "__pycache__" for part in path.parts)


def _has_effective_enterprise_files(enterprise_dir: Path) -> bool:
    if not enterprise_dir.is_dir():
        return False
    for path in enterprise_dir.rglob("*"):
        if _is_ignored_path(path) or path.is_dir():
            continue
        if path.name == "__init__.py":
            continue
        return True
    return False


def detect_enterprise_footprint(base_dir: str | Path | None = None) -> EnterpriseFootprintStatus:
    apps_dir = _apps_dir(base_dir)
    enterprise_apps: list[str] = []
    for app_dir in sorted(apps_dir.iterdir(), key=lambda item: item.name):
        if not app_dir.is_dir() or app_dir.name.startswith(("_", ".")):
            continue
        if _has_effective_enterprise_files(app_dir / "enterprise"):
            enterprise_apps.append(app_dir.name)
    return EnterpriseFootprintStatus(
        enterprise_apps=tuple(enterprise_apps),
        license_mgmt_present=(apps_dir / "license_mgmt").is_dir(),
    )


def require_enterprise_license_management(base_dir: str | Path | None = None) -> EnterpriseFootprintStatus:
    status = detect_enterprise_footprint(base_dir)
    if status.has_enterprise_footprint and not status.license_mgmt_present:
        apps_text = ", ".join(status.enterprise_apps)
        raise EnterpriseFootprintError(
            f"Detected enterprise footprint in apps: {apps_text}, but apps/license_mgmt is missing. "
            "Refuse to start without license management."
        )
    return status
```

- [ ] **Step 4: 重新运行测试，确认探测器行为正确**

Run:

```bash
cd server && uv run pytest apps/core/tests/test_enterprise_footprint.py -k "enterprise_footprint or license_management" -v
```

Expected: PASS

- [ ] **Step 5: 提交探测器骨架**

```bash
git add server/config/components/enterprise.py server/apps/core/tests/test_enterprise_footprint.py
git commit -m "feat: detect enterprise footprint"
```

## Task 2: 让 `app.py` 和 `extra.py` 统一复用探测器

**Files:**
- Modify: `server/config/components/app.py`
- Modify: `server/config/components/extra.py`
- Modify: `server/apps/core/tests/test_enterprise_footprint.py`

- [ ] **Step 1: 先补两处接线测试**

在 `server/apps/core/tests/test_enterprise_footprint.py` 追加：

```python
import importlib
import sys


def _reload(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_app_component_refuses_start_when_enterprise_footprint_exists_without_license_mgmt(monkeypatch, tmp_path):
    _write(tmp_path / "apps" / "monitor" / "enterprise" / "support-files" / "plugins" / "demo.json", "{}")

    import config.components.base as base_settings

    monkeypatch.setattr(base_settings, "BASE_DIR", tmp_path)
    monkeypatch.setenv("INSTALL_APPS", "")

    with pytest.raises(RuntimeError, match="monitor"):
        _reload("config.components.app")


def test_extra_component_adds_license_mgmt_to_explicit_install_apps(monkeypatch, tmp_path):
    _write(tmp_path / "apps" / "__init__.py", "")
    _write(tmp_path / "apps" / "monitor" / "__init__.py", "")
    _write(tmp_path / "apps" / "monitor" / "enterprise" / "language" / "en.yaml", "key: value")
    _write(tmp_path / "apps" / "license_mgmt" / "__init__.py", "")

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("INSTALL_APPS", "monitor")

    reloaded = _reload("config.components.extra")

    assert set(reloaded.install_apps.split(",")) == {"monitor", "license_mgmt"}
```

- [ ] **Step 2: 跑这些测试，确认接线还没完成**

Run:

```bash
cd server && uv run pytest apps/core/tests/test_enterprise_footprint.py -k "app_component or extra_component" -v
```

Expected: FAIL，`app.py` 和 `extra.py` 还在直接判断 `apps/license_mgmt` 目录。

- [ ] **Step 3: 改造 `app.py` / `extra.py`**

在 `server/config/components/app.py` 顶部补导入并替换旧判断：

```python
from config.components.enterprise import require_enterprise_license_management

_install_apps = {item.strip() for item in os.getenv("INSTALL_APPS", "").split(",") if item.strip()}
_enterprise_status = require_enterprise_license_management(BASE_DIR)

if _enterprise_status.should_enable_license_mgmt:
    _install_apps.add("license_mgmt")

if "license_mgmt" in _install_apps:
    INSTALLED_APPS += ("apps.license_mgmt",)
    MIDDLEWARE += (
        "apps.license_mgmt.middleware.license_guard.LicenseAppGuardMiddleware",
        "apps.license_mgmt.middleware.license_guard.LicenseCreateGuardMiddleware",
    )
```

在 `server/config/components/extra.py` 改成：

```python
from pathlib import Path

from config.components.enterprise import require_enterprise_license_management

install_apps = os.getenv("INSTALL_APPS", "")
_enterprise_status = require_enterprise_license_management(Path.cwd())

if install_apps and _enterprise_status.should_enable_license_mgmt:
    apps_set = {a.strip() for a in install_apps.split(",") if a.strip()}
    apps_set.add("license_mgmt")
    install_apps = ",".join(sorted(apps_set))
```

- [ ] **Step 4: 重新跑核心探测测试**

Run:

```bash
cd server && uv run pytest apps/core/tests/test_enterprise_footprint.py -v
```

Expected: PASS

- [ ] **Step 5: 提交 config 接线改造**

```bash
git add server/config/components/app.py server/config/components/extra.py server/apps/core/tests/test_enterprise_footprint.py
git commit -m "refactor: centralize enterprise license checks"
```

## Task 3: 让 `init_realm_resource` 复用同一份判定结果

**Files:**
- Modify: `server/apps/system_mgmt/management/commands/init_realm_resource.py`
- Create: `server/apps/system_mgmt/tests/test_init_realm_resource_license.py`

- [ ] **Step 1: 先写 management command 的纯测试**

```python
import types

import pytest

from apps.system_mgmt.management.commands.init_realm_resource import get_install_apps
from config.components.enterprise import EnterpriseFootprintError


def test_get_install_apps_adds_license_mgmt_when_enterprise_status_requires_it(monkeypatch, settings):
    monkeypatch.setenv("INSTALL_APPS", "monitor")
    monkeypatch.setattr(
        "apps.system_mgmt.management.commands.init_realm_resource.require_enterprise_license_management",
        lambda base_dir: types.SimpleNamespace(should_enable_license_mgmt=True),
    )

    assert get_install_apps() == {"monitor", "license_mgmt"}


def test_get_install_apps_propagates_enterprise_mismatch(monkeypatch, settings):
    monkeypatch.setattr(
        "apps.system_mgmt.management.commands.init_realm_resource.require_enterprise_license_management",
        lambda base_dir: (_ for _ in ()).throw(EnterpriseFootprintError("monitor mismatch")),
    )

    with pytest.raises(EnterpriseFootprintError, match="monitor mismatch"):
        get_install_apps()
```

- [ ] **Step 2: 跑这组测试，确认当前实现未复用统一探测器**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_init_realm_resource_license.py -v
```

Expected: FAIL，当前 `get_install_apps()` 还在自己判断 `apps/license_mgmt` 目录。

- [ ] **Step 3: 改造 management command**

在 `server/apps/system_mgmt/management/commands/init_realm_resource.py` 顶部补导入：

```python
from config.components.enterprise import require_enterprise_license_management
```

把 `get_install_apps()` 改成：

```python
def get_install_apps() -> set[str]:
    apps = {item.strip() for item in os.getenv("INSTALL_APPS", "").split(",") if item.strip()}

    from django.conf import settings

    enterprise_status = require_enterprise_license_management(settings.BASE_DIR)
    if enterprise_status.should_enable_license_mgmt:
        apps.add("license_mgmt")
    return apps
```

- [ ] **Step 4: 跑最终回归**

Run:

```bash
cd server && uv run pytest apps/core/tests/test_enterprise_footprint.py apps/system_mgmt/tests/test_init_realm_resource_license.py -v
```

Expected: PASS

- [ ] **Step 5: 提交 command 收口改造**

```bash
git add server/apps/system_mgmt/management/commands/init_realm_resource.py server/apps/system_mgmt/tests/test_init_realm_resource_license.py
git commit -m "test: guard realm init with enterprise footprint"
```

## Task 4: 做一次最小模块级验收

**Files:**
- Modify: none
- Test: `server/apps/core/tests/test_enterprise_footprint.py`
- Test: `server/apps/system_mgmt/tests/test_init_realm_resource_license.py`

- [ ] **Step 1: 跑 server 最小相关用例集合**

```bash
cd server && uv run pytest \
  apps/core/tests/test_enterprise_footprint.py \
  apps/system_mgmt/tests/test_init_realm_resource_license.py \
  apps/system_mgmt/tests/sensitive_info_management_test.py -k "enterprise or system_mgmt_urls" -v
```

Expected: PASS

- [ ] **Step 2: 读输出确认 4 个验收口径都被覆盖**

```text
1. 有效 enterprise 资源文件会触发 footprint
2. 只有 __init__.py 的 enterprise 目录不会触发
3. footprint 存在但缺少 license_mgmt 会抛错
4. app.py / extra.py / init_realm_resource.py 读取结果一致
```

- [ ] **Step 3: 如有失败，优先修测试夹具而不是放宽生产逻辑**

```python
# 不要把 require_enterprise_license_management 改成日志告警后继续运行；
# 如测试因路径夹具不完整失败，只补全 tmp_path 下的 apps 结构和 monkeypatch。
```

- [ ] **Step 4: 生成最终 diff 检查**

```bash
git --no-pager diff --stat HEAD~3..HEAD
```

Expected: 只包含 `config/components`、`apps/core/tests`、`apps/system_mgmt` 相关文件。

- [ ] **Step 5: 提交验收确认**

```bash
git commit --allow-empty -m "chore: verify enterprise footprint guard"
```
