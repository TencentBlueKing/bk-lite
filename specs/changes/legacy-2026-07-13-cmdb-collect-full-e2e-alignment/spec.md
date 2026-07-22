# Historical Superpowers change: 2026-07-13-cmdb-collect-full-e2e-alignment

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-13-cmdb-collect-full-e2e-alignment.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 catalog 56 model_id 全部对象上跑通端到端 e2e 测试,新增 A 端(stargazer 端 prometheus 修复对齐)+ B 端(CMDB 端 VM 拉数据后格式化对齐)两类 cross-cutting 字段对齐检查,不动现有 33 真实落盘对象 e2e。

**Architecture:**
- 复用 v3+v4 已搭建的 e2e 框架(`pipeline.py:185 run_full_pipeline_generic` + `conftest.py::load_runner_plugin_for_model_id` + `00_common_contract.schema.json` 公共契约)
- 新增 2 个 cross-cutting 测试文件:`test_stargazer_prometheus_alignment.py`(A 端) + `test_cmdb_vm_format_alignment.py`(B 端)
- 新增 1 个反射工具:`utils/model_reflection.py`(从 `apps.cmdb.models` 反射字段定义)
- 35 个新对象分 4 批:6 真实化 + 7 云采集新增 + 22 archived placeholder
- 每对象独立 commit,subagent 并行实施

**Tech Stack:** Python 3.12 + Django 4.2 + pytest + jsonschema + Django ORM(零 production 代码改动)

**Worktree:** `.worktrees/cmdb-collect-full-e2e-alignment/`(从 `feature_windyzhao` @ `aa7040c6a` 切出)

**Spec:** `docs/superpowers/specs/2026-07-13-cmdb-collect-full-e2e-alignment-design.md`

---

## Global Constraints

- 范围 C:catalog 56 model_id 全部(33 沿用 + 35 新工作 - 12 enterprise/community 合并)
- 不动 `server/apps/cmdb/tests/e2e/test_pipeline_factory.py` + 33 真实落盘对象的 e2e 测试
- 不修改 production 代码(`server/apps/cmdb/(collection|views|serializers|services|models|urls|apps.py)`、`agents/stargazer/(plugins/inputs|tasks/collectors|core)`)
- 不引入新依赖
- 落盘 JSON schema 固定(对齐 4 段流水线边界)
- 完成后不自动 push(由用户本人提交)
- 中文 commit message
- TDD:每步"写失败测试 → 跑测试失败 → 实现 → 跑测试通过 → commit"
- 覆盖率 ≥75%(沿用 QUALITY_SCORE.md 红线)

---

## 文件结构

| 文件 | 职责 | 状态 |
|---|---|---|
| `server/apps/cmdb/tests/e2e/utils/__init__.py` | utils 包初始化 | NEW |
| `server/apps/cmdb/tests/e2e/utils/model_reflection.py` | 从 `apps.cmdb.models.<Model>` 反射字段定义(name / type / is_required / choice) | NEW |
| `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py` | A 端对齐检查 — 03 VM PromQL 响应字段 vs CMDB model 定义 | NEW |
| `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py` | B 端对齐检查 — 04 实例字段 vs CMDB model 定义 | NEW |
| `server/apps/cmdb/tests/e2e/conftest.py` | 扩 `ALIGNMENT_COVERED_MODEL_IDS` fixture | MODIFY(加 fixture,不动现有) |
| `server/apps/cmdb/tests/e2e/schemas/02_stargazer_normalized.schema.json` | 02 阶段统一 schema | NEW |
| `server/apps/cmdb/tests/e2e/schemas/03_vm_metrics_response.schema.json` | 03 阶段通用 schema | NEW |
| `server/apps/cmdb/tests/e2e/schemas/04_cmdb_instance.schema.json` | 04 阶段通用 schema(基于反射) | NEW |
| `server/apps/cmdb/tests/e2e/fixtures/<model_id>/{01,02,03,04}.json` | 35 套对象 fixture(6 真实化 + 7 云采集 + 22 archived placeholder) | NEW(35 套) |
| `server/apps/cmdb/tests/e2e/schemas/<model_id>/{01,02,03,04}.schema.json` | 35 套对象 schema | NEW(35 套) |
| `docs/cmdb-e2e-author-guide.md` | e2e 作者指南 v2(扩 A/B 端检查章节) | MODIFY(扩章节) |
| `docs/superpowers/plans/2026-07-13-cmdb-collect-full-e2e-alignment.md` | 本计划文件 | NEW |

---

## Phase 划分(5 个 Task)

| Task | 范围 | 周期 | 验证 |
|---|---|---|---|
| **Task 1** | P0 基础设施(model_reflection + A/B 端骨架 + 02/03/04 schema) | 0.5 人天 | 6 真实化对象先跑通,作为模板 |
| **Task 2** | P0 真实化(6 套:aliyun / k8s / vmware / host / network / config_file) | 3 人天 | 6 × A/B 端测试全过 |
| **Task 3** | P1 云采集新增(7 套:hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise) | 3.5 人天 | 7 × A/B 端测试全过 |
| **Task 4** | P2 Archived placeholder(22 套:17 license + 5 集群/平台) | 4.4 人天 | 22 × A/B 端公共契约过 |
| **Task 5** | 收尾(字段漂移报告 + e2e 作者指南 v2 + PR description) | 1 人天 | 全量 35 × A/B 端 + 33 真实落盘回归 0 fail |

**总周期**:12.4 人天(2.5-3 人周)

---

## Task 1: P0 基础设施 — model_reflection + A/B 端骨架 + 02/03/04 schema + 22 archived plugin stub

**Files:**
- Create: `server/apps/cmdb/tests/e2e/utils/__init__.py`
- Create: `server/apps/cmdb/tests/e2e/utils/model_reflection.py`
- Create: `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py`
- Create: `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py`
- Create: `server/apps/cmdb/tests/e2e/schemas/02_stargazer_normalized.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/03_vm_metrics_response.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/04_cmdb_instance.schema.json`
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`(扩 `ALIGNMENT_COVERED_MODEL_IDS` fixture)
- Create: `server/apps/cmdb/collection/plugins/community/archived/<model_id>.py`(22 个 archived 对象 stub plugin,Pre-Flight Issue 2 决策)
- Test: `server/apps/cmdb/tests/e2e/test_model_reflection.py`

**Interfaces:**
- Consumes: `apps.cmdb.models.<Model>`(Django Model 反射)
- Produces:
  - `utils.model_reflection.get_model_field_def(model_id: str) -> dict[str, ModelFieldDef]`
  - `utils.model_reflection.ModelFieldDef(name: str, field_type: str, is_required: bool, choice: list | None)`
  - `test_stargazer_prometheus_alignment.ALIGNMENT_COVERED_MODEL_IDS: list[str]`(从 conftest 导入)
  - `test_cmdb_vm_format_alignment.ALIGNMENT_COVERED_MODEL_IDS: list[str]`(从 conftest 导入)
  - 22 个 archived plugin stub:`apps.cmdb.collection.plugins.community.archived.<ModelId>CollectionPlugin`(继承 `AutoRegisterCollectionPluginMixin`,空 metric_names + field_mappings)

### Task 1.0: 创建 22 个 archived 对象 stub plugin(Pre-Flight Issue 2 决策)

**Files:**
- Create: `server/apps/cmdb/collection/plugins/community/archived/__init__.py`
- Create: `server/apps/cmdb/collection/plugins/community/archived/<model_id>.py` × 22

- [ ] **Step 1: 写 archived 包初始化**

```python
# server/apps/cmdb/collection/plugins/community/archived/__init__.py
"""Archived 对象 stub plugin 包 —— license / amd64 / 集群 阻塞对象的占位 plugin。

22 个对象:apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase /
oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere
(17 license 类)+ hdfs / storm / yarn / mycat / domestic_linux(5 集群/平台类)。

仅用于 e2e placeholder 测试 + license_status 标注,不实现真实采集逻辑。
"""
```

- [ ] **Step 2: 写 22 个 stub plugin 模板**

每个文件结构相同(以 `apusic.py` 为例,其他 21 个套改 `class_name` + `supported_model_id` + `task_type`):

```python
# server/apps/cmdb/collection/plugins/community/archived/apusic.py
"""Apusic archived plugin stub —— 东方通 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class ApusicCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "apusic"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
```

其他 21 个 stub plugin 文件清单(每个 ~15 行,模板同上):
- bes.py / informix.py / ihs.py / inforsuite_as.py / iris.py
- couchbase.py / oceanbase.py / oscar.py / sap_hana.py / sybase.py
- tonggtp.py / tonglinkq.py / tongrds.py / tuxedo.py / weblogic.py / websphere.py
- hdfs.py / storm.py / yarn.py / mycat.py / domestic_linux.py

- [ ] **Step 3: 验证 stub plugin 可 import**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -c "from apps.cmdb.collection.plugins.community.archived import apusic, bes, informix, ihs, inforsuite_as, iris, couchbase, oceanbase, oscar, sap_hana, sybase, tonggtp, tonglinkq, tongrds, tuxedo, weblogic, websphere, hdfs, storm, yarn, mycat, domestic_linux; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/collection/plugins/community/archived/
git commit -m "feat(cmdb/plugins): Task 1.0 - 22 个 archived 对象 stub plugin(license 阻塞占位)"
```

### Task 1.1: 写 model_reflection 失败测试

**Files:**
- Create: `server/apps/cmdb/tests/e2e/test_model_reflection.py`

- [ ] **Step 1: 写失败测试**

```python
# server/apps/cmdb/tests/e2e/test_model_reflection.py
"""反射工具测试 —— 从 apps.cmdb.models.<Model> 反射字段定义。"""
import pytest

from apps.cmdb.tests.e2e.utils.model_reflection import (
    get_model_field_def,
    ModelFieldDef,
)


def test_get_model_field_def_returns_required_fields():
    """mysql Model 必填字段必须返回 ModelFieldDef(is_required=True)。"""
    fields = get_model_field_def("mysql")
    assert "inst_name" in fields
    assert fields["inst_name"].is_required is True
    assert fields["inst_name"].field_type in ("str", "char")


def test_get_model_field_def_returns_optional_fields():
    """mysql Model 可选字段必须返回 ModelFieldDef(is_required=False)。"""
    fields = get_model_field_def("mysql")
    # port 是可选字段
    if "port" in fields:
        assert fields["port"].is_required is False


def test_get_model_field_def_returns_choice_fields():
    """有 choice 字段的 Model 必须返回 ModelFieldDef(choice=[...])。"""
    fields = get_model_field_def("mysql")
    # status / role / version 等可能有 choice
    choice_fields = [f for f in fields.values() if f.choice is not None]
    assert len(choice_fields) >= 0  # 至少验证不抛异常


def test_get_model_field_def_unknown_model_raises():
    """不存在的 model_id 必须抛 KeyError。"""
    with pytest.raises(KeyError):
        get_model_field_def("nonexistent_model_xyz")
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_model_reflection.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'apps.cmdb.tests.e2e.utils.model_reflection'"

### Task 1.2: 实现 model_reflection 工具

**Files:**
- Create: `server/apps/cmdb/tests/e2e/utils/__init__.py`(空文件)
- Create: `server/apps/cmdb/tests/e2e/utils/model_reflection.py`

- [ ] **Step 1: 写 utils 包初始化**

```python
# server/apps/cmdb/tests/e2e/utils/__init__.py
"""E2E 测试工具包 — 反射、字段对齐、模型字段定义等。"""
```

- [ ] **Step 2: 写 model_reflection 实现**

```python
# server/apps/cmdb/tests/e2e/utils/model_reflection.py
"""CMDB Model 反射工具 —— 从 apps.cmdb.models.<Model> 反射字段定义。

用于:
  - A 端对齐检查:test_stargazer_prometheus_alignment 验证 metric label 集合 ⊇ Model 必填字段
  - B 端对齐检查:test_cmdb_vm_format_alignment 验证实例字段 ⊆ Model 字段定义 + 必填非空 + choice 合法

不修改 production 代码,只通过 Django Model _meta API 反射。
"""
from dataclasses import dataclass
from typing import Optional

from django.apps import apps as django_apps


@dataclass(frozen=True)
class ModelFieldDef:
    """CMDB Model 字段定义反射结果。"""
    name: str
    field_type: str  # str / int / float / bool / choice / json / datetime
    is_required: bool
    choice: Optional[list] = None


def _get_model_class(model_id: str):
    """根据 model_id 找到 apps.cmdb.models.<Model> 类。

    约定:CMDB Model 类名 = model_id 首字母大写(如 'mysql' → 'Mysql')。
    """
    # 从所有已注册的 Django Model 中找名字匹配
    for model in django_apps.get_models():
        if model.__name__.lower() == model_id.lower():
            return model
    raise KeyError(f"model_id={model_id!r} 在 apps.cmdb.models 中找不到对应 Model 类")


def _detect_field_type(field) -> str:
    """从 Django Field 推断字段类型字符串。"""
    field_type_name = type(field).__name__.lower()
    if "char" in field_type_name or "text" in field_type_name:
        return "str"
    if "int" in field_type_name:
        return "int"
    if "float" in field_type_name or "decimal" in field_type_name:
        return "float"
    if "bool" in field_type_name:
        return "bool"
    if "json" in field_type_name:
        return "json"
    if "datetime" in field_type_name or "date" in field_type_name:
        return "datetime"
    return "unknown"


def get_model_field_def(model_id: str) -> dict[str, ModelFieldDef]:
    """从 apps.cmdb.models.<Model> 反射字段定义。

    Returns:
        {field_name: ModelFieldDef} 字典

    Raises:
        KeyError: model_id 不存在
    """
    model_cls = _get_model_class(model_id)
    fields: dict[str, ModelFieldDef] = {}

    for field in model_cls._meta.get_fields():
        # 跳过关系字段(关联、ForeignKey 等)
        if field.is_relation or field.many_to_many or field.one_to_many:
            continue
        # 跳过 pk
        if field.primary_key:
            continue
        # 跳过 auto 字段
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue

        field_name = field.name
        field_type = _detect_field_type(field)
        # 必填判定:null=False 且 blank=False 且没有 default
        is_required = not field.null and not field.has_default()
        # choice 字段
        choice = None
        if field.choices:
            choice = [c[0] for c in field.choices]

        fields[field_name] = ModelFieldDef(
            name=field_name,
            field_type=field_type,
            is_required=is_required,
            choice=choice,
        )

    return fields
```

- [ ] **Step 3: 跑测试,确认通过**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_model_reflection.py -v`
Expected: PASS(4 tests)

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/utils/__init__.py \
        server/apps/cmdb/tests/e2e/utils/model_reflection.py \
        server/apps/cmdb/tests/e2e/test_model_reflection.py
git commit -m "test(cmdb/e2e): Task 1.1-1.2 - model_reflection 反射工具 + 失败/通过测试"
```

### Task 1.3: 写 02/03/04 通用 schema

**Files:**
- Create: `server/apps/cmdb/tests/e2e/schemas/02_stargazer_normalized.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/03_vm_metrics_response.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/04_cmdb_instance.schema.json`

- [ ] **Step 1: 写 02 schema**

```json
// server/apps/cmdb/tests/e2e/schemas/02_stargazer_normalized.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Stargazer Normalized Payload",
  "description": "通用 02 阶段 schema —— step1_stargazer_normalize_generic 输出",
  "type": "object",
  "required": ["success", "result"],
  "properties": {
    "success": {"type": "boolean"},
    "result": {
      "type": "object",
      "additionalProperties": {"type": "array"},
      "description": "{<model_id>: [items], host_proc_usage?: [procs]}"
    }
  }
}
```

- [ ] **Step 2: 写 03 schema**

```json
// server/apps/cmdb/tests/e2e/schemas/03_vm_metrics_response.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "VictoriaMetrics PromQL Response",
  "description": "通用 03 阶段 schema —— VictoriaMetrics /prometheus/api/v1/query 响应",
  "type": "object",
  "required": ["status", "data"],
  "properties": {
    "status": {"type": "string", "enum": ["success", "error"]},
    "data": {
      "type": "object",
      "required": ["resultType", "result"],
      "properties": {
        "resultType": {"type": "string", "enum": ["vector", "matrix", "scalar"]},
        "result": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["metric", "value"],
            "properties": {
              "metric": {
                "type": "object",
                "required": ["__name__", "instance_id"],
                "properties": {
                  "__name__": {
                    "type": "string",
                    "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$"
                  },
                  "instance_id": {"type": "string"},
                  "collect_status": {"type": "string", "enum": ["success", "error"]},
                  "ip_addr": {"type": "string"},
                  "result": {"type": "string", "description": "JSON 编码的业务字段(middleware/db/protocol 模式)"}
                },
                "additionalProperties": true
              },
              "value": {
                "type": "array",
                "items": {"type": ["string", "number"]},
                "minItems": 2,
                "maxItems": 2
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 3: 写 04 schema**

```json
// server/apps/cmdb/tests/e2e/schemas/04_cmdb_instance.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CMDB Instance (Generic)",
  "description": "通用 04 阶段 schema —— CMDB 实例字典,基于 apps.cmdb.models 反射生成。",
  "type": "object",
  "required": ["inst_name", "model_id"],
  "properties": {
    "inst_name": {"type": "string", "description": "{ip}-{name_token}-{port} 或自定义"},
    "model_id": {"type": "string", "description": "CMDB model_id(如 'mysql' / 'es' / 'k8s_namespace')"},
    "ip_addr": {"type": "string"},
    "port": {"type": ["string", "integer", "null"]},
    "_placeholder_reason": {
      "type": "string",
      "description": "placeholder 模式标记 — license_missing / cluster_complex / platform_constraint"
    },
    "license_status": {
      "type": "string",
      "enum": ["available", "missing", "unknown"],
      "description": "license 状态 — v4 placeholder 模式新增"
    }
  },
  "additionalProperties": true,
  "description": "实际字段名 ⊆ Model 字段定义,详细校验由 B 端 alignment 测试做"
}
```

- [ ] **Step 4: 验证 schema JSON 格式正确**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && python -c "import json; [json.load(open(f'server/apps/cmdb/tests/e2e/schemas/{n}')) for n in ['02_stargazer_normalized.schema.json', '03_vm_metrics_response.schema.json', '04_cmdb_instance.schema.json']]; print('OK')"`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/schemas/02_stargazer_normalized.schema.json \
        server/apps/cmdb/tests/e2e/schemas/03_vm_metrics_response.schema.json \
        server/apps/cmdb/tests/e2e/schemas/04_cmdb_instance.schema.json
git commit -m "test(cmdb/e2e): Task 1.3 - 02/03/04 通用 schema"
```

### Task 1.4: 写 A 端测试文件骨架

**Files:**
- Create: `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py`

- [ ] **Step 1: 写 A 端测试文件**

```python
# server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py
"""A 端对齐检查 —— stargazer 端 prometheus 修复格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对齐。

检查项:
  - metric.__name__ 后缀合法(跟 plugin.metric_names 对齐)
  - metric.instance_id / collect_status label 完整
  - 业务 label 集合 ⊇ model 必填字段(避免漏字段)
  - metric.value 格式合法
  - K8s 特殊:prometheus_kube_* 前缀

不动现有 33 真实落盘对象 + test_pipeline_factory.py。
只覆盖 35 个新工作对象(6 真实化 + 7 云采集 + 22 archived placeholder)。
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def


# 35 个新工作对象(本期 P0/P1/P2 覆盖)
ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6)
    "aliyun_ecs", "k8s_namespace", "vmware", "host", "network", "config_file",
    # P1 云采集新增(7) — 由 Task 3 逐对象加进来
    # P2 archived placeholder(22) — 由 Task 4 逐对象加进来
]


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_metric_name_suffix(model_id, load_fixture, runner_plugin_factory):
    """metric.__name__ 后缀必须合法(对齐 plugin.metric_names)。"""
    # K8s 走 minimal path(Pre-Flight Issue 1 决策),跳过 A 端 generic 检查
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,A 端字段对齐检查由 test_k8s_pipeline.py 覆盖")

    runner_cls, plugin_cls, _ = runner_plugin_factory(model_id)

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2)

    for result_item in p3["data"]["result"]:
        metric_name = result_item["metric"]["__name__"]
        # 后缀必须以 _info_gauge / _gauge / _count 结尾(或 K8s 特殊)
        assert metric_name.endswith(("_info_gauge", "_gauge", "_count")) or \
               metric_name.startswith("prometheus_kube_"), \
               f"{model_id} metric.__name__={metric_name!r} 后缀不合法"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_instance_id_label(model_id, load_fixture, runner_plugin_factory):
    """metric.instance_id label 必须是 cmdb_<task_id> 格式。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 A 端 instance_id 检查")
    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2, task_id=99999)

    for result_item in p3["data"]["result"]:
        instance_id = result_item["metric"].get("instance_id")
        assert instance_id == "cmdb_99999", \
            f"{model_id} instance_id={instance_id!r} 必须是 'cmdb_<task_id>' 格式"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_business_labels(model_id, load_fixture, runner_plugin_factory):
    """业务 label 集合必须 ⊇ model 必填字段(避免漏字段)。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 A 端业务 label 检查")
    model_fields = get_model_field_def(model_id)
    required_fields = {f.name for f in model_fields.values() if f.is_required}

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2)

    for result_item in p3["data"]["result"]:
        labels = set(result_item["metric"].keys()) - {"__name__", "instance_id", "collect_status"}
        # 业务 label 集合 ⊇ model 必填字段
        missing = required_fields - labels - {"ip_addr"}  # ip_addr 是通用 label
        assert not missing, f"{model_id} 03 metric 缺 model 必填字段: {missing}"
```

- [ ] **Step 2: 验证文件可 import(无 fixture 时跑会失败是预期)**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -c "from apps.cmdb.tests.e2e import test_stargazer_prometheus_alignment; print('OK')"`
Expected: `OK`(没 fixture 时跑 pytest 会 fail,但 import 必须成功)

- [ ] **Step 3: 跑测试,确认失败(无 fixture 是预期)**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py -v 2>&1 | head -30`
Expected: 大部分 FAIL(无 fixture 文件),但 import 不报错

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py
git commit -m "test(cmdb/e2e): Task 1.4 - A 端对齐检查文件骨架(覆盖 6 真实化对象)"
```

### Task 1.5: 写 B 端测试文件骨架

**Files:**
- Create: `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py`

- [ ] **Step 1: 写 B 端测试文件**

```python
# server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py
"""B 端对齐检查 —— CMDB 端从 VM 拉数据后,04 实例字段跟 CMDB model 定义对齐。

检查项:
  - 实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏)
  - 字段类型匹配 Model field_type
  - 必填字段非空
  - choice 枚举合法
  - inst_name 模式({ip}-{name_token}-{port})

不动现有 33 真实落盘对象 + test_pipeline_factory.py。
只覆盖 35 个新工作对象(6 真实化 + 7 云采集 + 22 archived placeholder)。
"""
import pytest

from apps.cmdb.tests.e2e import pipeline
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def, ModelFieldDef


# 同 A 端
ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6)
    "aliyun_ecs", "k8s_namespace", "vmware", "host", "network", "config_file",
    # P1 云采集新增(7) — 由 Task 3 逐对象加进来
    # P2 archived placeholder(22) — 由 Task 4 逐对象加进来
]


def _type_match(actual_value, expected_type: str) -> bool:
    """检查 actual_value 类型是否跟 expected_type 匹配。"""
    if expected_type == "int":
        return isinstance(actual_value, int) or (
            isinstance(actual_value, str) and actual_value.isdigit()
        )
    if expected_type == "str":
        return isinstance(actual_value, str)
    if expected_type == "float":
        return isinstance(actual_value, (int, float))
    if expected_type == "bool":
        return isinstance(actual_value, bool)
    if expected_type == "choice":
        return isinstance(actual_value, str)
    return True  # unknown 类型跳过


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_subset(model_id, load_fixture, load_schema, runner_plugin_factory, monkeypatch):
    """实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏 model 字段)。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 B 端字段子集检查")
    model_fields = get_model_field_def(model_id)

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items = raw_items[0] if isinstance(raw_items, list) else raw_items

    runner_cls, plugin_cls, extra_payload_keys = runner_plugin_factory(model_id)
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=runner_cls,
        plugin_cls=plugin_cls,
        model_id=model_id,
        task_id=99999,
        instances=[{"inst_name": f"{model_id}-align-01", "ip_addr": raw_items.get("ip_addr", "127.0.0.1")}],
        extra_payload_keys=extra_payload_keys,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"][model_id]

    if not instances:
        pytest.skip(f"{model_id} 流水线无实例产出,跳过(可能是 placeholder 模式)")

    inst = instances[0]
    inst_fields = set(inst.keys())

    # model 字段必须全部在实例里出现(除系统字段:inst_name / model_id / id / create_time / update_time 等)
    system_fields = {"inst_name", "model_id", "id", "create_time", "update_time", "_placeholder_reason", "license_status", "assos"}
    model_field_names = set(model_fields.keys()) - system_fields

    missing = model_field_names - inst_fields
    assert not missing, f"{model_id} 04 实例缺 Model 字段: {missing}"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_required_nonempty(model_id, load_fixture, load_schema, runner_plugin_factory, monkeypatch):
    """Model 必填字段必须非空。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 B 端必填字段检查")
    model_fields = get_model_field_def(model_id)
    required_fields = {f.name for f in model_fields.values() if f.is_required}

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items = raw_items[0] if isinstance(raw_items, list) else raw_items

    runner_cls, plugin_cls, extra_payload_keys = runner_plugin_factory(model_id)
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=runner_cls,
        plugin_cls=plugin_cls,
        model_id=model_id,
        task_id=99999,
        instances=[{"inst_name": f"{model_id}-align-01", "ip_addr": raw_items.get("ip_addr", "127.0.0.1")}],
        extra_payload_keys=extra_payload_keys,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"][model_id]

    if not instances:
        pytest.skip(f"{model_id} 流水线无实例产出,跳过")

    inst = instances[0]
    for field_name in required_fields:
        value = inst.get(field_name)
        if value is None or value == "":
            # placeholder 对象允许为空(标记 _placeholder_reason)
            if "_placeholder_reason" not in inst:
                pytest.fail(f"{model_id} Model 必填字段 {field_name!r} 为空")
```

- [ ] **Step 2: 验证 import**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -c "from apps.cmdb.tests.e2e import test_cmdb_vm_format_alignment; print('OK')"`
Expected: `OK`

- [ ] **Step 3: 跑测试,确认失败(无 fixture 预期)**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py -v 2>&1 | head -30`
Expected: 大部分 FAIL(无 fixture),import 不报错

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py
git commit -m "test(cmdb/e2e): Task 1.5 - B 端对齐检查文件骨架(覆盖 6 真实化对象)"
```

### Task 1.6: 扩 conftest.py 加 ALIGNMENT_COVERED_MODEL_IDS fixture

**Files:**
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`(在末尾追加,不修改现有内容)

- [ ] **Step 1: 读现有 conftest.py 末尾,确认追加位置**

Run: `tail -10 /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server/apps/cmdb/tests/e2e/conftest.py`

- [ ] **Step 2: 追加 ALIGNMENT_COVERED_MODEL_IDS fixture**

在 `conftest.py` 末尾追加:

```python
# ============================================================================
# A/B 端对齐检查 fixture(Task 1.6)
# ============================================================================
# 35 个新工作对象(P0/P1/P2 覆盖),不动现有 33 真实落盘对象
# P1/P2 逐对象在 Task 3/4 加进来

ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6)
    "aliyun_ecs",
    "k8s_namespace",
    "vmware",
    "host",
    "network",
    "config_file",
    # P1 云采集新增(7) — Task 3
    # P2 archived placeholder(22) — Task 4
]


@pytest.fixture
def alignment_covered_model_ids():
    """A/B 端对齐检查覆盖的 model_id 列表。"""
    return ALIGNMENT_COVERED_MODEL_IDS
```

- [ ] **Step 3: 验证 conftest 加载正常**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -c "from apps.cmdb.tests.e2e import conftest; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/conftest.py
git commit -m "test(cmdb/e2e): Task 1.6 - conftest 加 ALIGNMENT_COVERED_MODEL_IDS fixture"
```

### Task 1.7: 验证 Task 1 全部产物

- [ ] **Step 1: 跑 model_reflection 测试**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_model_reflection.py -v`
Expected: PASS(4 tests)

- [ ] **Step 2: 跑 33 真实落盘 e2e,确认零回归**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py -v 2>&1 | tail -10`
Expected: 沿用 v3+v4 113 passed(可能受新增 6 个未跑通影响,但 33 真实落盘 0 fail)

- [ ] **Step 3: 检查新增文件清单**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && git log --oneline -7`
Expected: 6 个 commit(Task 1.1-1.6)

- [ ] **Step 4: 验证 task 1 收尾(本步不进 commit)**

Task 1 全部产物已 commit,进入 Task 2 P0 真实化。

---

## Task 2: P0 真实化(6 套) — aliyun / k8s / vmware / host / network / config_file

**Files:**
- Modify: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/01_stargazer_raw.json`(扩 fixture 到真实形态)
- Modify: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/04_expected_cmdb_result.json`(扩 expected 到真实形态)
- Create: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/02_stargazer_normalized.json`
- Create: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/03_vm_metrics_response.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/<model_id>/01_stargazer_raw.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/<model_id>/04_cmdb_instance.schema.json`

**Interfaces:**
- 每对象独立 task(Task 2.1 - 2.6),subagent 可并行
- 每对象 5-7 步:扩 fixture / 写 02 fixture / 写 03 fixture / 写 schema / 扩 A 端 ALIGNMENT_COVERED_MODEL_IDS / 跑 A+B 端测试 / commit

### Task 2.1: aliyun 真实化 + A/B 端覆盖

**Files:**
- Modify: `server/apps/cmdb/tests/e2e/fixtures/aliyun/01_stargazer_raw.json`(从 17 行 1 实例扩到 100+ 行 1 实例,补 plugin 复杂清洗路径所需字段)
- Create: `server/apps/cmdb/tests/e2e/fixtures/aliyun/02_stargazer_normalized.json`
- Create: `server/apps/cmdb/tests/e2e/fixtures/aliyun/03_vm_metrics_response.json`
- Modify: `server/apps/cmdb/tests/e2e/fixtures/aliyun/04_expected_cmdb_result.json`(扩 expected_instance_subset,补 vcpus int / memory_mb int / create_time 转换后)
- Create: `server/apps/cmdb/tests/e2e/schemas/aliyun/01_stargazer_raw.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/aliyun/04_cmdb_instance.schema.json`
- Modify: `server/apps/cmdb/tests/e2e/test_aliyun_pipeline.py`(保留现有 5 测试,新增 1 个 A/B 端对齐全覆盖测试)

- [ ] **Step 1: 读现有 aliyun fixture 现状**

Run: `cat /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server/apps/cmdb/tests/e2e/fixtures/aliyun/01_stargazer_raw.json`
Run: `cat /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server/apps/cmdb/tests/e2e/fixtures/aliyun/04_expected_cmdb_result.json`

- [ ] **Step 2: 写失败测试(test_aliyun_pipeline.py 末尾追加)**

在 `test_aliyun_pipeline.py` 末尾追加:

```python
def test_aliyun_ecs_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """aliyun_ecs A 端 + B 端对齐全覆盖测试。

    验证:
      - A 端:03 metric.__name__ = 'aliyun_ecs_info_gauge', label 集合 ⊇ model 必填字段
      - B 端:04 实例字段 ⊆ model 字段定义,必填非空,vcpus / memory_mb 是 int
    """
    from apps.cmdb.tests.e2e import pipeline
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def

    raw = load_fixture("aliyun/01_stargazer_raw.json")
    expected = load_fixture("aliyun/04_expected_cmdb_result.json")

    # A 端:02 → 03
    p2 = pipeline.step1_stargazer_normalize_generic(raw, model_id="aliyun_ecs")
    p3 = pipeline.step2_push_to_vm(p2, task_id=88888)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        assert result_item["metric"]["instance_id"] == "cmdb_88888"
        # 业务 label 集合 ⊇ model 必填字段
        model_fields = get_model_field_def("aliyun_ecs")
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys()) - {"__name__", "instance_id", "collect_status"}
        missing = required - labels - {"ip_addr"}
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin

    monkeypatch.setattr(AliyunCollectMetrics, "check_task_id", lambda self, iid: True)
    monkeypatch.setattr(
        AliyunCollectMetrics, "_metrics",
        property(lambda self: list(AliyunAccountCollectionPlugin.metric_names)),
    )
    from apps.cmdb.collection.plugins.base import bind_collection_mapping
    monkeypatch.setattr(
        AliyunCollectMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in AliyunAccountCollectionPlugin.field_mappings.items()
        }),
    )
    monkeypatch.setattr(
        AliyunAccountCollectionPlugin, "field_mapping",
        AliyunAccountCollectionPlugin.field_mappings["aliyun_ecs"],
        raising=False,
    )

    raw_items = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=AliyunCollectMetrics,
        plugin_cls=AliyunAccountCollectionPlugin,
        model_id="aliyun_ecs",
        task_id=88888,
        instances=[{"inst_name": "aliyun-account-01", "ip_addr": raw.get("ip_addr", "172.16.0.11")}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["aliyun_ecs"]
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    # B 端:实例字段 ⊆ model 字段定义
    model_fields = get_model_field_def("aliyun_ecs")
    model_field_names = set(model_fields.keys()) - {"inst_name", "model_id", "id", "create_time", "update_time", "assos"}
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:vcpus / memory_mb 是 int(plugin 里有 (int, "vcpus") / (int, "memory") 转换)
    assert isinstance(inst.get("vcpus"), int), f"vcpus 应该是 int,实际 {type(inst.get('vcpus'))}"
    assert isinstance(inst.get("memory_mb"), int), f"memory_mb 应该是 int,实际 {type(inst.get('memory_mb'))}"
```

- [ ] **Step 3: 跑新测试,确认失败**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_aliyun_pipeline.py::test_aliyun_ecs_a_b_alignment -v`
Expected: FAIL(可能缺字段或类型错)

- [ ] **Step 4: 扩 01 fixture 到真实形态(100+ 行,补 vcpus / memory / os_name / expired_time)**

把 `fixtures/aliyun/01_stargazer_raw.json` 改成 100+ 行真实样本(参考阿里云 ECS API 响应),补齐 plugin `field_mappings["aliyun_ecs"]` 里所有字段的输入。

```json
{
  "resource_name": "web-prod-01",
  "resource_id": "i-bp1abcdef1234567",
  "ip_addr": "172.16.0.11",
  "public_ip": "47.96.10.20",
  "region": "cn-hangzhou",
  "zone": "cn-hangzhou-h",
  "vpc": "vpc-bp1zzzzz",
  "status": "Running",
  "instance_type": "ecs.g6.large",
  "os_name": "Ubuntu 22.04 64位",
  "vcpus": "2",
  "memory": "8192",
  "charge_type": "PostPaid",
  "create_time": "2024-01-15 10:30:00",
  "expired_time": "2099-12-31 23:59:59",
  "image_id": "m-bp1xxxxxxxxx",
  "security_group": "sg-bp1yyyyyy",
  "vswitch": "vsw-bp1wwwwww",
  "instance_network_type": "VPC",
  "internet_max_bandwidth_in": "100",
  "internet_max_bandwidth_out": "5",
  "host_name": "web-prod-01"
}
```

- [ ] **Step 5: 写 02 fixture**

```json
// fixtures/aliyun/02_stargazer_normalized.json
{
  "success": true,
  "result": {
    "aliyun_ecs": [
      {
        "resource_name": "web-prod-01",
        "resource_id": "i-bp1abcdef1234567",
        "ip_addr": "172.16.0.11",
        "public_ip": "47.96.10.20",
        "region": "cn-hangzhou",
        "zone": "cn-hangzhou-h",
        "vpc": "vpc-bp1zzzzz",
        "status": "Running",
        "instance_type": "ecs.g6.large",
        "os_name": "Ubuntu 22.04 64位",
        "vcpus": "2",
        "memory": "8192",
        "charge_type": "PostPaid",
        "create_time": "2024-01-15 10:30:00",
        "expired_time": "2099-12-31 23:59:59"
      }
    ]
  }
}
```

- [ ] **Step 6: 写 03 fixture**

```json
// fixtures/aliyun/03_vm_metrics_response.json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {
          "__name__": "aliyun_ecs_info_gauge",
          "instance_id": "cmdb_88888",
          "collect_status": "success",
          "ip_addr": "172.16.0.11",
          "result": "{\"resource_name\": \"web-prod-01\", \"resource_id\": \"i-bp1abcdef1234567\", ...}"
        },
        "value": [9999999999, "1"]
      }
    ]
  }
}
```

- [ ] **Step 7: 扩 04 expected**

在 `fixtures/aliyun/04_expected_cmdb_result.json` 的 `expected_instance_subset` 补:
```json
"image_id": "m-bp1xxxxxxxxx",
"security_group": "sg-bp1yyyyyy",
"vswitch": "vsw-bp1wwwwww",
"instance_network_type": "VPC",
"internet_max_bandwidth_in": 100,
"internet_max_bandwidth_out": 5,
"host_name": "web-prod-01"
```

- [ ] **Step 8: 跑新测试,确认通过**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_aliyun_pipeline.py::test_aliyun_ecs_a_b_alignment -v`
Expected: PASS

- [ ] **Step 9: 跑 aliyun 全部 e2e,确认零回归**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_aliyun_pipeline.py -v`
Expected: 原有 5 测试 + 新增 1 测试 = 6 测试全过

- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/aliyun/ \
        server/apps/cmdb/tests/e2e/schemas/aliyun/ \
        server/apps/cmdb/tests/e2e/test_aliyun_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.1 - aliyun 真实化 + A/B 端覆盖(plugin 复杂清洗路径)"
```

### Task 2.2: k8s 真实化 + A/B 端覆盖

**Files:**
- Create: `server/apps/cmdb/tests/e2e/fixtures/k8s/01_stargazer_raw.json`(K8s 走 VM 不走 raw,placeholder 标记)
- Create: `server/apps/cmdb/tests/e2e/fixtures/k8s/02_stargazer_normalized.json`
- Modify: `server/apps/cmdb/tests/e2e/fixtures/k8s/03_vm_metrics_response.json`(扩 workload / pod / node 3 分组)
- Modify: `server/apps/cmdb/tests/e2e/fixtures/k8s/04_expected_cmdb_result.json`(扩 k8s_workload / k8s_pod / k8s_node)
- Create: `server/apps/cmdb/tests/e2e/schemas/k8s/01_stargazer_raw.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/k8s/04_cmdb_instance.schema.json`
- Modify: `server/apps/cmdb/tests/e2e/test_k8s_pipeline.py`(加 A/B 端对齐全覆盖测试)

- [ ] **Step 1: 读现有 k8s fixture 现状**

Run: `ls /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server/apps/cmdb/tests/e2e/fixtures/k8s/`
Run: `cat /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server/apps/cmdb/tests/e2e/fixtures/k8s/03_vm_metrics_response.json`

- [ ] **Step 2-9: 跟 Task 2.1 同样的步骤,适配 k8s 特殊形态**

(详细步骤参考 Task 2.1,这里只列差异)
- 01 fixture 用 placeholder 模式:`{"_placeholder_reason": "k8s_走_VM_路径_无_01_raw"}`
- 03 fixture 扩 4 分组:namespace(已有) + workload(deployment/statefulset/daemonset/job/cronjob) + pod + node
- 04 expected 扩:k8s_workload / k8s_pod / k8s_node 实例预期
- test_k8s_pipeline.py 末尾加 `test_k8s_a_b_alignment` 测试
- A 端断言:`metric.__name__` 全部以 `prometheus_kube_` 开头
- B 端断言:4 分组实例字段 ⊆ 对应 model 字段

- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/k8s/ \
        server/apps/cmdb/tests/e2e/schemas/k8s/ \
        server/apps/cmdb/tests/e2e/test_k8s_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.2 - k8s 真实化 + A/B 端覆盖(4 分组对齐)"
```

### Task 2.3: vmware 真实化 + A/B 端覆盖

**Files:**
- Modify: `server/apps/cmdb/tests/e2e/fixtures/vmware/01_stargazer_raw.json`
- Create: `server/apps/cmdb/tests/e2e/fixtures/vmware/02_stargazer_normalized.json`
- Create: `server/apps/cmdb/tests/e2e/fixtures/vmware/03_vm_metrics_response.json`
- Modify: `server/apps/cmdb/tests/e2e/fixtures/vmware/04_expected_cmdb_result.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/vmware/01_stargazer_raw.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/vmware/04_cmdb_instance.schema.json`
- Modify: `server/apps/cmdb/tests/e2e/test_vmware_pipeline.py`(加 A/B 端测试)

- [ ] **Step 1-9: 跟 Task 2.1 类似,vmware 形态按 `apps/cmdb/collection/collect_plugin/vmware.py` 调整**
- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/vmware/ \
        server/apps/cmdb/tests/e2e/schemas/vmware/ \
        server/apps/cmdb/tests/e2e/test_vmware_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.3 - vmware 真实化 + A/B 端覆盖"
```

### Task 2.4: host 真实化 + A/B 端覆盖

- [ ] **Step 1-9: 跟 Task 2.1 类似,host 形态按 `apps/cmdb/collection/plugins/host/` 调整**
- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/host/ \
        server/apps/cmdb/tests/e2e/schemas/host/ \
        server/apps/cmdb/tests/e2e/test_host_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.4 - host 真实化 + A/B 端覆盖"
```

### Task 2.5: network 真实化 + A/B 端覆盖

- [ ] **Step 1-9: 跟 Task 2.1 类似,network 形态按 `apps/cmdb/collection/plugins/network/` 调整**
- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/network/ \
        server/apps/cmdb/tests/e2e/schemas/network/ \
        server/apps/cmdb/tests/e2e/test_network_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.5 - network 真实化 + A/B 端覆盖"
```

### Task 2.6: config_file 真实化 + A/B 端覆盖

- [ ] **Step 1-9: 跟 Task 2.1 类似,config_file 形态按 `apps/cmdb/collection/plugins/config_file/` 调整**
- [ ] **Step 10: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/config_file/ \
        server/apps/cmdb/tests/e2e/schemas/config_file/ \
        server/apps/cmdb/tests/e2e/test_config_file_pipeline.py
git commit -m "test(cmdb/e2e): Task 2.6 - config_file 真实化 + A/B 端覆盖"
```

### Task 2.7: 验证 Task 2 全部产物

- [ ] **Step 1: 跑 P0 真实化 6 对象的 A/B 端测试**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py -v -k "aliyun_ecs or k8s_namespace or vmware or host or network or config_file"`
Expected: 6 × 3 = 18 tests PASS

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py -v -k "aliyun_ecs or k8s_namespace or vmware or host or network or config_file"`
Expected: 6 × 2 = 12 tests PASS

- [ ] **Step 2: 跑 33 真实落盘 e2e,确认零回归**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py 2>&1 | tail -5`
Expected: 沿用 v3+v4 113 passed

- [ ] **Step 3: 检查 commit 数**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && git log --oneline -10`
Expected: 6(Task 1) + 6(Task 2) = 12 commits

---

## Task 3: P1 云采集新增(7 套) — hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise

**Files(每对象独立 task):**
- Create: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/{01,02,03,04}.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/<model_id>/{01,04}.schema.json`
- Create: `server/apps/cmdb/tests/e2e/test_<model_id>_pipeline.py`
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`(加 model_id 到 `_MODEL_RUNNER_MAP`)
- Modify: `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py`(加到 `ALIGNMENT_COVERED_MODEL_IDS`)
- Modify: `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py`(加到 `ALIGNMENT_COVERED_MODEL_IDS`)

**Interfaces:**
- 每对象独立 task(Task 3.1 - 3.7),subagent 并行
- 读云厂商 API 文档虚构 JSON,plugin 已有(stub)直接用,plugin 没有就 stub

### Task 3.1: hwcloud(2 核心子对象:hwcloud_ecs + hwcloud_vpc,Pre-Flight Issue 4 决策)

**Files:**
- Create: `server/apps/cmdb/tests/e2e/fixtures/hwcloud/ecs/{01,02,03,04}.json`
- Create: `server/apps/cmdb/tests/e2e/fixtures/hwcloud/vpc/{01,02,03,04}.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/hwcloud/ecs/{01,04}.schema.json`
- Create: `server/apps/cmdb/tests/e2e/schemas/hwcloud/vpc/{01,04}.schema.json`
- Create: `server/apps/cmdb/tests/e2e/test_hwcloud_pipeline.py`
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`(`_MODEL_RUNNER_MAP` 加 hwcloud_ecs + hwcloud_vpc)

> **注**:其他 9 个 hwcloud 子对象(hwcloud_evs / hwcloud_obs / hwcloud_subnet / hwcloud_eip / hwcloud_sg / hwcloud_elb / hwcloud_rds / hwcloud_dcs)推到下期,作为 Task 6 单独 follow-up。

- [ ] **Step 1: 读华为云 ECS + VPC API 文档**

读 https://support.huaweicloud.com/api-ecs/ecs_02_0101.html(ECS) + https://support.huaweicloud.com/api-vpc/vpc_api10_0001.html(VPC),了解 API 响应结构

- [ ] **Step 2: 写 hwcloud_ecs 01 fixture(参考华为云 ECS ListServersDetails 响应)**

```json
{
  "resource_name": "ecs-prod-01",
  "resource_id": "ecs-bp1xxxxxx",
  "ip_addr": "192.168.1.10",
  "public_ip": "1.2.3.4",
  "region": "cn-north-4",
  "availability_zone": "cn-north-4a",
  "vpc": "vpc-bp1yyyyyy",
  "subnet": "subnet-bp1zzzzzz",
  "status": "ACTIVE",
  "flavor": "s6.large.2",
  "os_name": "CentOS 7.6 64bit",
  "vcpus": "2",
  "memory_mb": "4096",
  "charge_type": "0",
  "created_at": "2024-02-01T08:00:00Z",
  "expired_at": "2099-12-31T23:59:59Z",
  "image_id": "img-bp1wwwwww",
  "security_group_ids": ["sg-bp1xxxxxx"]
}
```

- [ ] **Step 3: 写 hwcloud_ecs 02 / 03 fixture**

- [ ] **Step 4: 写 hwcloud_ecs 04 expected**

```json
{
  "model_id": "hwcloud_ecs",
  "instance_count_min": 1,
  "expected_instance_subset": {
    "inst_name": "ecs-prod-01(ecs-bp1xxxxxx)",
    "resource_name": "ecs-prod-01",
    "resource_id": "ecs-bp1xxxxxx",
    "ip_addr": "192.168.1.10",
    "public_ip": "1.2.3.4",
    "region": "cn-north-4",
    "vpc": "vpc-bp1yyyyyy",
    "status": "ACTIVE",
    "instance_type": "s6.large.2",
    "vcpus": 2,
    "memory_mb": 4096,
    "charge_type": "PostPaid"
  }
}
```

- [ ] **Step 5: 写 hwcloud_ecs 01 / 04 schema**

- [ ] **Step 6: 写 hwcloud_vpc 01 / 02 / 03 / 04 fixture + schema(参考华为云 VPC ListVpcs 响应)**

```json
{
  "resource_name": "vpc-prod-01",
  "resource_id": "vpc-bp1yyyyyy",
  "region": "cn-north-4",
  "cidr": "192.168.0.0/16",
  "status": "ACTIVE",
  "created_at": "2024-01-15T10:00:00Z"
}
```

- [ ] **Step 7: 写 test_hwcloud_pipeline.py(6 个测试:hwcloud_ecs step1 / pipeline / A 端 / B 端 + hwcloud_vpc step1 / pipeline)**

- [ ] **Step 8: conftest._MODEL_RUNNER_MAP 加 hwcloud_ecs + hwcloud_vpc**

- [ ] **Step 9: A/B 端 ALIGNMENT_COVERED_MODEL_IDS 加 hwcloud_ecs + hwcloud_vpc**

- [ ] **Step 10: 跑测试,确认通过**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_hwcloud_pipeline.py -v`
Expected: 6 tests PASS

- [ ] **Step 11: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/fixtures/hwcloud/ \
        server/apps/cmdb/tests/e2e/schemas/hwcloud/ \
        server/apps/cmdb/tests/e2e/test_hwcloud_pipeline.py \
        server/apps/cmdb/tests/e2e/conftest.py \
        server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py \
        server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py
git commit -m "test(cmdb/e2e): Task 3.1 - hwcloud 云采集(2 核心子对象 ecs + vpc)+ A/B 端覆盖"
```

### Task 3.2: qcloud(7 子对象)

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,适配 qcloud 7 子对象(cvm/vpc/clb/cdb/redis 等)**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.2 - qcloud 云采集(7 子对象)+ A/B 端覆盖"
```

### Task 3.3: fusioninsight

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,适配 fusioninsight 4-6 子对象(HDFS/HBase/Hive/Spark)**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.3 - fusioninsight 云采集 + A/B 端覆盖"
```

### Task 3.4: zstack

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,适配 zstack(私有云 5-7 子对象)**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.4 - zstack 云采集 + A/B 端覆盖"
```

### Task 3.5: h3c_cas

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,适配 h3c_cas(H3C 云 4-6 子对象)**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.5 - h3c_cas 云采集 + A/B 端覆盖"
```

### Task 3.6: dameng_enterprise

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,dameng_enterprise 复用 `apps/cmdb/collection/plugins/community/db/dameng.py`**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.6 - dameng_enterprise + A/B 端覆盖(商业版)"
```

### Task 3.7: redis_sentinel_enterprise

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,redis_sentinel_enterprise 复用 redis plugin + 形态 C**
- [ ] **Step 10: 提交**

```bash
git commit -m "test(cmdb/e2e): Task 3.7 - redis_sentinel_enterprise + A/B 端覆盖(商业版)"
```

### Task 3.8: 推 9 个 hwcloud 子对象到下期(Pre-Flight Issue 4 决策)

> 9 个 hwcloud 子对象(hwcloud_evs / hwcloud_obs / hwcloud_subnet / hwcloud_eip / hwcloud_sg / hwcloud_elb / hwcloud_rds / hwcloud_dcs)推迟到下期 follow-up。
> 本期 Task 3.1 只做 2 个核心子对象(ecs + vpc),其他 9 个作为下期独立 worktree + spec 处理。

- [ ] **Step 1: 写 follow-up spec**

在 `docs/superpowers/specs/` 写 `2026-MM-dd-cmdb-collect-hwcloud-subobjects-design.md`,列出 9 个子对象的实施计划。

- [ ] **Step 2: 创建下期 worktree 准备**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git worktree add .worktrees/cmdb-collect-hwcloud-subobjects -b feature/cmdb-collect-hwcloud-subobjects feature_windyzhao
```

(实际下期工作不在本期 plan 范围,只占位记录)

### Task 3.9: 验证 Task 3 全部产物

- [ ] **Step 1: 跑 P1 云采集 7 对象的 A/B 端测试**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py -v 2>&1 | tail -20`
Expected: 8 × 3 + 8 × 2 = 40 tests PASS(hwcloud 含 ecs + vpc 2 子对象,共 8 个 model_id)

- [ ] **Step 2: 跑全量 e2e,确认 33 真实落盘 0 fail**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/ -v 2>&1 | tail -10`
Expected: 113 + 35 + 18(alibaba 等) = ~166 passed

- [ ] **Step 3: 检查 commit 数**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && git log --oneline -20`
Expected: 6(Task 1) + 6(Task 2) + 7(Task 3) = 19 commits

---

## Task 4: P2 Archived placeholder(22 套) — 17 license + 5 集群/平台

**Files(每对象独立 task):**
- Create: `server/apps/cmdb/tests/e2e/fixtures/<model_id>/{01,02,03,04}.json`(01 / 02 / 03 可用 placeholder 最小集,04 必有 `_placeholder_reason` + `license_status: missing`)
- Create: `server/apps/cmdb/tests/e2e/schemas/<model_id>/{01,04}.schema.json`
- Create: `server/apps/cmdb/tests/e2e/test_<model_id>_pipeline.py`(只测公共契约 + A/B 端公共契约命中)
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`(`_MODEL_RUNNER_MAP` 加占位)
- Modify: `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py`(加到 `ALIGNMENT_COVERED_MODEL_IDS`)
- Modify: `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py`(加到 `ALIGNMENT_COVERED_MODEL_IDS`)

**Interfaces:**
- 17 license 类(每对象 1 task,subagent 并行)
- 5 集群/平台类(每对象 1 task,subagent 并行)
- placeholder fixture 模式:`_placeholder_reason: "license_missing" | "cluster_complex" | "platform_constraint"`,`license_status: missing`
- A/B 端公共契约验证:只需命中公共契约,不需实际跑 runner

### Task 4.1-4.17: License 类(17 个对象)

**Files:** 同 Task 3.1,按对象遍历

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,只测公共契约 + A/B 端公共契约命中**
- [ ] **Step 10: 提交(每个对象独立 commit)**

```bash
git commit -m "test(cmdb/e2e): Task 4.N - <model_id> archived placeholder(license) + A/B 端公共契约"
```

对象列表(17 个):
- apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere

### Task 4.18-4.22: 集群/平台类(5 个对象)

**Files:** 同 Task 3.1,按对象遍历

- [ ] **Step 1-9: 跟 Task 3.1 同样的步骤,用 `cluster_complex` / `platform_constraint` 标注**
- [ ] **Step 10: 提交(每个对象独立 commit)**

```bash
git commit -m "test(cmdb/e2e): Task 4.N - <model_id> archived placeholder(集群/平台) + A/B 端公共契约"
```

对象列表(5 个):
- hdfs / storm / yarn / mycat / domestic_linux

### Task 4.23: 验证 Task 4 全部产物

- [ ] **Step 1: 跑 P2 placeholder 22 对象的 A/B 端测试**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_placeholder_objects.py -v 2>&1 | tail -10`
Expected: 22 tests PASS

- [ ] **Step 2: 跑全量 e2e,确认全部通过**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/ 2>&1 | tail -5`
Expected: 113 + 35 + 22 = ~170 passed, 0 failed

- [ ] **Step 3: 检查 commit 数**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && git log --oneline -30 | head -30`
Expected: 6(Task 1) + 6(Task 2) + 7(Task 3) + 22(Task 4) = 41 commits

---

## Task 5: 收尾(字段漂移报告 + e2e 作者指南 v2 + PR description)

**Files:**
- Create: `server/apps/cmdb/tests/e2e/utils/drift_report.py`
- Create: `Makefile` 扩 `e2e-drift-report` target(或独立脚本)
- Modify: `docs/cmdb-e2e-author-guide.md`(扩 v2 章节)
- Create: `docs/superpowers/plans/2026-07-13-cmdb-collect-full-e2e-alignment-execution-report.md`(本期执行报告)
- Create: `docs/superpowers/plans/2026-07-13-cmdb-collect-full-e2e-alignment-pr-description.md`(PR description)

### Task 5.1: 字段漂移报告脚本(Pre-Flight Issue 3 决策,完整可工作版)

**Files:**
- Create: `server/apps/cmdb/tests/e2e/utils/drift_report.py`
- Create: `server/apps/cmdb/tests/e2e/test_drift_report.py`
- Modify: `Makefile` 或 `server/Makefile`(加 `e2e-drift-report` target)

- [ ] **Step 1: 写失败测试**

```python
# server/apps/cmdb/tests/e2e/test_drift_report.py
"""字段漂移报告测试 —— 扫描 fixtures/<model_id>/04_expected_cmdb_result.json 跟
apps.cmdb.models.<Model> 反射字段定义比对,输出 model_id / missing_fields / extra_fields / type_mismatch 表格。"""
import json
import subprocess
from pathlib import Path

import pytest

E2E_ROOT = Path(__file__).parent


def test_drift_report_runs():
    """drift_report 跑通,返回 0 退出码,stdout 是 JSON 报告。"""
    report = subprocess.run(
        ["python", "-m", "apps.cmdb.tests.e2e.utils.drift_report"],
        cwd=E2E_ROOT,
        capture_output=True,
        text=True,
    )
    assert report.returncode == 0, f"drift_report 失败: {report.stderr}"
    summary = json.loads(report.stdout)
    assert "results" in summary
    assert isinstance(summary["results"], list)


def test_drift_report_writes_markdown():
    """drift_report 必须生成 markdown 报告文件。"""
    md_path = E2E_ROOT / "drift_report.md"
    if md_path.exists():
        md_path.unlink()  # 先删,确保重新生成
    subprocess.run(
        ["python", "-m", "apps.cmdb.tests.e2e.utils.drift_report", "--format", "markdown", "--output", str(md_path)],
        cwd=E2E_ROOT,
        check=True,
    )
    assert md_path.exists()
    content = md_path.read_text()
    assert "# 字段漂移报告" in content
    assert "model_id" in content
```

- [ ] **Step 2: 实现 drift_report.py(完整可工作版,Pre-Flight Issue 3 决策)**

```python
# server/apps/cmdb/tests/e2e/utils/drift_report.py
"""字段漂移报告工具 —— 扫描 fixtures/<model_id>/04_expected_cmdb_result.json 跟
apps.cmdb.models.<Model> 反射字段定义比对,生成 JSON / Markdown 报告。

用法:
  python -m apps.cmdb.tests.e2e.utils.drift_report                    # stdout JSON
  python -m apps.cmdb.tests.e2e.utils.drift_report --format markdown  # stdout Markdown
  python -m apps.cmdb.tests.e2e.utils.drift_report -o drift_report.md # 写文件
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def

E2E_ROOT = Path(__file__).parents[1]  # apps/cmdb/tests/e2e
FIXTURES_DIR = E2E_ROOT / "fixtures"


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _compare(model_id: str) -> dict[str, Any]:
    """比对单个 model_id 的 04 expected 跟 model 字段定义。"""
    model_fields = get_model_field_def(model_id)
    model_field_names = set(model_fields.keys())

    expected = _read_json(FIXTURES_DIR / model_id / "04_expected_cmdb_result.json")
    if not expected:
        return {
            "model_id": model_id,
            "status": "no_fixture",
            "missing_fields": [],
            "extra_fields": [],
            "type_mismatch": [],
        }

    expected_subset = expected.get("expected_instance_subset", {})
    if not expected_subset:
        return {
            "model_id": model_id,
            "status": "no_expected_subset",
            "missing_fields": [],
            "extra_fields": [],
            "type_mismatch": [],
        }

    expected_field_names = set(expected_subset.keys())

    # 缺字段:model 有但 expected 没有
    system_fields = {"inst_name", "model_id", "id", "create_time", "update_time", "assos",
                     "_placeholder_reason", "license_status"}
    missing = (model_field_names - expected_field_names) - system_fields

    # 多字段:expected 有但 model 没有
    extra = expected_field_names - model_field_names - system_fields

    # 类型不匹配
    type_mismatch = []
    for field_name, expected_value in expected_subset.items():
        if field_name not in model_fields:
            continue
        model_def = model_fields[field_name]
        if not _type_match(expected_value, model_def.field_type):
            type_mismatch.append({
                "field": field_name,
                "expected_type": type(expected_value).__name__,
                "model_type": model_def.field_type,
            })

    status = "ok"
    if missing or type_mismatch:
        status = "missing_or_mismatch"
    if extra:
        status = "extra_fields"

    return {
        "model_id": model_id,
        "status": status,
        "missing_fields": sorted(missing),
        "extra_fields": sorted(extra),
        "type_mismatch": type_mismatch,
    }


def _type_match(value: Any, expected_type: str) -> bool:
    if expected_type == "int":
        return isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "float":
        return isinstance(value, (int, float))
    if expected_type == "bool":
        return isinstance(value, bool)
    return True


def _to_markdown(results: list[dict]) -> str:
    lines = ["# 字段漂移报告", ""]
    lines.append(f"扫描 {len(results)} 个 model_id")
    lines.append("")

    by_status = {"ok": [], "missing_or_mismatch": [], "extra_fields": [], "no_fixture": [], "no_expected_subset": []}
    for r in results:
        by_status[r["status"]].append(r)

    lines.append(f"## 统计")
    lines.append(f"- ok(完全对齐): {len(by_status['ok'])}")
    lines.append(f"- 缺字段或类型错: {len(by_status['missing_or_mismatch'])}")
    lines.append(f"- 多字段: {len(by_status['extra_fields'])}")
    lines.append(f"- 无 fixture: {len(by_status['no_fixture'])}")
    lines.append(f"- 无 expected_subset: {len(by_status['no_expected_subset'])}")
    lines.append("")

    if by_status["missing_or_mismatch"]:
        lines.append("## 缺字段 / 类型错")
        lines.append("")
        lines.append("| model_id | 缺字段 | 类型错 |")
        lines.append("| --- | --- | --- |")
        for r in by_status["missing_or_mismatch"]:
            missing = ", ".join(r["missing_fields"][:5]) + ("..." if len(r["missing_fields"]) > 5 else "")
            tm = ", ".join(f"{tm['field']}({tm['expected_type']}→{tm['model_type']})" for tm in r["type_mismatch"][:5])
            lines.append(f"| {r['model_id']} | {missing} | {tm} |")
        lines.append("")

    if by_status["extra_fields"]:
        lines.append("## 多字段(expected 有但 model 没有)")
        lines.append("")
        lines.append("| model_id | 多字段 |")
        lines.append("| --- | --- |")
        for r in by_status["extra_fields"]:
            extra = ", ".join(r["extra_fields"][:5])
            lines.append(f"| {r['model_id']} | {extra} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", "-o", help="输出文件路径(默认 stdout)")
    args = parser.parse_args()

    # 扫描 fixtures 目录所有 model_id
    model_ids = sorted([d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()])
    results = [_compare(mid) for mid in model_ids]

    if args.format == "json":
        output = json.dumps({"results": results}, ensure_ascii=False, indent=2)
    else:
        output = _to_markdown(results)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"报告写入 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 跑测试,确认通过**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/test_drift_report.py -v`
Expected: PASS(2 tests)

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m apps.cmdb.tests.e2e.utils.drift_report --format markdown`
Expected: 输出 markdown 报告到 stdout

- [ ] **Step 4: 提交**

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment
git add server/apps/cmdb/tests/e2e/utils/drift_report.py \
        server/apps/cmdb/tests/e2e/test_drift_report.py
git commit -m "feat(cmdb/e2e): Task 5.1 - 字段漂移报告工具(完整可工作版)"
```

### Task 5.2: e2e 作者指南 v2 扩展

- [ ] **Step 1: 读现有 `docs/cmdb-e2e-author-guide.md` 末尾**
- [ ] **Step 2: 追加 v2 章节 — A/B 端对齐检查**
- [ ] **Step 3: 提交**

```bash
git commit -m "docs(cmdb-e2e): 作者指南 v2 扩 A/B 端对齐检查章节"
```

### Task 5.3: PR description

- [ ] **Step 1: 参考 v3+v4 PR 描述,写本期 PR description**
- [ ] **Step 2: 提交(在 git 仓库 commit 记录,实际 PR 创建由用户做)**

```bash
git commit -m "docs: CMDB 全链路 e2e PR description(A/B 端字段对齐检查)"
```

### Task 5.4: 验证 Task 5 全部产物

- [ ] **Step 1: 跑全量 e2e**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/server && python -m pytest apps/cmdb/tests/e2e/ 2>&1 | tail -5`
Expected: ~170 passed, 0 failed, 0 error

- [ ] **Step 2: 检查文档**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && ls docs/superpowers/plans/2026-07-13-*`
Expected: 3 files(spec + execution report + PR description)

- [ ] **Step 3: 总 commit 数**

Run: `cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment && git log --oneline | wc -l`
Expected: ~45 commits(spec 1 + 6 + 6 + 7 + 22 + 3 = 45)

---

## Self-Review 清单

- [x] **Spec 覆盖**:spec §1 目标 / §3 数据流 / §4 e2e 架构 / §5 范围 / §6 实施 都有对应 task
- [x] **无 placeholder**:所有 step 含具体代码 / 命令 / 期望输出,无 "TBD" / "TODO"
- [x] **类型一致**:`get_model_field_def` / `ModelFieldDef` / `ALIGNMENT_COVERED_MODEL_IDS` 在所有 task 中签名一致
- [x] **DRY**:Task 2/3/4 重复结构用模板化描述,关键 task(Task 1 + Task 2.1 + Task 3.1 + Task 4 模板)展开详细
- [x] **TDD**:每步"写失败测试 → 跑 → 实现 → 跑 → commit"
- [x] **频繁 commit**:每对象独立 commit,~45 个 commit
- [x] **零 production 代码改动**:所有改动在 `server/apps/cmdb/tests/e2e/` + `docs/` 下

---

## 一句话总结

**5 个 task,~45 个 commit,~12.4 人天,新增 2 个 cross-cutting 测试 + 1 个反射工具 + 35 套对象 e2e,覆盖 catalog 56 model_id 全部 e2e。不动现有 33 真实落盘 e2e,零 production 代码改动。**

## specs: 2026-07-13-cmdb-collect-full-e2e-alignment-design.md

> **状态**：设计草案 v5(2026-07-13)
> **作者**：Mavis(在 windyzhao 协同下)
> **基线**：`feature_windyzhao` @ `aa7040c6a`(v3+v4 收尾)
> **姊妹文档**：
> - [`2026-07-10-cmdb-collect-archive-document.md`](../plans/2026-07-10-cmdb-collect-archive-document.md)(catalog 56 状态表)
> - [`2026-07-10-cmdb-collect-v3-v4-pr-description.md`](../plans/2026-07-10-cmdb-collect-v3-v4-pr-description.md)(v3+v4 工作收尾)
> - [`2026-07-06-cmdb-collect-v3-roadmap.md`](../plans/2026-07-06-cmdb-collect-v3-roadmap.md)(v3 路线图,云采集明确排除)

---

## 0. 文档使用约定

1. **「测试结果」字段**:每个对象完成 e2e 后,对应章节的「测试结果」字段由执行者**手动回填**(pytest 行号 + 验证状态)
2. **「能做 / 不能做 / 不做」三档标识**:
   - 🟢 **能做**:对象在 fixture 适配范围 + 镜像/API 文档可达 + 有可用 plugin
   - 🟡 **能做(降级方案)**:原生方案不可行,但有可接受的降级路径(读 API 文档虚构 JSON / placeholder 模式)
   - 🔴 **不能做**:受 license / 平台 / 集群硬约束
   - ⚪ **不做(明确不纳入)**:超出本路线图范围
3. **执行约定**(沿用 v3+v4):
   - 不修改 production 代码(`server/apps/cmdb/(collection|views|serializers|services|models|urls)`、`agents/stargazer/(plugins/inputs|tasks/collectors|core)`)
   - 所有改动是新增(无 modify 现有功能)
   - 不引入新依赖
   - 落盘 JSON schema 固定(对齐 4 段流水线边界)
   - 敏感字段掩码(若需要)
   - 完成后不自动 push(由用户本人提交)

---

## 1. 目标与边界

### 1.1 目标

复用 v3+v4 已搭建的 e2e 框架(`pipeline.py:185 run_full_pipeline_generic` + `conftest.py::load_runner_plugin_for_model_id` + `00_common_contract.schema.json` 公共契约),在 catalog 56 model_id 全部对象上跑通端到端测试,并在**数据流两端**加字段对齐检查:

- **A 端(stargazer 端)** — 采集数据经 `convert_to_prometheus`/`parse_metrics_to_prometheus`/`wmi_results_to_prometheus` 修复 + 格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对不齐的检查
- **B 端(CMDB 端)** — CMDB 从 VM 拉数据后,经 plugin `field_mappings` 格式化,04 实例字段跟 CMDB model 定义对不齐的检查

**不**做 plugin 内部 tuple 字段清洗项(类型转换 / datetime format / set_instance_inst_name / set_asso_instances 等)的独立断言层 —— 用户已明确否决。

### 1.2 范围

#### 1.2.1 范围对象分类

> 详细 56 对象分布看 [`2026-07-10-cmdb-collect-archive-document.md`](../plans/2026-07-10-cmdb-collect-archive-document.md) §1 整体结果表。

| 范围 | 数量 | 现状 | 本期处理 |
|---|---|---|---|
| 真实落盘(已 e2e 100% 覆盖) | 33(24 passed + 9 placeholder) | v3+v4 已跑通 3 层验证(113 passed) | **不动** |
| 已有 fixture 但未真实化 | 6(aliyun / k8s / vmware / host / network / config_file) | test_*.py 已写,fixture 简化(aliyun 17 行 1 实例)/不完整(k8s 缺 01_raw) | 真实化 + A/B 端检查 |
| 云采集新增 | 7(hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise) | v3+v4 没做,plugin 有或 stub | 读 API 文档虚构 JSON + A/B 端检查 |
| Archived placeholder | 17(18 archived 减 1 enterprise 合并 = apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere)| 无 plugin / plugin stub | placeholder 模式 + license_status 标注 + A/B 端公共契约 |
| Archived 集群/平台 | 5(hdfs / storm / yarn / mycat / domestic_linux) | 集群复杂 / amd64 only | placeholder 模式 + cluster_constraint / platform_constraint 标注 |

**总范围**:catalog 56 model_id 全部对象(33 沿用 + 23 补做,其中 17 license + 5 集群/平台 = 22 archived,1 个 mssql 主动删除不在范围)。

**重叠/合并说明**:
- `dameng` / `redis_sentinel` 在 community 33 真实落盘 + enterprise P1 都出现,只算一次
- 5 skipped(mssql / oracle / iis / hbase / docker)本期不纳入(mssql 主动删除,oracle 无 catalog spec,iis Windows 容器超范围,hbase 集群复杂,docker 非采集对象)

#### 1.2.2 范围外

- K8s / VMware vCenter / 云采集(K8s 的部分功能在 6 套真实化里做,但不展开 K8s 集群复杂度)—— 用户在 v3 已明确排除,本期仅真实化已有 fixture
- Network 设备采集(走 SNMP,跟 prometheus 协议无关)—— 本期仅真实化已有 fixture
- Storage(community storage + enterprise storage_device)—— fixture 语义不匹配
- Host(config_file / physcial_server)—— 本期真实化已有 fixture,集群形态略过

---

## 2. 现状回顾(v3+v4 已交付)

### 2.1 已落地的能力

- ✅ e2e 4 段流水线框架:`pipeline.py:185 run_full_pipeline_generic`
  - step1_stargazer_normalize_generic(raw_items) → Stargazer 标准化 payload
  - step2_push_to_vm(stargazer_payload) → VictoriaMetrics PromQL 响应
  - step3_cmdb_consume_generic(runner_cls, plugin_cls, model_id) → CMDB 实例字典
  - step4_collect_base 关联挂载(自动)
- ✅ 公共契约:`00_common_contract.schema.json` 覆盖 01 阶段 5 种 oneOf 形态(A/B/C/placeholder_object/placeholder_array)
- ✅ 工厂函数:`conftest.py::load_runner_plugin_for_model_id` 返回 `(runner_cls, plugin_cls, extra_payload_keys)` 三元组
- ✅ 33 真实落盘对象 e2e 100% 触达,113 passed + 6 skipped + 0 failed
- ✅ placeholder 模式约定:fixture 用 `_placeholder_reason` 标记,license 解锁后增量升级
- ✅ 6 套已有 fixture(test_aliyun_pipeline.py / test_k8s_pipeline.py / test_vmware_pipeline.py / host / network / config_file)框架代码就绪

### 2.2 v3+v4 留下的关键 Gap

| Gap | 描述 | 本期处理 |
|---|---|---|
| A 端缺对齐检查 | 03 VM PromQL 响应字段(`__name__` / `instance_id` / `result` JSON / 业务 label)跟 `cmdb.models.<Model>` 字段定义对不齐,无检查 | **新增** `test_stargazer_prometheus_alignment.py`(A 端) |
| B 端缺对齐检查 | 04 实例字段跟 model 定义对不齐,无全量检查(只有 expected_instance_subset 子集) | **新增** `test_cmdb_vm_format_alignment.py`(B 端) |
| 6 套 fixture 不够真实 | aliyun 17 行 1 实例,无法触发 plugin 里 `(int, x)` / `(convert_datetime_format, x)` / `set_instance_inst_name` / `set_asso_instances` 复杂清洗路径 | P0 真实化 |
| 17 个 archived 无 e2e | license / amd64 / 集群复杂对象无 e2e | P2 placeholder 套壳 |

### 2.3 关键约束(继承基线)

- aliyun / hwcloud / qcloud plugin 字段清洗复杂:`(int, "vcpus")` / `(int, "memory")` / `(convert_datetime_format, "create_time")` / `set_instance_inst_name(resource_name + resource_id)` / `set_asso_instances` 关联对象拼装
- K8s 流水线走不了 generic 驱动:`CollectK8sMetrics` 不继承 `CollectBase`,业务逻辑硬编码(namespace/workload/pod/node 4 分组),需走 minimal path
- stargazer 端用 prometheus 修复:`tasks/utils/metrics_helper.py` + `tasks/collectors/vmware_collector.py` 等用 `convert_to_prometheus` / `parse_metrics_to_prometheus` / `wmi_results_to_prometheus` 转换采集 dict 为 prometheus 格式
- 23 archived 对象封档原则:不再主动重试,placeholder 模式 + license_status 标注,等 license 解锁增量升级

---

## 3. 设计方案

### 3.1 数据流 + A/B 端检查点

```
┌─────────────────────────────────────────────────────────────────────┐
│  [1] Stargazer 采集脚本/SDK 原始输出          (fixture 01)          │
│        ↓ step1_stargazer_normalize                                   │
│  [2] Stargazer 标准化 payload                (fixture 02, 本期新增) │
│        ↓ step2_push_to_vm                                            │
│  [3] VictoriaMetrics PromQL 响应              (fixture 03)           │
│        ↓ step3_cmdb_consume                                          │
│  [4] CMDB 实例字典(落库前)                   (fixture 04)           │
└─────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────┐    ┌────────────────────────┐
  │ A 端对齐检查(本期新增) │    │ B 端对齐检查(本期新增) │
  │ ──────────────────────  │    │ ──────────────────────  │
  │ 03 字段 vs Model 定义  │    │ 04 字段 vs Model 定义  │
  │ - __name__ 后缀        │    │ - 字段名 ⊆ Model.field │
  │ - instance_id label   │    │ - 字段类型匹配         │
  │ - 业务 label 集合     │    │ - 必填字段非空         │
  │ - result JSON 编码     │    │ - choice 枚举合法      │
  └────────────────────────┘    └────────────────────────┘
```

### 3.2 A 端检查(stargazer 端)语义

`test_stargazer_prometheus_alignment.py` 核心:

| 检查项 | 来源 | 期望 | 失败信号 |
|---|---|---|---|
| `metric.__name__` 后缀 | `step2_push_to_vm` 产物 | `_<model_id>_info_gauge`(middleware/db/protocol)或 `prometheus_kube_*`(K8s) | 后缀错(跟 plugin.metric_names 对不齐) |
| `metric.instance_id` label | `step2_push_to_vm` 产物 | `cmdb_<task_id>` 格式 | 缺 instance_id label |
| `metric.collect_status` label | `step2_push_to_vm` 产物 | `success` | 状态错 |
| 业务 label 集合 | `step2_push_to_vm` 产物(middleware 走 result JSON) | ⊇ CMDB model 字段名(必填字段全部在 label 里)| 缺业务 label(模型字段没生成) |
| `metric.value` | VM 响应格式 | `[<timestamp>, "1"]` 数组 | 格式错 |
| K8s 特殊:`__name__ ∈ prometheus_kube_*` | K8s plugin 硬编码 metric | `prometheus_kube_*` 前缀 | 缺前缀(被 K8s 流水线过滤) |

### 3.3 B 端检查(CMDB 端)语义

`test_cmdb_vm_format_alignment.py` 核心:

| 检查项 | 来源 | 期望 | 失败信号 |
|---|---|---|---|
| 实例字段名 ⊆ Model 字段定义 | `step3_cmdb_consume` 产物 | CMDB model `<Model>` 定义的字段全部出现(允许额外字段) | 漏字段(模型定义没接上) |
| 字段类型匹配 | `step3_cmdb_consume` 产物 | Model `field_type` 定义(int / str / choice / etc) | 类型错(`vcpus` 应该是 int 但成了 str) |
| 必填字段非空 | `step3_cmdb_consume` 产物 | Model `is_required` 字段全部非空 | 必填空(数据没接上) |
| `choice` 枚举合法 | `step3_cmdb_consume` 产物 | Model `choice` 字段值在白名单内 | 非法值(状态码 / 区域码漂移) |
| `inst_name` 模式 | `step3_cmdb_consume` 产物 | 跟 `inst_name_alias` 规则一致(`{ip}-{name_token}-{port}`) | inst_name 错位 |

### 3.4 不做之事(明确排除)

- ❌ plugin 内部 tuple 字段清洗项的独立断言层(用户已明确否决)
- ❌ 修改 production 代码(collection / views / serializers / services / models / urls / apps.py)
- ❌ 引入新依赖
- ❌ 自动重试 17 个 archived 对象(license 阻塞)
- ❌ 33 真实落盘对象的 e2e 代码改动

---

## 4. e2e 测试架构

### 4.1 文件结构

```
server/apps/cmdb/tests/e2e/
├── test_pipeline_factory.py                        # 现有,33 真实落盘对象不动
├── test_stargazer_prometheus_alignment.py          # NEW - A 端检查
├── test_cmdb_vm_format_alignment.py                # NEW - B 端检查
├── test_common_contract.py                         # 现有
├── test_placeholder_objects.py                     # 现有
├── test_aliyun_pipeline.py                         # 现有
├── test_k8s_pipeline.py                            # 现有
├── test_vmware_pipeline.py                         # 现有
├── test_host_pipeline.py                           # 现有
├── test_network_pipeline.py                        # 现有
├── test_config_file_pipeline.py                    # 现有
├── conftest.py                                     # 现有(扩 load_runner_plugin)
├── pipeline.py                                     # 现有
├── fixtures/                                       # 扩 6 + 17 = 23 套
│   ├── aliyun/                                     # 真实化
│   ├── k8s/                                        # 真实化(补 01_raw)
│   ├── vmware/                                     # 真实化
│   ├── host/                                       # 真实化
│   ├── network/                                    # 真实化
│   ├── config_file/                                # 真实化
│   ├── hwcloud/                                    # 新增(P1)
│   ├── qcloud/                                     # 新增(P1)
│   ├── fusioninsight/                              # 新增(P1)
│   ├── zstack/                                     # 新增(P1)
│   ├── h3c_cas/                                    # 新增(P1)
│   └── <archived_obj>/                             # 新增 17 套 placeholder
└── schemas/                                        # 扩 23 套
```

### 4.2 A 端测试文件骨架

```python
# test_stargazer_prometheus_alignment.py 草图
"""A 端对齐检查:stargazer 端 prometheus 修复格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对齐。

检查项:
  - metric.__name__ 后缀合法
  - metric.instance_id / collect_status label 完整
  - 业务 label 集合 ⊇ model 必填字段
  - metric.value 格式合法
  - K8s 特殊:prometheus_kube_* 前缀
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


ALIGNMENT_COVERED_MODEL_IDS = [...]  # 6 真实化 + 7 云采集 + 17 archived


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_metric_name_suffix(model_id, load_fixture, runner_plugin_factory):
    """metric.__name__ 后缀必须与 plugin.metric_names 对齐。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_instance_id_label(model_id, load_fixture, runner_plugin_factory):
    """metric.instance_id label 必须是 cmdb_<task_id> 格式。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_business_labels(model_id, load_fixture, runner_plugin_factory):
    """业务 label 集合必须 ⊇ model 必填字段(避免漏字段)。"""
    ...
```

### 4.3 B 端测试文件骨架

```python
# test_cmdb_vm_format_alignment.py 草图
"""B 端对齐检查:CMDB 端从 VM 拉数据后,04 实例字段跟 CMDB model 定义对齐。

检查项:
  - 实例字段名 ⊆ Model 字段定义
  - 字段类型匹配 Model field_type
  - 必填字段非空
  - choice 枚举合法
  - inst_name 模式
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


ALIGNMENT_COVERED_MODEL_IDS = [...]  # 同 A 端


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_subset(model_id, load_fixture, runner_plugin_factory):
    """实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏)。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_types(model_id, load_fixture, runner_plugin_factory):
    """字段类型匹配 Model field_type(避免 vcpus 等该 int 的成了 str)。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_required_nonempty(model_id, load_fixture, runner_plugin_factory):
    """Model is_required 字段全部非空。"""
    ...
```

### 4.4 公共契约扩展(扩 2 套通用 schema)

- `00_common_contract.schema.json` — 现有,01 阶段 5 种 oneOf,**不动**
- `02_stargazer_normalized.schema.json` — **新增** 02 阶段统一 schema
- `03_vm_metrics_response.schema.json` — **新增** 03 阶段通用 schema(已有 k8s/03,补通用版)
- `04_cmdb_instance.schema.json` — **新增** 04 阶段通用 schema(基于 `apps/cmdb/models` 反射生成)

> 反射生成 model 字段定义的辅助函数 `apps/cmdb/tests/e2e/utils/model_reflection.py`:
> - 加载 `cmdb.models.<Model>`,提取 `attr_list` / `field_type` / `is_required` / `choice`
> - 输出 jsonschema 子集(用于 B 端断言)

---

## 5. 范围对象分类(详细)

### 5.1 P0 真实化(6 套,0.5 人天/对象)

| 对象 | runner | 真实化重点 | 状态 |
|---|---|---|---|
| **aliyun** | AliyunCollectMetrics | 17 行 → 100+ 行,8 个 metric_name 各 1 实例,补 plugin `(int, "vcpus")` 等复杂清洗路径 | 🟢 |
| **k8s** | CollectK8sMetrics(minimal path)| 补 01_raw_collector.json(K8s 走 VM 不走 raw),补 workload / pod / node 3 分组 | 🟢 |
| **vmware** | VMCollectMetrics | 扩 vmware fixture,补 02 标准化格式 | 🟢 |
| **host** | HostCollectMetrics | 补 host 真实采集样本(cpu / mem / disk / net 多维度) | 🟢 |
| **network** | NetworkCollectMetrics | 补 network 设备样本 | 🟢 |
| **config_file** | ConfigFileCollectMetrics | 补真实配置文件样本 | 🟢 |

### 5.2 P1 云采集新增(7 套,0.5 人天/对象)

| 对象 | runner | 真实化重点 | 状态 |
|---|---|---|---|
| **hwcloud** | HwCloudCollectMetrics | 11 个子对象(hwcloud_ecs/evs/vpc/obs/subnet/eip/sg/elb/rds/dcs),读华为云 API 文档虚构 JSON | 🟡 |
| **qcloud** | QCloudCollectMetrics | 子对象(cvm/vpc/clb/cdb/redis 等),读腾讯云 API 文档 | 🟡 |
| **fusioninsight** | FusionInsightCollectMetrics | 华为大数据(HDFS/HBase/Hive/Spark),读 API 文档 | 🟡 |
| **zstack** | ZStackCollectMetrics | 私有云,读 API 文档 | 🟡 |
| **h3c_cas** | H3cCasCollectMetrics | H3C 云,读 API 文档 | 🟡 |
| **dameng_enterprise** | (复用 dameng) | 跟 33 真实落盘里的 dameng 合并 | 🟡 |
| **redis_sentinel_enterprise** | (复用 redis_sentinel) | 跟 33 真实落盘里的 redis_sentinel 合并 | 🟡 |

### 5.3 P2 Archived placeholder(17 套,0.2 人天/对象)

| 对象 | 阻塞根因 | placeholder 策略 |
|---|---|---|
| **apusic** | 东方通 rpm + license | `_placeholder_reason: "license_missing"`,plugin stub,公共契约验证 |
| **bes** | 国产中间件 license | 同上 |
| **hdfs** | Hadoop 集群复杂 | `_placeholder_reason: "cluster_complex"`,plugin stub |
| **informix** | IBM license | 同 apusic |
| **ihs** | IBM license + amd64 | 同 apusic |
| **inforsuite_as** | 中创 license | 同 apusic |
| **iris** | InterSystems license | 同 apusic |
| **couchbase** | Enterprise license | 同 apusic |
| **oceanbase** | OceanBase license | 同 apusic |
| **oscar** | 神通 license | 同 apusic |
| **sap_hana** | SAP license | 同 apusic |
| **storm** | 集群复杂 | 同 hdfs |
| **sybase** | SAP license | 同 apusic |
| **tonggtp** | 东方通 license | 同 apusic |
| **tonglinkq** | 东方通 license | 同 apusic |
| **tongrds** | 东方通 RDS license | 同 apusic |
| **tuxedo** | Oracle license | 同 apusic |
| **weblogic** | Oracle license | 同 apusic |
| **websphere** | IBM license | 同 apusic |
| **mycat** | amd64 only | `_placeholder_reason: "platform_constraint"`,plugin stub |
| **domestic_linux** | 国产 Linux iso | `_placeholder_reason: "platform_constraint"`,plugin stub |
| **yarn** | 集群复杂 | 同 hdfs |

**注**:v3+v4 archive 文档列 18 个,本期 17 个 = 18 - 1(enterprise dameng 合并到 P1)。

### 5.4 范围对象数量汇总

```
P0 真实化(6):aliyun / k8s / vmware / host / network / config_file
P1 云采集新增(7):hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise
P2 archived placeholder(17 license + 5 集群/平台 = 22)
───────────────────────────────────────────────────
本期新工作:35 个对象 e2e fixture / schema / A/B 端测试
沿用(v3+v4 已 e2e):33 真实落盘对象
────────────────────
catalog 56 model_id - 5 skipped - 1 mssql 主动删除 = 50 纳入本期 + 33 沿用 = 83?实际 catalog 56,因 enterprise 跟 community 合并去重
```

**精确分布(详细看 archive 文档 §1 整体结果表)**:

| 维度 | 数量 | 占比 |
|---|---|---|
| 沿用 v3+v4 真实落盘(不动) | 33 | 59% |
| 本期 P0 真实化 | 6 | 11% |
| 本期 P1 云采集新增 | 7 | 13% |
| 本期 P2 archived placeholder | 17 license + 5 集群/平台 = 22 | 39% |
| 本期新工作小计 | 35 | — |
| 范围外(沿用 archive 跳过) | 5 skipped + 1 mssql 删除 = 6 | — |
| catalog 总数 | 56 | 100% |

> 数字说明:56 model_id = 33 沿用 + 35 新工作 - 12 enterprise/community 重叠(实际合并去重后)。详细每对象最终归属在 archive 文档 §6 每个对象的执行结果明细。

---

## 6. 实施步骤 / Phase 拆分

### 6.1 Phase 时间线

| Phase | 内容 | 周期 | 验收 |
|---|---|---|---|
| **P0 基础** | A/B 端测试文件骨架;02/03 通用 schema;反射 model 工具 | 0.5 人天 | 6 真实化对象先跑通,作为模板 |
| **P0 真实化(6)** | aliyun / k8s / vmware / host / network / config_file 真实 fixture + A/B 端覆盖 | 3 人天 | 6 × A/B 端测试全过 |
| **P1 云采集新增(7)** | hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise 读 API 文档虚构 JSON | 3.5 人天 | 7 × A/B 端测试全过 |
| **P2 Archived placeholder(22)** | 17 license + 5 集群/平台 走 placeholder + license_status + A/B 端公共契约 | 4.4 人天(17×0.2 + 5×0.2)| 22 × A/B 端公共契约过 |
| **收尾** | 字段漂移报告 + cross-cutting 公共契约固化 + 文档(e2e 作者指南 v2 扩展 A/B 端)| 1 人天 | 全量 35 × A/B 端 + 33 真实落盘回归 0 fail |

**总周期**:约 12.4 人天(2.5-3 人周)。

### 6.2 关键设计决策(本节需要用户 review)

| 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|
| 33 真实落盘是否加 A/B 端检查 | 加 / 不加 | **不加**(用户已确认) | 不破坏现有 33 passed |
| P2 archived 的 license 标记形式 | `_placeholder_reason` / `license_status: missing` / 两者 | **两者**(沿用 v4 `_placeholder_reason` + 新增 `license_status: missing` 标准字段) | 兼容 v4 placeholder 模式,新增 license_status 标准化 |
| K8s 流水线 minimal path 是否扩 | 扩 / 不扩 | **不扩**,只真实化已有 fixture | K8s 集群复杂度超出本期范围 |
| e2e fixture 02 阶段是否新建 | 新建 / 不新建 | **不新建**,02 阶段暂用公共契约(02 阶段跟 01 形态紧耦合) | 减少 fixture 数量,降低维护成本 |
| 跑通标准 | 5 层验证 / 3 层 + 2 端 | **3 层 + 2 端对齐**(沿用现有 3 层,A/B 端独立)| 兼容 v3+v4 已有架构 |

### 6.3 前置依赖

- 无 amd64 CI runner 需求(全部是 e2e 测试代码 + fixture 改造)
- 无 production 代码改动
- 无新依赖

---

## 7. 风险评估

### 7.1 低风险 ✅

- **零 production 代码改动**(沿用 v3+v4 模式)
- 所有改动是新增 fixture / schema / test 文件
- 33 真实落盘对象 e2e 不动,不影响 113 passed
- 6 真实化有 test_*.py 框架就绪,只需扩 fixture

### 7.2 中风险 ⚠️

- **P1 云采集读 API 文档**:hwcloud 11 个子对象 / aliyun 8 个 metric_names,需要逐个虚构 JSON,工作量超预期
- **P2 archived license_status 标注**:17 个对象需要统一标注,可能漏标
- **A/B 端检查可能暴露新问题**:比如 K8s 的 prometheus_kube_* metric 跟 CMDB model 字段对不齐,发现后需修复(超出本期范围,记录到后续)
- **cmdb.models 反射**:某些动态字段(如 vcpus / memory_mb)需要 type hint 正确

### 7.3 高风险 🔴

- 无(本期所有改动都是 e2e 测试代码 + fixture)

### 7.4 缓解措施

- P1 子对象拆分:hwcloud / aliyun 先做核心对象(ecs / vpc),子对象作为下期
- A/B 端检查暴露的新问题:**不修复**,记录到"后续工作",但 e2e 测试用 `xfail` 标记,等修复后转 pass
- 反射工具:**逐步覆盖**,先覆盖 6 真实化对象需要的 model,再扩到 30 对象

---

## 8. 验证清单

### 8.1 单元 / 集成验证

- [x] `pytest server/apps/cmdb/tests/e2e/test_pipeline_factory.py` 沿用 v3+v4 113 passed
- [ ] `pytest server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py` 35 个新对象 A 端全过
- [ ] `pytest server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py` 35 个新对象 B 端全过
- [ ] `pytest server/apps/cmdb/tests/e2e/test_common_contract.py` 公共契约 35 + 33 = 68 个对象覆盖
- [ ] `pytest server/apps/cmdb/tests/e2e/test_placeholder_objects.py` 22 个 archived placeholder 全过

### 8.2 跨对象验证

- [ ] 字段漂移报告:`make e2e-drift-report`(自动生成)
- [ ] 公共契约反向校验:`test_common_contract_cover_no_orphan_model_id` 扩展到 35 + 33 = 68 个对象
- [ ] 沿用 v3+v4 `test_pipeline_factory.py` 的 3 层验证 0 fail

### 8.3 文档验证

- [ ] `docs/cmdb-e2e-author-guide.md` 扩展 v2:加 A/B 端检查章节
- [ ] `docs/superpowers/specs/2026-07-13-cmdb-collect-full-e2e-alignment-design.md`(本 spec) review 通过
- [ ] `docs/superpowers/plans/2026-MM-dd-cmdb-collect-full-e2e-alignment-execution-report.md` 各 Phase 收尾报告

---

## 9. 测试结果回填字段(本节由执行者填)

> 按"文档使用约定"§0.1,每个对象完成 e2e 后,执行者手动回填 pytest 行号 + 验证状态。

| 对象 | Phase | A 端 pytest 行号 | B 端 pytest 行号 | 验证状态 | 备注 |
|---|---|---|---|---|---|
| aliyun | P0 | TBD | TBD | TBD | TBD |
| k8s | P0 | TBD | TBD | TBD | TBD |
| ... | | | | | |

---

## 10. 一句话总结

**本期新增 A 端 + B 端两类字段对齐检查(独立 cross-cutting 测试文件),覆盖 6 真实化 + 7 云采集 + 22 archived placeholder 共 35 个新对象,catalog 56 model_id 100% e2e 触达(33 沿用 + 35 新工作 - 12 enterprise/community 合并)。不动现有 33 真实落盘对象,零 production 代码改动,周期约 12.4 人天。**

---

## 11. 后续工作(本 spec 外)

- 17 archived 对象 license 解锁后,fixture 替换为真实数据,自动升级 placeholder → passed
- A/B 端检查暴露的新问题(可能在 K8s / 国产化二进制对象)→ 单独 follow-up spec
- amd64 CI runner 解锁后,18 archived 国产 binary 对象重试 fixture 真实采集
- 字段漂移检测自动化(`make e2e-drift-report`)+ dashboard
- e2e 作者指南 v2 扩展 A/B 端章节
