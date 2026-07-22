# Historical Superpowers change: 2026-06-08-license-enterprise-footprint

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-08-license-enterprise-footprint.md

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

## specs: 2026-06-08-license-enterprise-footprint-design.md

- 日期：2026-06-08
- 模块：`server/config/components`、`server/apps/system_mgmt`、`server/apps/license_mgmt`
- 主题：避免通过删除 `apps/license_mgmt` 目录绕过企业版许可校验

## 1. 背景与目标

当前服务端把“是否启用 license 管控”近似等同于“`server/apps/license_mgmt` 目录是否存在”。这个判断散落在多个入口：

- `server/config/components/app.py`
- `server/config/components/extra.py`
- `server/apps/system_mgmt/management/commands/init_realm_resource.py`

这会带来一个明显绕过点：如果仓库里仍保留其它 app 的 enterprise 增强内容，但用户强制删除 `apps/license_mgmt` 目录，系统就会按社区版路径启动，其它 app 也不会再进入许可校验。

本次目标：

- 不再只根据 `apps/license_mgmt` 目录存在与否判断企业版状态。
- 追加判断各 app 下 `enterprise` 目录是否存在**有效内容**。
- 对只有 `__init__.py` 的空壳 `enterprise` 目录不触发企业版识别。
- 一旦检测到 enterprise 内容仍存在，但 `license_mgmt` 缺失，系统必须在启动阶段失败，不能静默降级。

非目标：

- 不调整现有 license 授权规则、授权码模型和中间件拦截逻辑。
- 不引入人工维护的 enterprise app 白名单作为主判断来源。
- 不把空目录、`__pycache__`、隐藏文件视为 enterprise 有效内容。

## 2. 仓库现状与判定事实

当前仓库已存在多类 enterprise 内容：

| app | enterprise 内容 | 是否应计入 footprint |
|---|---|---|
| `core` | `license_filter.py` | 是 |
| `system_mgmt` | `urls.py`、`sensitive_info.py` | 是 |
| `monitor` | `language/`、`support-files/plugins/` | 是 |
| `node_mgmt` | `support-files/controllers/`、`support-files/collectors/` | 是 |
| `console_mgmt` | 仅 `__init__.py` | 否 |

设计结论：

- “有效 enterprise 内容”不只包含可导入 Python 模块，也包含会被运行时消费的资源文件，如语言包、JSON、插件定义、support-files。
- 只要 `enterprise` 目录下存在除 `__init__.py` 之外的有效文件，就说明该 app 仍然带有企业版 footprint。

## 3. 方案对比

### 方案 A：集中式 enterprise 探测器（采用）

新增统一探测器，扫描 `server/apps/*/enterprise`，输出：

- `has_enterprise_footprint`
- `enterprise_apps`
- `license_mgmt_present`

所有现有入口都改为消费这一个结果。

优点：

- 判断口径唯一，避免不同入口结果漂移。
- 能同时覆盖 Python enterprise 模块和非 Python 资源目录。
- 能在启动早期 fail closed，堵住“删目录降级”的绕过路径。

缺点：

- 需要把现有 3 处判断统一改造为依赖公共函数。

### 方案 B：在现有入口各自补扫描逻辑

在 `app.py`、`extra.py`、`init_realm_resource.py` 分别补 enterprise 目录扫描。

缺点：

- 逻辑重复，后续容易再次漂移。
- 某个入口漏改时，仍可能出现启动配置和菜单资源判断不一致。

### 方案 C：维护 enterprise app 白名单

通过固定配置声明哪些 app 算 enterprise，再检查这些 app 是否存在 enterprise 内容。

缺点：

- 需要长期维护配置，容易与实际目录结构脱节。
- 不能天然适配未来新增 enterprise app。

## 4. 设计总览

### 4.1 新的判定模型

建议增加一个集中式探测接口，例如：

```python
EnterpriseDetectionResult(
    has_enterprise_footprint: bool,
    enterprise_apps: list[str],
    license_mgmt_present: bool,
)
```

语义如下：

- `enterprise_apps`：存在有效 enterprise 内容的 app 列表。
- `has_enterprise_footprint`：`enterprise_apps` 是否非空。
- `license_mgmt_present`：`apps/license_mgmt` 目录是否完整存在。

### 4.2 有效内容判定规则

扫描范围：`server/apps/*/enterprise`

忽略项：

- `__init__.py`
- `__pycache__`
- 隐藏文件/目录

命中项：

- 任意其它 Python 文件
- 任意语言包文件
- 任意 JSON / YAML / 配置资源
- `support-files` 下被运行时读取的插件、控制器、采集器等文件

判定原则：

- 按“是否存在运行时有意义的文件”判断，而不是按“是否可 import”判断。
- 只要某个 app 命中至少一个有效文件，该 app 就进入 `enterprise_apps`。

## 5. 行为规则

统一行为如下：

| 条件 | 行为 |
|---|---|
| `enterprise_apps` 为空 | 视为社区版，跳过 license_mgmt 强制启用 |
| `enterprise_apps` 非空，且 `license_mgmt` 存在 | 视为企业版，按现有逻辑启用 `apps.license_mgmt` 与许可中间件 |
| `enterprise_apps` 非空，但 `license_mgmt` 缺失 | 启动阶段直接报错并阻止启动 |

这意味着：

- 不能再通过删除 `license_mgmt` 目录把带有 enterprise 内容的部署降级成社区版。
- 只有空壳 `enterprise` 目录时，才允许继续按社区版运行。

## 6. 落点设计

### 6.1 `server/config/components/app.py`

当前职责：

- 判断是否把 `apps.license_mgmt` 注入 `INSTALLED_APPS`
- 判断是否挂载两个 license middleware

改造后：

- 不再直接 `os.path.isdir(BASE_DIR/apps/license_mgmt)`。
- 统一调用 enterprise 探测器。
- 若检测到 footprint 但缺少 `license_mgmt`，在 Django 配置初始化阶段直接抛出异常。
- 只有在“footprint 存在且 license_mgmt 完整”时，才注入 `apps.license_mgmt` 与相关 middleware。

### 6.2 `server/config/components/extra.py`

当前职责：

- 基于 `apps/license_mgmt` 目录存在与否，强制把 `license_mgmt` 补进 `INSTALL_APPS`

改造后：

- 复用同一个探测结果。
- 仅在“footprint 存在且 license_mgmt 完整”时把 `license_mgmt` 补进 `INSTALL_APPS`。
- 若 footprint 存在但 `license_mgmt` 缺失，直接传播同一类异常，不允许继续加载局部配置。

### 6.3 `server/apps/system_mgmt/management/commands/init_realm_resource.py`

当前职责：

- 决定是否向 system-manager 注入 License 菜单与相关权限资源

改造后：

- `get_install_apps()` 不再自行判断目录是否存在，而是消费统一探测结果。
- 只有在企业版完整成立时才注入 license 菜单。
- 如果配置非法（有 footprint 但无 `license_mgmt`），命令执行也应直接失败，保证离线初始化行为与服务启动行为一致。

## 7. 错误处理

该问题被定义为**配置错误**，不是可容忍降级场景。

建议异常内容包含：

- 明确原因：检测到企业版内容，但缺少 `apps/license_mgmt`
- 命中的 app 列表
- 建议动作：恢复 `apps/license_mgmt`，或移除所有有效 enterprise 内容后再按社区版运行

示例语义：

```text
Detected enterprise footprint in apps: core, monitor, node_mgmt, system_mgmt, but apps/license_mgmt is missing. Refuse to start without license management.
```

要求：

- 不能静默打印日志后继续启动。
- 不能只在某个入口失败、另一个入口继续运行。
- 异常应尽量在配置初始化早期抛出，避免半初始化状态。

## 8. 测试与验收口径

至少覆盖以下场景：

1. `license_mgmt` 存在，且存在有效 enterprise 内容 -> 正常识别企业版。
2. `license_mgmt` 缺失，但所有 `enterprise` 目录都只有 `__init__.py` 或为空 -> 识别为社区版。
3. `license_mgmt` 缺失，且任一 app 存在有效 enterprise 文件 -> 启动失败。
4. 非 Python 资源文件（如 `monitor`/`node_mgmt` 的 `support-files`、语言包）也能触发 footprint。
5. `console_mgmt` 这种只有 `__init__.py` 的空壳目录不会误触发。
6. `app.py`、`extra.py`、`init_realm_resource.py` 读取到的判定结果一致。

## 9. 预期改动清单

- 新增一个统一的 enterprise footprint 探测模块
- `server/config/components/app.py` 改为消费探测结果
- `server/config/components/extra.py` 改为消费探测结果
- `server/apps/system_mgmt/management/commands/init_realm_resource.py` 改为消费探测结果
- 补充针对目录扫描与非法配置场景的测试

## 10. 决策摘要

- 采用**集中式 enterprise 探测器**，不采用分散扫描或手工白名单。
- “有效 enterprise 内容”包括 Python 代码和运行时资源文件，不限于可导入模块。
- 仅 `__init__.py` 不算 enterprise footprint。
- 发现 enterprise footprint 但缺失 `license_mgmt` 时，系统必须 fail closed，直接拒绝启动。
