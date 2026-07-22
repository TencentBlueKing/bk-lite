# Historical Superpowers change: 2026-07-21-provider-lazy-loading

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-21-provider-lazy-loading.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 避免无关 `manage.py` 命令启动时加载 provider，同时保证业务首次访问时安全、完整地初始化内置 provider 与 adapter 注册表。

**Architecture:** `SystemMgmtConfig.ready()` 仅保留必须启动注册的 NATS handler。Provider 与 capability adapter 注册表在 `get/list` 首次读取时通过 loader 懒加载；loader 使用显式模块清单、进程锁和失败回滚维护一致状态。

**Tech Stack:** Python 3.12、Django 4.2、pytest、Pydantic provider manifest。

## Global Constraints

- 仅修改 provider 加载链路和对应定向测试。
- 保留 `BUILTIN_PROVIDER_MODULES` 显式清单，不扫描包目录。
- 新行为必须先通过失败测试证明，再修改生产代码。
- 不影响 `apps.system_mgmt.nats` 的启动期注册。

---

### Task 1: Provider 注册表按需初始化

**Files:**
- Modify: `server/apps/system_mgmt/apps.py`
- Modify: `server/apps/system_mgmt/providers/registry.py`
- Modify: `server/apps/system_mgmt/providers/loader.py`
- Create: `server/apps/system_mgmt/tests/test_provider_loader.py`

**Interfaces:**
- Consumes: `load_builtin_providers(force: bool = False)` 与现有全局 provider/adapter registry。
- Produces: 注册表读取时自动初始化，以及不主动加载 provider 的 `HandleConfig.ready()`。

- [x] **Step 1: 编写并运行失败测试**

```python
def test_system_mgmt_ready_does_not_load_providers(monkeypatch): ...
def test_provider_registry_list_lazily_loads_builtin_providers(): ...
def test_adapter_registry_get_lazily_loads_builtin_providers(): ...
```

Run: `uv run pytest apps/system_mgmt/tests/test_provider_loader.py -q`
Expected: `ready()` 调用 loader 或清空注册表后 `list/get` 返回空导致 FAIL。

- [x] **Step 2: 实现并验证最小懒加载链路**

```python
def ensure_builtin_providers_loaded():
    from .loader import load_builtin_providers
    load_builtin_providers()
```

`ProviderRegistry.get/list` 与 `CapabilityAdapterRegistry.get` 在读取前调用该函数；loader 直接使用底层全局 registry，避免递归。

Run: `uv run pytest apps/system_mgmt/tests/test_provider_loader.py -q`
Expected: PASS。

### Task 2: 并发、失败回滚与真实命令验证

**Files:**
- Modify: `server/apps/system_mgmt/providers/loader.py`
- Modify: `server/apps/system_mgmt/tests/test_provider_loader.py`

**Interfaces:**
- Consumes: Task 1 的懒加载入口。
- Produces: `reset_builtin_providers()`、线程安全的双重检查加载、初始化失败后的空注册表状态。

- [x] **Step 1: 编写并运行并发、回滚与重置失败测试**

```python
def test_builtin_provider_loading_is_thread_safe(monkeypatch): ...
def test_builtin_provider_loading_rolls_back_all_registries_on_failure(monkeypatch): ...
def test_reset_builtin_providers_clears_loaded_state(): ...
```

Run: `uv run pytest apps/system_mgmt/tests/test_provider_loader.py -q`
Expected: 新增测试因缺少锁、回滚或重置入口而 FAIL。

- [x] **Step 2: 实现进程锁、失败回滚和重置**

```python
with _providers_load_lock:
    if _providers_loaded and not force:
        return
    try:
        _register_all_builtin_providers()
    except Exception:
        provider_registry.clear()
        capability_adapter_registry.clear()
        _providers_loaded = False
        raise
```

- [x] **Step 3: 运行定向回归与真实命令验证**

Run: `uv run pytest apps/system_mgmt/tests/test_provider_loader.py apps/system_mgmt/tests/test_provider_manifest.py apps/system_mgmt/tests/test_runtime_service.py -q`
Expected: PASS。

Run: `uv run python manage.py help --commands`
Expected: 命令成功；通过独立 shell 检查确认内置 provider manifest 模块未进入 `sys.modules`。
