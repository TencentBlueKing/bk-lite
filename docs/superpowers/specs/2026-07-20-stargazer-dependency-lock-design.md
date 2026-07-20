# Stargazer 依赖锁定设计

## 背景

Stargazer 固定使用 `sanic==24.6.0`。该版本仅声明 `tracerite>=1.0.0`，没有上限。2026-07-19 发布的 tracerite 2.6.0 将 `tracerite.html.style` 改名为 `html_style`，而 Sanic 24.6.0 初始化错误页时仍访问旧属性，导致 service 和 ARQ worker 在导入 Sanic 时退出。

仓库中的 `uv.lock` 已解析为 `tracerite==1.1.3`，但生产 Dockerfile 使用 `pip3 install -e ".[dev,...]"` 全新解析依赖，没有消费锁文件。因此，同一份 Stargazer 代码会随 PyPI 或 Nexus 中的传递依赖变化生成不同镜像。

tracerite 2.6.1 和 2.6.2 已恢复 `style` 别名，重新构建当前镜像可能暂时恢复，但不能消除构建漂移。

## 目标

- Stargazer 镜像必须安装 `uv.lock` 中记录的完整依赖集合。
- 明确记录 Sanic 24.6.0 已验证的 tracerite 版本，避免传递依赖关系被忽略。
- service 和 worker 必须运行同一个锁定的 Python 环境。
- 锁文件过期、依赖无法获取或兼容性导入失败时，镜像构建必须失败，不得生成不确定镜像。
- 保持现有全部 optional extras、开发依赖和 Nexus 私有镜像源能力。

## 非目标

- 不升级 Sanic、sanic-ext 或 tracerite。
- 不修改 Stargazer 业务逻辑、worker 数量或 Supervisor 重启策略。
- 不处理本次拉取产生的其他模块合并冲突。
- 本次不扩展到 Python 基础镜像 digest 或操作系统包锁定。

## 方案

### 依赖声明

在 `agents/stargazer/pyproject.toml` 的运行时依赖中增加：

```toml
"tracerite==1.1.3",
```

选择 1.1.3 的原因：

- 当前 `uv.lock` 已锁定该版本；
- 该版本提供 Sanic 24.6.0 使用的 `tracerite.html.style`；
- 精确版本不会因上游重新发布兼容版本而改变镜像内容。

更新锁文件后，Stargazer 根包元数据也必须记录 `tracerite==1.1.3` 的直接约束。不得手工编辑 `uv.lock`。

### 镜像构建

Dockerfile 使用固定版本的 uv 创建 `/app/.venv`，再以锁文件同步全部依赖：

```text
pip3 install uv==0.8.16
uv sync --frozen --all-groups --all-extras
```

当设置 `NEXUS_PYTHON_REPOSITY` 时，同步命令必须把该地址作为 uv 的默认索引；未设置时使用 uv 默认索引。不得假设 uv 会读取 pip 的全局配置。

镜像增加：

```dockerfile
ENV PATH="/app/.venv/bin:$PATH"
```

这样现有 Supervisor 命令中的 `sanic` 和 `python` 都解析到 `/app/.venv/bin`，service 与四个 worker 不需要各自改写启动命令。

### 构建数据流

```text
pyproject.toml
      │ uv lock
      ▼
   uv.lock
      │ uv sync --frozen --all-groups --all-extras
      ▼
 /app/.venv
      │ PATH 优先
      ├──────────────▶ sanic server:app
      └──────────────▶ python /app/start_worker.py
```

生产镜像不再调用 `pip install -e` 重新求解应用依赖。

## 失败处理

- `pyproject.toml` 与 `uv.lock` 不一致：提交前的锁文件检查失败；不允许只改声明不更新锁文件。
- Nexus 缺少锁定制品：`uv sync` 失败并终止镜像构建，不回退到其他未批准版本。
- tracerite 或 Sanic 无法导入：镜像兼容性验证失败，不发布镜像。
- `/app/.venv/bin` 未进入 PATH：启动命令路径断言失败，避免运行到基础镜像的全局 Python。

## 测试设计

该变更属于构建配置，但仍采用红—绿验证：

1. RED：增加镜像依赖合同检查，当前 Dockerfile 因仍使用 `pip3 install -e` 且没有锁文件同步而失败。
2. GREEN：修改依赖声明、锁文件和 Dockerfile，使合同检查通过。
3. 锁文件一致性：执行 `uv lock --check`。
4. 环境解析：在同步环境中断言：
   - `importlib.metadata.version("sanic") == "24.6.0"`；
   - `importlib.metadata.version("tracerite") == "1.1.3"`；
   - `hasattr(tracerite.html, "style")`；
   - `import sanic` 成功。
5. 启动烟测：确认 `which sanic` 和 `which python` 均位于 `/app/.venv/bin`，并启动 service/worker 至完成模块导入，不连接真实生产 Redis 或 NATS。
6. 执行 Stargazer 最小质量门禁 `make lint`。

测试不得通过 monkeypatch 为 tracerite 补属性，也不得把 2.6.0 的失败隐藏为 Supervisor 重试。

## 发布与回滚

- 合并前完成一次无缓存镜像构建，证明没有复用旧的全局 site-packages。
- 发布后核对 service 和全部 worker 均进入稳定运行态，不再出现快速重启和 FATAL。
- 回滚使用上一已知可用的 Stargazer 镜像；不在运行中的容器内临时安装依赖。
- 若 Nexus 尚未同步 `tracerite==1.1.3` 或 uv 0.8.16，则构建应保持失败，先补齐制品后再发布。

## 验收标准

- 相同代码、锁文件和目标平台重复构建时，Python 包版本保持一致。
- 镜像内 Sanic 为 24.6.0、tracerite 为 1.1.3。
- `import sanic` 与 `tracerite.html.style` 检查通过。
- Supervisor 的 service 与 worker 均使用 `/app/.venv`。
- Nexus 和默认索引两种构建路径均使用锁文件，不再执行无锁依赖求解。
