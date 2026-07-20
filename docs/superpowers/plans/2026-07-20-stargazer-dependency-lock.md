# Stargazer Dependency Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Stargazer 镜像严格安装 `uv.lock` 中的依赖，并固定 Sanic 24.6.0 已验证兼容的 tracerite 1.1.3。

**Architecture:** `pyproject.toml` 显式声明 tracerite 精确版本，`uv.lock` 继续作为完整解析结果的唯一真相源。Docker 使用固定版本 uv 将锁定依赖安装到 `/app/.venv`，并通过 PATH 让 Supervisor 的 service 与 worker 共用该环境；静态合同测试、运行时导入测试和无缓存镜像烟测共同阻止依赖再次漂移。

**Tech Stack:** Python 3.12、uv 0.8.16、pytest、Docker、Sanic 24.6.0、tracerite 1.1.3、Supervisor。

## Global Constraints

- 不升级 Sanic、sanic-ext 或 tracerite；精确版本必须为 `sanic==24.6.0`、`sanic-ext==23.12.0`、`tracerite==1.1.3`。
- 生产镜像必须执行 `uv sync --frozen --all-groups --all-extras`，不得执行 `pip3 install -e` 重新求解应用依赖。
- uv 构建工具固定为 `uv==0.8.16`。
- `/app/.venv/bin` 必须位于镜像 PATH 首位，Supervisor 现有 `sanic` 与 `python` 命令保持不变。
- `NEXUS_PYTHON_REPOSITY` 非空时必须作为 uv 默认索引；空值时使用 uv 默认索引。
- 不修改 Stargazer 业务逻辑、worker 数量、Supervisor 重启策略或 Python 基础镜像。
- 不手工编辑 `uv.lock`，统一由 `uv lock` 生成。
- 所有注释、提交信息和新增文档使用中文。

---

## File Structure

- `agents/stargazer/tests/test_dependency_lock_contract.py`：唯一新增测试文件，验证声明、锁文件、Docker 安装策略和实际 Python 运行时兼容性。
- `agents/stargazer/pyproject.toml`：增加 tracerite 直接精确约束。
- `agents/stargazer/uv.lock`：由 uv 重新生成 Stargazer 根包的直接依赖元数据；tracerite 制品版本仍为 1.1.3。
- `agents/stargazer/support-files/docker/Dockerfile`：安装固定 uv、使用 frozen lock 同步依赖、显式传递 Nexus 索引并设置虚拟环境 PATH。

### Task 1: 用合同测试驱动完整依赖锁定

**Files:**
- Create: `agents/stargazer/tests/test_dependency_lock_contract.py`
- Modify: `agents/stargazer/pyproject.toml:13-46`
- Modify: `agents/stargazer/uv.lock`
- Modify: `agents/stargazer/support-files/docker/Dockerfile:1-26`

**Interfaces:**
- Consumes: `pyproject.toml` 的 PEP 621 `project.dependencies`、uv lock v1 的 `package` 数组、环境中已安装的 Python distribution metadata。
- Produces: `tracerite==1.1.3` 直接依赖合同、`/app/.venv` 镜像运行环境，以及 `test_dependency_lock_contract.py` 中四个持续回归测试。

- [ ] **Step 1: 写入失败的依赖与镜像合同测试**

创建 `agents/stargazer/tests/test_dependency_lock_contract.py`，内容如下：

```python
import importlib
import tomllib
from importlib.metadata import version
from pathlib import Path


STARGAZER_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = STARGAZER_ROOT / "pyproject.toml"
LOCK_PATH = STARGAZER_ROOT / "uv.lock"
DOCKERFILE_PATH = STARGAZER_ROOT / "support-files" / "docker" / "Dockerfile"


def _read_toml(path: Path) -> dict:
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def _logical_dockerfile() -> str:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    return content.replace("\\\n", " ")


def test_pyproject_directly_pins_tracerite() -> None:
    dependencies = _read_toml(PYPROJECT_PATH)["project"]["dependencies"]

    assert "tracerite==1.1.3" in dependencies


def test_lock_contains_the_approved_tracerite_version() -> None:
    packages = _read_toml(LOCK_PATH)["package"]
    tracerite_packages = [
        package for package in packages if package["name"] == "tracerite"
    ]

    assert [package["version"] for package in tracerite_packages] == ["1.1.3"]


def test_dockerfile_installs_the_frozen_uv_environment() -> None:
    dockerfile = _logical_dockerfile()

    assert "pip3 install uv==0.8.16" in dockerfile
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in dockerfile
    assert dockerfile.count("uv sync --frozen --all-groups --all-extras") == 2
    assert '--default-index "$NEXUS_PYTHON_REPOSITY"' in dockerfile
    assert '--allow-insecure-host "$(echo $NEXUS_PYTHON_REPOSITY' in dockerfile
    assert "pip3 install -e" not in dockerfile


def test_sanic_imports_with_the_approved_tracerite_api() -> None:
    tracerite_html = importlib.import_module("tracerite.html")

    assert version("sanic") == "24.6.0"
    assert version("tracerite") == "1.1.3"
    assert hasattr(tracerite_html, "style")
    importlib.import_module("sanic")
```

- [ ] **Step 2: 运行测试并确认 RED 来自缺失的锁定合同**

在 `agents/stargazer` 执行：

```bash
uv run pytest tests/test_dependency_lock_contract.py -v
```

预期：测试失败；至少包含以下两个真实产品合同失败，不得是语法错误或测试收集错误：

```text
FAILED test_pyproject_directly_pins_tracerite
FAILED test_dockerfile_installs_the_frozen_uv_environment
```

若本地环境尚未同步 1.1.3，`test_sanic_imports_with_the_approved_tracerite_api` 也会以实际 tracerite 版本不等于 1.1.3 失败，这是允许的第三个 RED。

- [ ] **Step 3: 在 pyproject 中增加最小直接依赖约束**

在 `agents/stargazer/pyproject.toml` 中紧随 Sanic 声明加入一行，形成：

```toml
dependencies = [
    "pyarmor==9.0.7",
    "sanic==24.6.0",
    "tracerite==1.1.3",
    "sanic-ext==23.12.0",
```

不得调整或顺手收紧其他依赖。

- [ ] **Step 4: 使用 uv 更新锁文件而非手工编辑**

在 `agents/stargazer` 执行：

```bash
uv lock
```

预期：命令成功；`uv.lock` 的 `[[package]] name = "tracerite"` 仍为 1.1.3，同时 `name = "stargazer"` 包的 dependency metadata 新增直接 `tracerite` 约束。

- [ ] **Step 5: 将 Dockerfile 改为 frozen lock 安装**

保留 Dockerfile 的基础镜像、apt 安装、源码复制和 Supervisor 配置，将依赖安装部分替换为以下完整内容：

```dockerfile
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install uv==0.8.16

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv sync --frozen --all-groups --all-extras \
        --default-index "$NEXUS_PYTHON_REPOSITY" \
        --allow-insecure-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    else \
    uv sync --frozen --all-groups --all-extras; \
    fi

ENV PATH="/app/.venv/bin:$PATH"

RUN apt-get reinstall -y supervisor
CMD ["supervisord", "-n"]
```

这里保留 pip 的 Nexus 配置供 `pip3 install uv==0.8.16` 使用；uv 同步阶段显式使用同一索引，不依赖 pip 配置透传。

- [ ] **Step 6: 验证锁文件与聚焦测试 GREEN**

在 `agents/stargazer` 依次执行：

```bash
uv lock --check
uv run pytest tests/test_dependency_lock_contract.py -v
```

预期：锁文件检查成功，测试输出 `4 passed`；不得出现 warning、skip 或 xfail。

- [ ] **Step 7: 运行 Stargazer 最小质量门禁**

在 `agents/stargazer` 执行：

```bash
make lint
```

预期：pre-commit 对全部配置项返回 Passed；若门禁报告与本任务无关的既有失败，保留完整输出并先区分基线，不修改无关文件。

- [ ] **Step 8: 检查最小 diff 并提交 Task 1**

在仓库根执行：

```bash
git diff --check
git diff -- agents/stargazer/pyproject.toml agents/stargazer/uv.lock agents/stargazer/support-files/docker/Dockerfile agents/stargazer/tests/test_dependency_lock_contract.py
git status --short
```

预期：仅上述四个任务文件进入本次变更范围，`git diff --check` 无输出。

提交：

```bash
git add agents/stargazer/pyproject.toml agents/stargazer/uv.lock agents/stargazer/support-files/docker/Dockerfile agents/stargazer/tests/test_dependency_lock_contract.py
git commit -m "fix(stargazer): 锁定镜像 Python 依赖"
```

### Task 2: 无缓存镜像和 Supervisor 运行环境验收

**Files:**
- Verify only: `agents/stargazer/support-files/docker/Dockerfile`
- Verify only: `agents/stargazer/support-files/supervisor/service.conf`
- Verify only: `agents/stargazer/support-files/supervisor/worker.conf`

**Interfaces:**
- Consumes: Task 1 生成的 `bklite/stargazer` Docker 构建输入和 `/app/.venv`。
- Produces: 镜像内 distribution 版本、可执行文件路径、Sanic 导入和 ARQ WorkerSettings 导入的真实证据。

- [ ] **Step 1: 无缓存构建默认索引镜像**

在 `agents/stargazer` 执行：

```bash
docker build --no-cache -t bklite/stargazer:dependency-lock-test -f support-files/docker/Dockerfile .
```

预期：镜像构建成功；依赖阶段输出 `uv sync --frozen --all-groups --all-extras`，不出现 `pip3 install -e`。

- [ ] **Step 2: 验证镜像内版本、API 与可执行路径**

执行：

```bash
docker run --rm --entrypoint python bklite/stargazer:dependency-lock-test -c 'import importlib, shutil, sys; from importlib.metadata import version; html = importlib.import_module("tracerite.html"); assert version("sanic") == "24.6.0"; assert version("tracerite") == "1.1.3"; assert hasattr(html, "style"); assert shutil.which("python") == "/app/.venv/bin/python"; assert shutil.which("sanic") == "/app/.venv/bin/sanic"; importlib.import_module("sanic"); print(sys.executable, version("sanic"), version("tracerite"))'
```

预期输出：

```text
/app/.venv/bin/python 24.6.0 1.1.3
```

- [ ] **Step 3: 验证 service 与 worker 的导入边界而不连接外部服务**

执行：

```bash
docker run --rm --entrypoint python bklite/stargazer:dependency-lock-test -c 'from server import app; from core.worker import WorkerSettings; assert app is not None; assert WorkerSettings.functions; print("service-worker-imports-ok")'
```

预期输出：

```text
service-worker-imports-ok
```

该命令只导入模块，不调用 `app.run` 或 `run_worker`，不得连接 Redis、NATS 或其他生产服务。

- [ ] **Step 4: 验证 Nexus 构建分支的命令合同**

无需在计划中记录或提交真实 Nexus 地址。复用 Task 1 的 `test_dockerfile_installs_the_frozen_uv_environment`，确认非空 `NEXUS_PYTHON_REPOSITY` 分支包含 `--default-index` 和 `--allow-insecure-host`。发布环境把测试地址注入 `STARGAZER_TEST_NEXUS_URL` 后，在 `agents/stargazer` 依次执行：

```bash
test -n "$STARGAZER_TEST_NEXUS_URL"
docker build --no-cache --build-arg NEXUS_PYTHON_REPOSITY="$STARGAZER_TEST_NEXUS_URL" -t bklite/stargazer:dependency-lock-nexus-test -f support-files/docker/Dockerfile .
```

预期：uv 与全部锁定制品仅从注入的测试 Nexus 获取；若缺少 `uv==0.8.16` 或 `tracerite==1.1.3`，构建失败且不回退其他版本。命令中的地址由发布环境注入，不写入仓库、日志或计划文件。

- [ ] **Step 5: 汇总最终验证证据**

在仓库根执行：

```bash
git status --short
git log -1 --oneline
```

预期：Task 1 提交存在，Task 2 不产生新文件或未提交改动。记录以下证据用于交付说明：聚焦测试 `4 passed`、`uv lock --check` 成功、`make lint` 成功、默认索引无缓存镜像成功、镜像版本输出和 service/worker 导入输出。
