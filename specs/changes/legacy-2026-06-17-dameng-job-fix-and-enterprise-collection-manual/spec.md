# Historical Superpowers change: 2026-06-17-dameng-job-fix-and-enterprise-collection-manual

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-17-dameng-job-fix-and-enterprise-collection-manual.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把商业版达梦数据库配置采集链路统一为 JOB/DB 类型（修复 3 处缺陷），并产出一份独立完整的商业版配置采集插件接入手册。

**Architecture:** 单一事实来源 = JOB。格式化插件改继承 `BaseDBCollectionPlugin`（注册到 `(DB,"dameng")`）；NodeParams 收敛为唯一的 SSH/job 版并搬入企业包；对象树/指标映射/Stargazer 脚本保持不变。手册以修复后的达梦为贯穿范例。

**Tech Stack:** Python 3.12 / Django 4.2 / pytest + pytest-django；CMDB 企业扩展机制（`apps.cmdb.extensions` 注册表 + `apps.cmdb.collect` 门面契约）。

**关联设计规格:** `docs/superpowers/specs/2026-06-17-dameng-job-fix-and-enterprise-collection-manual-design.md`

**全局约定:**
- 所有命令在 `server/` 目录下执行：`cd server && uv run pytest ...`。
- 提交信息结尾附:`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
- 当前分支 `claude/vigilant-edison-03def2`（非 master，可直接提交）。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `server/apps/cmdb_enterprise/collect/dameng.py` | 修改 | 达梦格式化插件(DB) + 达梦 SSH/job NodeParams（唯一定义） |
| `server/apps/cmdb/node_configs/databases/dameng.py` | 删除 | 旧的、重复的社区版 NodeParams（搬入企业包后删除） |
| `server/apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py` | 新建 | 插件注册槽位 + 对象树回归（无 DB/IO） |
| `server/apps/cmdb_enterprise/tests/test_dameng_node_params_service.py` | 新建 | NodeParams 唯一注册 + job 下发契约 |
| `server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md` | 新建 | 独立完整手册 |

---

## Task 1: 达梦格式化插件改注册到 DB 槽位

**Files:**
- Modify: `server/apps/cmdb_enterprise/collect/dameng.py`
- Test: `server/apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py`：

```python
"""达梦采集链路 — 注册槽位与对象树回归（无 DB/IO）。"""

from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.services.collect_object_tree import get_collect_obj_tree


def _dameng_registrations():
    return [r for r in CollectionPluginRegistry.get_registry_snapshot() if r["model_id"] == "dameng"]


def test_dameng_plugin_registered_under_db_not_protocol():
    task_types = {r["task_type"] for r in _dameng_registrations()}
    assert CollectPluginTypes.DB in task_types
    assert CollectPluginTypes.PROTOCOL not in task_types


def test_dameng_plugin_resolves_via_db_lookup():
    plugin_cls = get_collection_plugin(CollectPluginTypes.DB, "dameng")
    assert plugin_cls.supported_task_type == CollectPluginTypes.DB
    assert plugin_cls.metric_names == ("dameng_info_gauge",)


def test_dameng_field_mapping_has_core_fields():
    plugin_cls = get_collection_plugin(CollectPluginTypes.DB, "dameng")
    fm = plugin_cls.field_mapping
    for key in ("inst_name", "ip_addr", "port", "version", "dm_db_name"):
        assert key in fm


def test_dameng_in_collect_obj_tree_as_job():
    tree = get_collect_obj_tree()
    databases = next(node for node in tree if node.get("id") == "databases")
    dameng = next(child for child in databases["children"] if child.get("model_id") == "dameng")
    assert dameng["type"] == CollectDriverTypes.JOB
    assert dameng["task_type"] == CollectPluginTypes.DB
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py -v`
Expected: `test_dameng_plugin_registered_under_db_not_protocol` 与 `test_dameng_plugin_resolves_via_db_lookup` FAIL（当前达梦注册在 `(PROTOCOL,"dameng")`，DB 查找抛 `ValueError: Unsupported collection plugin`）。`test_dameng_in_collect_obj_tree_as_job` 应已 PASS（对象树本就是 JOB，作为回归保护）。

- [ ] **Step 3: 把插件基类改为 BaseDBCollectionPlugin**

将 `server/apps/cmdb_enterprise/collect/dameng.py` 整体替换为(本步仅改插件与 import，NodeParams 暂保留旧实现，Task 2 再收敛)：

```python
from apps.cmdb.collection.plugins.community.db.base import BaseDBCollectionPlugin
from apps.cmdb.node_configs.base import BaseNodeParams


class DaMengCollectionPlugin(BaseDBCollectionPlugin):
    supported_model_id = "dameng"
    metric_names = ("dameng_info_gauge",)
    field_mapping = {
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "dm_db_name": "dm_db_name",
        "dm_db_max_sessions": "dm_db_max_sessions",
        "dm_arch_mode": "dm_arch_mode",
        "dm_global_charset": "dm_global_charset",
        "dm_arch_dest": "dm_arch_dest",
        "dm_dba_roles": "dm_dba_roles",
        "dm_mode": "dm_mode",
        "dm_install_path": "dm_install_path",
        "dm_home_bash": "dm_home_bash",
        "dm_ctl_path": "dm_ctl_path",
        "dm_redo_log": "dm_redo_log",
        "dm_datafile": "dm_datafile",
        "dm_tablespace": "dm_tablespace",
        "operator": "operator",
        "bak_operator": "bak_operator",
        "inst_name": BaseDBCollectionPlugin.get_inst_name,
    }


class NodeParams(BaseNodeParams):
    supported_model_id = "dameng"
    plugin_name = "dameng_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        _password = f"PASSWORD_password_{self._instance_id}"
        credential_data = {
            "port": self.credential.get("port", 3306),
            "user": self.credential.get("user", ""),
            "password": "${" + _password + "}",
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        return {f"PASSWORD_password_{self._instance_id}": self.credential.get("password", "")}
```

> 说明:`BaseDBCollectionPlugin.get_inst_name` 与原 `ProtocolCollectMetrics.get_inst_name` 产物一致(均为 `f"{ip_addr}-{model_id}-{port}"`)，切换行为等价。原先的 `ProtocolCollectMetrics`、`BaseProtocolCollectionPlugin` import 已移除。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py -v`
Expected: 4 个用例全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git add server/apps/cmdb_enterprise/collect/dameng.py server/apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py
git commit -m "fix(cmdb): 达梦格式化插件改注册到 DB 槽位

DaMengCollectionPlugin 原继承 BaseProtocolCollectionPlugin 注册在 (PROTOCOL,dameng)，
但运行时按 task_type=DB 查找导致 Unsupported collection plugin。改继承 BaseDBCollectionPlugin。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 达梦 NodeParams 收敛为唯一 JOB 注册

**Files:**
- Modify: `server/apps/cmdb_enterprise/collect/dameng.py`
- Delete: `server/apps/cmdb/node_configs/databases/dameng.py`
- Test: `server/apps/cmdb_enterprise/tests/test_dameng_node_params_service.py`

- [ ] **Step 1: 写失败测试**

新建 `server/apps/cmdb_enterprise/tests/test_dameng_node_params_service.py`：

```python
"""达梦 NodeParams — 唯一注册 + JOB 下发契约。"""

from types import SimpleNamespace

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


def _all_subclasses(cls):
    result = set()
    for sub in cls.__subclasses__():
        result.add(sub)
        result |= _all_subclasses(sub)
    return result


def _dameng_node_param_classes():
    # 触发社区 + 企业 NodeParams 的自动注册(导入副作用)
    import apps.cmdb.node_configs  # noqa: F401

    return [c for c in _all_subclasses(BaseNodeParams) if getattr(c, "supported_model_id", None) == "dameng"]


def _make_instance():
    return SimpleNamespace(
        id=123,
        model_id="dameng",
        driver_type="job",
        decrypt_credentials={"username": "SYSDBA", "password": "pwd", "port": 5236},
        access_point=[{"id": "node-1"}],
        timeout=60,
        instances=[],
        ip_range="1.1.1.1",
        params={},
    )


def test_only_one_dameng_node_params_class():
    classes = _dameng_node_param_classes()
    assert len(classes) == 1, f"期望唯一达梦 NodeParams，实际: {[c.__name__ for c in classes]}"


def test_dameng_node_params_is_ssh_job():
    cls = NodeParamsFactory.get_params_class("dameng", "job")
    assert issubclass(cls, SSHNodeParamsMixin)


def test_dameng_node_params_emits_job_credential():
    cls = NodeParamsFactory.get_params_class("dameng", "job")
    node_params = cls(_make_instance())
    assert node_params.executor_type == "job"
    credential = node_params.set_credential()
    assert "node_id" in credential
    assert "password" in credential
    assert credential.get("port") != 3306
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_dameng_node_params_service.py -v`
Expected: `test_only_one_dameng_node_params_class` FAIL（当前存在两个达梦 NodeParams:社区 `DaMengNodeParams` + 企业 `NodeParams`）。其余用例可能因注册先后非确定而表现不稳，本步以第一个用例的 FAIL 为准。

- [ ] **Step 3: 把企业 dameng.py 的 NodeParams 换成唯一 SSH/job 版**

将 `server/apps/cmdb_enterprise/collect/dameng.py` 整体替换为最终版：

```python
from apps.cmdb.collection.plugins.community.db.base import BaseDBCollectionPlugin
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class DaMengCollectionPlugin(BaseDBCollectionPlugin):
    supported_model_id = "dameng"
    metric_names = ("dameng_info_gauge",)
    field_mapping = {
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "dm_db_name": "dm_db_name",
        "dm_db_max_sessions": "dm_db_max_sessions",
        "dm_arch_mode": "dm_arch_mode",
        "dm_global_charset": "dm_global_charset",
        "dm_arch_dest": "dm_arch_dest",
        "dm_dba_roles": "dm_dba_roles",
        "dm_mode": "dm_mode",
        "dm_install_path": "dm_install_path",
        "dm_home_bash": "dm_home_bash",
        "dm_ctl_path": "dm_ctl_path",
        "dm_redo_log": "dm_redo_log",
        "dm_datafile": "dm_datafile",
        "dm_tablespace": "dm_tablespace",
        "operator": "operator",
        "bak_operator": "bak_operator",
        "inst_name": BaseDBCollectionPlugin.get_inst_name,
    }


class DaMengNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "dameng"
    plugin_name = "dameng_info"
```

> 说明:`SSHNodeParamsMixin` 提供 `executor_type="job"`、SSH 凭据(`node_id`/`password` env/默认端口 22)与 `env_config`/`build_credentials_pool`，与原社区 `DaMengNodeParams` 完全一致，仅落位从社区包搬入企业包。`__init_subclass__` 自动把 `(dameng, None) → "dameng_info"` 写入 `PLUGIN_MAP`。

- [ ] **Step 4: 删除社区重复定义**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git rm server/apps/cmdb/node_configs/databases/dameng.py
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_dameng_node_params_service.py -v`
Expected: 3 个用例全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git add server/apps/cmdb_enterprise/collect/dameng.py server/apps/cmdb_enterprise/tests/test_dameng_node_params_service.py
git commit -m "fix(cmdb): 达梦 NodeParams 收敛为唯一 SSH/job 版

删除企业包内 executor_type=protocol、端口3306 的错误 NodeParams 与社区重复定义，
统一为 SSH/job 版并落位企业包，消除重复注册与 executor 类型冲突。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 全量回归验证（无新代码，仅验证）

**Files:** 无（验证步骤）

- [ ] **Step 1: 跑达梦相关用例**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py apps/cmdb_enterprise/tests/test_dameng_node_params_service.py -v`
Expected: 全部 PASS（7 个用例）。

- [ ] **Step 2: 跑企业域全量用例，确认未回归**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/ -v`
Expected: 全绿（含既有 custom_reporting / file_field 等用例）。若有失败，先排查是否为达梦改动引入(检查 NodeParams 自动注册、对象树合并)，修复后回到本步。

- [ ] **Step 3: 跑 cmdb 社区域采集相关用例，确认删除社区 dameng.py 无副作用**

Run: `cd server && uv run pytest apps/cmdb/tests/test_collect_object_tree.py apps/cmdb/tests/test_enterprise_extensions.py -v`
Expected: 全绿。

---

## Task 4: 编写商业版配置采集插件接入手册

**Files:**
- Create: `server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md`

这是文档交付物，非 TDD。所有代码片段必须与仓库**修复后**的真实文件一致（实现时打开对应文件核对后再粘贴）。

- [ ] **Step 1: 创建手册并写入 8 个章节**

创建 `server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md`，按下列章节逐节撰写。每节的"必含内容"即写作大纲，须落到具体文件与代码：

**第 1 章 概述与适用范围**
- 商业版 vs 社区版关系:社区版采集对象定义在 `apps/cmdb/constants/constants.py` 的 `COLLECT_OBJ_TREE`；商业版经 `cmdb_enterprise` 包以"扩展契约"增量注入，二者在运行时合并。
- 读者前置:了解 Django app、CMDB 采集任务模型 `CollectModels`（`apps/cmdb/models/collect_model.py`）。
- 适用范围:新增一个商业版采集对象（数据库/中间件/主机/协议类）的端到端接入。

**第 2 章 整体架构与四段调用链路**
- 四段:① 采集对象树(前端入口) → ② 节点管理下发(NodeParams) → ③ Stargazer 采集插件 → ④ 回流格式化入库。
- 关键文件锚点:
  - 任务调度:`apps/cmdb/tasks/celery_tasks.py::sync_collect_task`
  - JOB 执行:`apps/cmdb/collection/collect_tasks/job_collect.py`（`CollectPluginTypes.DB → collect_db → DBCollect`）
  - 格式化:`apps/cmdb/collection/collect_tasks/databases.py`（`get_collection_plugin(task.task_type, model_id)`）
  - 入库:`apps/cmdb/collection/metrics_cannula.py`、`apps/cmdb/collection/common.py`

**第 3 章 企业版扩展机制详解**
- 注册表:`apps/cmdb/extensions.py` 的 `registry`；门面契约:`apps/cmdb/collect/extensions.py` 的 `CollectEnterpriseExtension`（三件套字段 `collect_tree` / `plugin_packages` / `node_param_packages`）。
- 注册时机:`apps/cmdb_enterprise/apps.py::ready()` → `apps/cmdb_enterprise/registry_hooks.py` 调 `registry.register("collect", _collect_ext())` 并显式 `from apps.cmdb_enterprise.collect import dameng` 触发自注册。
- provider:`apps/cmdb_enterprise/collect/provider.py`（`plugin_packages=("apps.cmdb_enterprise.collect",)`、`node_param_packages` 同）。
- 加载:`apps/cmdb/collection/plugins/loader.py` 合并社区+企业插件包；`apps/cmdb/node_configs/__init__.py` 合并企业 NodeParams 包。
- 覆盖规则:`apps/cmdb/collection/plugins/registry.py` 的 `priority`（社区默认 vs 企业更高优先级覆盖）。

**第 4 章 接入步骤**
- 步骤 0 对象树增量:`apps/cmdb_enterprise/collect/tree.py` 的 `ENTERPRISE_COLLECT_OBJ_TREE`；字段含义 `id/model_id/name/task_type/type/tag/desc/encrypted_fields`；`task_type` 取 `CollectPluginTypes`(DB/HOST/MIDDLEWARE/PROTOCOL)、`type` 取 `CollectDriverTypes`(job/protocol)；合并逻辑 `apps/cmdb/services/collect_object_tree.py`（支持 children 为 dict 或 list）。
- 步骤 1 NodeParams:继承 `SSHNodeParamsMixin, BaseNodeParams`(job) 或裸 `BaseNodeParams`(protocol)；`supported_model_id` / `plugin_name`；凭据 `set_credential` / `env_config`；`host_field`；`__init_subclass__` 按 `(model_id, supported_driver_type)` 自动注册到 `BaseNodeParams._registry`。
- 步骤 2 指标映射:`apps/cmdb/collection/constants.py` 的 `DB_COLLECT_METRIC_MAP` / `MIDDLEWARE_METRIC_MAP` / `PROTOCOL_METRIC_MAP` / `HOST_COLLECT_METRIC`；命名约定 `plugin_name="xxx_info"` ↔ 指标 `xxx_info_gauge`。
- 步骤 3 回流格式化插件:继承正确基类(`BaseDBCollectionPlugin` / `BaseMiddlewareCollectionPlugin` / `BaseProtocolCollectionPlugin`)；**`supported_task_type` 必须与对象树 `type/task_type` 对应一致**；`metric_names`；`field_mapping` 三种用法(字符串直映射 / 元组(转换函数, 字段名) / 函数动态计算，可参考 `apps/cmdb/collection/plugins/community/db/es.py`)。
- 步骤 4 Stargazer 采集插件:`agents/stargazer/enterprise/plugins/inputs/{model}/plugin.yml`；`executors.job`(SSHPlugin + shell 脚本) 或 `executors.protocol`(Python collector 实现 `list_all_resources()`)；`PluginSourceResolver` 企业优先、OSS 回退。

**第 5 章 关键一致性约束（含达梦反面教材）**
- 三处 task_type/driver 必须一致:对象树 `type` ↔ 格式化插件 `supported_task_type` ↔ Stargazer `default_executor`。
- `plugin_name` ↔ 指标名 `{name}_info_gauge` 一致。
- `model_id` 全链路一致。
- 反面教材(达梦曾经的 bug):
  - 断点 A:插件继承 `BaseProtocolCollectionPlugin`(PROTOCOL) 但对象树声明 DB → `Unsupported collection plugin`。
  - 断点 B:NodeParams `executor_type=protocol` 但 Stargazer 仅有 job executor → 执行器解析失败。
  - 隐患 C:两个同 `model_id` NodeParams 重复注册、静默覆盖。

**第 6 章 完整范例:达梦端到端接入**
- 贴**修复后**的真实代码(打开文件核对):
  - 对象树:`apps/cmdb_enterprise/collect/tree.py`
  - 格式化插件 + NodeParams:`apps/cmdb_enterprise/collect/dameng.py`(`DaMengCollectionPlugin` + `DaMengNodeParams`)
  - 指标映射:`apps/cmdb/collection/constants.py` 的 `DB_COLLECT_METRIC_MAP["dameng"]`
  - Stargazer:`agents/stargazer/enterprise/plugins/inputs/dameng/plugin.yml`

**第 7 章 测试规范**
- pytest 分层(`server/docs/testing-guide.md`):`_pure`(注册槽位/对象树) / `_service`(NodeParams 下发契约)。
- 以本次新增的 `test_dameng_collect_chain_pure.py` / `test_dameng_node_params_service.py` 为样板，给出"注册校验 / 下发参数校验 / 对象树合并校验"三类断言写法。

**第 8 章 排错手册**
- `ValueError: Unsupported collection plugin: task_type=..., model_id=...` → 插件 `supported_task_type` 与对象树 `type` 不一致。
- Stargazer 执行器解析失败 → `executor_type` 与 `plugin.yml` 中 executor 不符。
- 下发配置被静默覆盖 → 同 `model_id` 存在多个 NodeParams。
- 采集到数据但实例为空/指标查不到 → `metric_names` 与实际指标名(`plugin_name` 派生)不匹配。

- [ ] **Step 2: 核对手册内代码片段与仓库一致**

逐一打开第 6 章引用的文件，确认粘贴的代码与磁盘内容逐字一致（尤其 `dameng.py` 必须是 Task 2 的最终版）。

- [ ] **Step 3: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git add server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md
git commit -m "docs(cmdb): 新增商业版配置采集插件接入手册

独立完整手册，覆盖企业版扩展机制与四段采集链路，以达梦为端到端范例。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 自检对照（规格覆盖）

- 断点 A 修复 → Task 1。
- 断点 B + 隐患 C 修复（NodeParams 收敛、删除重复、executor=job）→ Task 2。
- 对象树/指标映射保持不变 → Task 1 含对象树回归断言。
- TDD（先红后绿）→ Task 1/2 均含失败测试 → 实现 → 通过。
- 测试与回归 → Task 3。
- 商业版独立完整手册（8 章、达梦范例、落位 `cmdb_enterprise` 包）→ Task 4。
- YAGNI:不新增 protocol 路径、不改其它库、不重写社区指南。

## specs: 2026-06-17-dameng-job-fix-and-enterprise-collection-manual-design.md

- 日期:2026-06-17
- 作者:windyzhao（与 Claude 协作）
- 范围:CMDB 商业版（`cmdb_enterprise`）配置采集
- 关联方法论:`/systematic-debugging`（链路审计）、`/test-driven-development`（修复）

---

## 1. 背景与问题

商业版达梦数据库配置采集链路存在 **JOB / PROTOCOL 两套互相打架的定义**，导致采集任务运行时报错。经逐段审计（前端对象树 → 节点管理下发 → Stargazer 采集 → 回流格式化入库），确认链路不完整。

### 1.1 链路逐段现状

| 链路段 | 文件 | 状态 |
|---|---|---|
| ① 采集对象树 | `apps/cmdb_enterprise/collect/tree.py` | ✅ `task_type=DB`、`type=JOB` |
| ② 指标映射 | `apps/cmdb/collection/constants.py:143` `DB_COLLECT_METRIC_MAP["dameng"]=["dameng_info_gauge"]` | ✅ |
| ③ Stargazer 采集插件 | `agents/stargazer/enterprise/plugins/inputs/dameng/` | ✅ job 脚本，`default_executor: job`，仅定义 job executor |
| ④ NodeParams 下发 | 见断点 B / 隐患 C | ❌ |
| ⑤ 回流格式化插件 | 见断点 A | ❌ |

### 1.2 三处缺陷（根因）

**🔴 断点 A — 格式化插件注册槽位错误。**
`apps/cmdb_enterprise/collect/dameng.py` 的 `DaMengCollectionPlugin` 继承 `BaseProtocolCollectionPlugin`（`apps/cmdb/collection/plugins/community/protocol/base.py:7` 设 `supported_task_type = PROTOCOL`），故注册到 `(PROTOCOL, "dameng")`。但运行时 `JobCollect` 的 DB 路径（`collect_tasks/job_collect.py:21` → `DBCollect` → `collect_tasks/databases.py:11`）按 `get_collection_plugin(task.task_type=DB, "dameng")` 查找，registry（`plugins/registry.py:57`）找不到 `(DB,"dameng")` → 抛 `ValueError: Unsupported collection plugin`。
对照：所有 JOB 类数据库（db2/es/hbase/mongodb/tidb）均继承 `BaseDBCollectionPlugin`（`supported_task_type=DB`），仅 dameng 用错基类。

**🔴 断点 B — 下发的 executor_type 与 Stargazer 插件不匹配。**
`apps/cmdb_enterprise/collect/dameng.py` 的 `NodeParams` 继承裸 `BaseNodeParams`，`executor_type` 默认 `"protocol"`（`node_configs/base.py:62`），端口默认写成 `3306`（MySQL 端口，达梦应为 5236）。下发后 Stargazer 去找 dameng 的 `protocol` executor，但其 `plugin.yml` 只有 job executor → 执行器解析失败。

**🟠 隐患 C — 两个 dameng NodeParams 重复注册、互相覆盖。**
两个 `supported_model_id="dameng"` 的 NodeParams 都未设 `supported_driver_type`，都注册到同一 key `(dameng, None)`（`node_configs/base.py:39`），后导入者静默覆盖：
- `apps/cmdb/node_configs/databases/dameng.py:9` `DaMengNodeParams(SSHNodeParamsMixin)` → executor_type=**job**（正确）
- `apps/cmdb_enterprise/collect/dameng.py:32` `NodeParams` → executor_type=**protocol**（错误）

---

## 2. Part 1 — 达梦修复：统一为 JOB 类型

### 2.1 决策

**单一事实来源 = JOB。** 依据:已有可用的 job 采集脚本 + 对象树声明 JOB + DB 指标映射齐备。不引入 protocol 路径（避免给 Stargazer 重复造 Python collector）。

NodeParams 落位决策(已确认):**收敛进企业包** —— 把正确的 SSH/job NodeParams 移入 `cmdb_enterprise/collect/dameng.py`，删除 `community/node_configs/databases/dameng.py`，使达梦所有企业代码集中在企业包内，经 `node_param_packages` 自动发现。

### 2.2 改动清单

| # | 改动 | 文件 |
|---|---|---|
| 1 | `DaMengCollectionPlugin` 基类 `BaseProtocolCollectionPlugin` → `BaseDBCollectionPlugin`；`inst_name` 映射由 `ProtocolCollectMetrics.get_inst_name` 改为 `BaseDBCollectionPlugin.get_inst_name`（两者产物均为 `f"{ip_addr}-{model_id}-{port}"`，行为等价） | `apps/cmdb_enterprise/collect/dameng.py` |
| 2 | 删除该文件中 protocol 版 `NodeParams` 类 | 同上 |
| 3 | 在该文件中新增 SSH/job 版 NodeParams（继承 `SSHNodeParamsMixin, BaseNodeParams`，`supported_model_id="dameng"`、`plugin_name="dameng_info"`，复用 mixin 的 job 凭据/env/executor_type=job） | 同上 |
| 4 | 删除 `apps/cmdb/node_configs/databases/dameng.py` | community 包 |

修复后唯一注册：`(DB, "dameng")` 格式化插件；`(dameng, None)` job NodeParams。`NodeParamsFactory.get_params_class("dameng","job")` 命中回退键 `(dameng, None)`，返回 job 类。

### 2.3 不需要改动

- 对象树（已是 DB/JOB）。
- `DB_COLLECT_METRIC_MAP`（`dameng_info_gauge` 与 `plugin_name="dameng_info"` 约定一致，与 db2/es/tidb 同构）。
- Stargazer 插件（job 脚本可用）。
- 指标查询/入库管线（与其它 JOB 库共用）。

### 2.4 测试（TDD：先红后绿）

遵循 `server/docs/testing-guide.md` 分层，置于 `apps/cmdb_enterprise/tests/`：

- **`_pure`（无 DB/IO）**
  - `DaMengCollectionPlugin.supported_task_type == CollectPluginTypes.DB`
  - registry 快照中存在 `(DB,"dameng")`，且**不存在** `(PROTOCOL,"dameng")`
  - `metric_names == ("dameng_info_gauge",)`；`field_mapping` 含 `inst_name/ip_addr/port/version/dm_*` 关键字段
- **`_service`（mock 依赖）**
  - `NodeParamsFactory.get_params_class("dameng","job")` 返回 job 类，且实例 `executor_type == "job"`
  - `set_credential()` 产出 `node_id`/`password` env（不含 port=3306）
  - 全局仅一个 `supported_model_id=="dameng"` 的 NodeParams 注册（无重复覆盖）
- **对象树**
  - `get_collect_obj_tree()` 中 databases 下存在 dameng 且 `type == JOB`

验证命令:`cd server && uv run pytest apps/cmdb_enterprise/tests/ -v`。修复前相关用例应红，修复后全绿。

---

## 3. Part 2 — 商业版配置采集插件接入手册（独立完整手册）

### 3.1 定位与落位

- 类型:**独立完整手册**，不依赖社区版 `apps/cmdb/collection/CMDB配置采集插件开发指南.md`，从零覆盖企业版全链路。
- 路径(已确认):`server/apps/cmdb_enterprise/商业版配置采集插件接入手册.md`
- 贯穿范例:**修复后的达梦**（正确的 JOB/DB 接法）。

### 3.2 目录结构

1. **概述与适用范围** — 商业版↔社区版架构关系、扩展契约理念、读者前置要求
2. **整体架构与四段调用链路** — 对象树 → 节点下发 → Stargazer 采集 → 回流格式化入库（含链路图/时序）
3. **企业版扩展机制详解** — `apps/cmdb/extensions` 注册表、`apps/cmdb/collect/extensions.py` collect 门面契约、`cmdb_enterprise/registry_hooks.py` 注册时机；collect 契约三件套:`collect_tree` / `plugin_packages` / `node_param_packages`；社区↔企业插件 `priority` 覆盖规则
4. **接入步骤**
   - 步骤 0:采集对象树增量(`collect/tree.py` + `ENTERPRISE_COLLECT_OBJ_TREE`；`task_type`(DB/HOST/MIDDLEWARE/PROTOCOL…) 与 `type`(job/protocol) 取值；`encrypted_fields`；合并逻辑 `services/collect_object_tree.py`)
   - 步骤 1:NodeParams 下发(SSH/job vs protocol 两种；`set_credential`/`env_config`/`executor_type`/`host_field`；`plugin_name` 与指标命名约定 `{name}_info_gauge`；`__init_subclass__` 自动注册与 `(model_id, driver_type)` key)
   - 步骤 2:指标映射(`DB_COLLECT_METRIC_MAP` / `MIDDLEWARE_METRIC_MAP` / `PROTOCOL_METRIC_MAP` / `HOST_COLLECT_METRIC`)
   - 步骤 3:回流格式化插件(继承正确基类 —— `BaseDBCollectionPlugin`/`BaseMiddleware...`/`BaseProtocolCollectionPlugin`；**`supported_task_type` 必须与 tree.type 一致**；`field_mapping` 三种用法:字符串/元组/函数；`priority` 覆盖)
   - 步骤 4:Stargazer 采集插件(`enterprise/plugins/inputs/{model}/plugin.yml`；job executor + shell 脚本 或 protocol executor + Python collector；`PluginSourceResolver` 企业优先、OSS 回退)
5. **关键一致性约束** — task_type 三处必须一致:`tree.type` ↔ `plugin.supported_task_type` ↔ stargazer executor;`plugin_name` ↔ `{name}_info_gauge`;`model_id` 全链路一致。以达梦曾经的 bug（断点 A/B/C）作反面教材
6. **完整范例:达梦端到端接入** — 贴修复后的正确代码（对象树/NodeParams/指标/格式化插件/Stargazer 插件）
7. **测试规范** — pytest 分层、注册校验、节点下发参数校验、对象树合并校验（引用 Part 1 测试为样板）
8. **排错手册** — `Unsupported collection plugin`(task_type 错配)、executor 解析失败(executor_type 与 plugin.yml 不符)、重复注册静默覆盖、指标查不到(metric/plugin_name 不匹配)

---

## 4. 实施顺序

1. Part 1 修复（TDD：先写测试 → 改代码 → 转绿）
2. 跑 `apps/cmdb_enterprise/tests/` 验证全绿
3. Part 2 手册（以修复后的达梦真实代码为范例，确保文档与代码一致）

## 5. 验收标准

- `uv run pytest apps/cmdb_enterprise/tests/ -v` 全绿，含新增达梦注册/下发/对象树用例。
- registry 中 dameng 仅注册于 `(DB,"dameng")`；NodeParams 仅一处、executor_type=job。
- 手册落位且四段链路、扩展机制、一致性约束、达梦完整范例齐备，代码片段与仓库现状一致。

## 6. 超出范围（YAGNI）

- 不为达梦新增 protocol 执行路径 / Python collector。
- 不改造其它数据库插件。
- 不重写社区版开发指南。
- 达梦端口默认值(5236)仅在新 job NodeParams 中按 SSH 凭据语义处理，不引入 protocol 端口配置。
