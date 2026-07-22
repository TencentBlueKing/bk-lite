# Historical Superpowers change: 2026-06-10-cmdb-field-governance-tags

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-10-cmdb-field-governance-tags.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为商业版 CMDB 模型字段新增治理标记能力，支持关键属性和时效性标记，并保持社区/商业前后端代码分离。

**Architecture:** 后端复用 CMDB `ModelEnterpriseExtension` 扩展契约，社区代码只提供 hook 与调用点，商业版 provider 实现 `governance` 规范化、导入导出和变更记录 diff。前端参考 `system-manager` 企业 hook 增强模式，社区属性页只加载扩展并提供表格/表单插槽，商业版提供真实治理标记 UI。

**Tech Stack:** Python 3.12, Django 4.2, pytest, Next.js 16, React 19, TypeScript, Ant Design, pnpm.

---

## 范围检查

本计划只覆盖第一阶段：模型字段支持治理标记。

不实现：

- CMDB 数据治理健康度计算。
- 运营分析仪表盘展示。
- 实例录入、实例列表、实例详情侧展示治理标记。

## 文件结构

后端社区侧：

- 修改 `server/apps/cmdb/model_ops/extensions.py`
  - 扩展 `ModelEnterpriseExtension` 默认 no-op 契约。
  - 提供治理导入、导出、变更记录 diff 的默认空实现。
- 修改 `server/apps/cmdb/services/model.py`
  - 字段新增/编辑继续调用 `validate_attr`。
  - 编辑字段时持久化 `governance`。
  - 变更记录 message 追加企业 diff 文案。
  - 模型配置导出调用企业扩展追加治理列。
- 修改 `server/apps/cmdb/model_migrate/migrete_service.py`
  - 导入字段行时调用企业扩展解析治理列。
  - 合并已有字段时允许更新 `governance`。
- 修改 `server/apps/cmdb/tests/test_enterprise_extensions.py`
  - 验证社区默认扩展仍为 no-op。

后端商业侧：

- 修改 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py`
  - 实现治理标记常量、规范化、校验、导入导出列、变更 diff。
- 新增 `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py`
  - 覆盖商业版治理标记核心规则。

前端社区侧：

- 新增 `web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`
  - 默认空扩展与 enterprise 动态加载。
- 修改 `web/src/app/cmdb/types/assetManage.ts`
  - 增加 `governance` 类型。
- 修改 `web/src/app/cmdb/(pages)/assetManage/management/detail/attributes/page.tsx`
  - 表格 columns 追加企业列。
- 修改 `web/src/app/cmdb/(pages)/assetManage/management/detail/attributes/attributesModal.tsx`
  - 调用企业扩展做回显、提交归一化、表单块渲染。

前端商业侧：

- 新增 `enterprise/web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`
  - 提供治理表格列、治理表单分组、字段类型切换清理逻辑。

## 执行规则

- 本计划不要求执行阶段自动提交。若用户要求提交，再按任务粒度提交。
- 每个任务先写测试或类型约束，再实现最小代码。
- 不改第二阶段和第三阶段代码。
- 不复制整个 CMDB 属性管理页面到企业版。
- 不沿用附件/图片字段在社区前端硬编码的方式。

### Task 1: 扩展后端社区契约

**Files:**
- Modify: `server/apps/cmdb/model_ops/extensions.py`
- Test: `server/apps/cmdb/tests/test_enterprise_extensions.py`

- [ ] **Step 1: 写社区默认扩展测试**

在 `server/apps/cmdb/tests/test_enterprise_extensions.py` 的 `test_model_default_when_unregistered` 中补充断言：

```python
def test_model_default_when_unregistered():
    ext = get_model_enterprise_extension()
    assert isinstance(ext, ModelEnterpriseExtension)
    assert ext.file_attr_types() == set()
    assert ext.unsupported_unique_attr_types() == set()
    assert ext.normalize_import_attr({"attr_id": "name"}) == {"attr_id": "name"}
    assert ext.extra_export_attr_headers() == ([], [])
    assert ext.extend_export_attr_row({"attr_id": "name"}) == {}
    assert ext.build_attr_change_message({}, {}) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_model_default_when_unregistered -q
```

Expected: FAIL，错误包含 `AttributeError: 'ModelEnterpriseExtension' object has no attribute 'normalize_import_attr'`。

- [ ] **Step 3: 实现社区默认契约**

在 `server/apps/cmdb/model_ops/extensions.py` 的 `ModelEnterpriseExtension` 类中加入：

```python
    def normalize_import_attr(self, attr: dict) -> dict:
        """模型配置导入时的企业版字段规范化。默认原样返回。"""
        return attr

    def extra_export_attr_headers(self) -> tuple[list[str], list[str]]:
        """模型配置导出时追加的属性表头，返回 (中文表头, 英文字段)。"""
        return [], []

    def extend_export_attr_row(self, attr: dict) -> dict:
        """模型配置导出时追加的属性行字段。默认不追加。"""
        return {}

    def build_attr_change_message(self, before_attr: dict, after_attr: dict) -> str:
        """模型属性变更记录追加文案。默认不追加。"""
        return ""
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_model_default_when_unregistered -q
```

Expected: PASS。

### Task 2: 实现后端商业治理规则

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py`
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py`

- [ ] **Step 1: 写商业 provider 纯规则测试**

创建 `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py`：

```python
import pytest

from apps.cmdb_enterprise.model_ops.provider import get_model_enterprise_extension
from apps.core.exceptions.base_app_exception import BaseAppException


def test_governance_defaults_for_normal_field():
    ext = get_model_enterprise_extension()
    attr = ext.validate_attr({"attr_id": "ip", "attr_type": "str"})
    assert attr["governance"] == {"key_attribute": False, "freshness": ""}


def test_governance_accepts_valid_values():
    ext = get_model_enterprise_extension()
    attr = ext.validate_attr(
        {
            "attr_id": "ip",
            "attr_type": "str",
            "governance": {"key_attribute": True, "freshness": "timely"},
        }
    )
    assert attr["governance"] == {"key_attribute": True, "freshness": "timely"}


@pytest.mark.parametrize("attr_type", ["attachment", "image", "table", "pwd"])
def test_governance_cleared_for_unsupported_types(attr_type):
    ext = get_model_enterprise_extension()
    attr = ext.validate_attr(
        {
            "attr_id": "field",
            "attr_type": attr_type,
            "governance": {"key_attribute": True, "freshness": "timely"},
        }
    )
    assert attr["governance"] == {"key_attribute": False, "freshness": ""}


def test_governance_rejects_invalid_freshness():
    ext = get_model_enterprise_extension()
    with pytest.raises(BaseAppException, match="时效性标记不合法"):
        ext.validate_attr(
            {
                "attr_id": "ip",
                "attr_type": "str",
                "governance": {"key_attribute": False, "freshness": "bad"},
            }
        )


def test_governance_rejects_non_boolean_key_attribute():
    ext = get_model_enterprise_extension()
    with pytest.raises(BaseAppException, match="关键属性标记必须为布尔值"):
        ext.validate_attr(
            {
                "attr_id": "ip",
                "attr_type": "str",
                "governance": {"key_attribute": "yes", "freshness": ""},
            }
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py -q
```

Expected: FAIL，至少 `governance` 默认值断言失败。

- [ ] **Step 3: 实现商业 provider 治理规则**

在 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py` 顶部补充：

```python
from apps.core.exceptions.base_app_exception import BaseAppException
```

在文件中加入常量：

```python
GOVERNANCE_DEFAULT = {"key_attribute": False, "freshness": ""}
GOVERNANCE_FRESHNESS_TIMELY = "timely"
GOVERNANCE_FRESHNESS_OCCASIONAL = "occasional"
GOVERNANCE_FRESHNESS_STABLE = "stable"
GOVERNANCE_FRESHNESS_CHOICES = {
    "",
    GOVERNANCE_FRESHNESS_TIMELY,
    GOVERNANCE_FRESHNESS_OCCASIONAL,
    GOVERNANCE_FRESHNESS_STABLE,
}
GOVERNANCE_FRESHNESS_WINDOWS = {
    GOVERNANCE_FRESHNESS_TIMELY: 7,
    GOVERNANCE_FRESHNESS_OCCASIONAL: 90,
    GOVERNANCE_FRESHNESS_STABLE: None,
}
GOVERNANCE_UNSUPPORTED_ATTR_TYPES = {"table", "pwd"}
```

在 `FileFieldModelExtension` 类中加入方法：

```python
    def _unsupported_governance_attr_types(self) -> set:
        return set(FILE_ATTR_TYPES) | GOVERNANCE_UNSUPPORTED_ATTR_TYPES

    def _default_governance(self) -> dict:
        return dict(GOVERNANCE_DEFAULT)

    def _normalize_governance(self, attr: dict) -> dict:
        attr_type = attr.get("attr_type")
        if attr_type in self._unsupported_governance_attr_types():
            return self._default_governance()

        raw = attr.get("governance") or {}
        if not isinstance(raw, dict):
            raise BaseAppException("治理标记必须为对象")

        key_attribute = raw.get("key_attribute", False)
        if not isinstance(key_attribute, bool):
            raise BaseAppException("关键属性标记必须为布尔值")

        freshness = raw.get("freshness", "")
        if freshness is None:
            freshness = ""
        freshness = str(freshness)
        if freshness not in GOVERNANCE_FRESHNESS_CHOICES:
            raise BaseAppException("时效性标记不合法")

        return {"key_attribute": key_attribute, "freshness": freshness}
```

修改 `validate_attr`，在已有附件/图片规则之后统一补充：

```python
        attr["governance"] = self._normalize_governance(attr)
        return attr
```

- [ ] **Step 4: 运行商业规则测试**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py -q
```

Expected: PASS。

### Task 3: 字段编辑持久化 governance 并写变更记录 diff

**Files:**
- Modify: `server/apps/cmdb/services/model.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py`

- [ ] **Step 1: 写字段更新持久化与 diff 测试**

在 `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py` 追加：

```python
import json

import pytest

from apps.cmdb.services.model import ModelManage


@pytest.mark.django_db
def test_update_model_attr_persists_governance(fake_graph, monkeypatch):
    captured = {}

    def fake_set(*args, **kwargs):
        captured["attrs"] = args[2]["attrs"]
        return [{"_id": 1, "attrs": args[2]["attrs"]}]

    monkeypatch.setattr("apps.cmdb.services.model.create_change_record", lambda *a, **k: None)
    monkeypatch.setattr("apps.cmdb.services.model.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
        lambda *a, **k: None,
    )
    existing = json.dumps(
        [
            {
                "attr_id": "ip",
                "attr_name": "IP",
                "attr_type": "str",
                "attr_group": "default",
                "is_required": False,
                "editable": True,
                "is_only": False,
                "option": {},
                "user_prompt": "",
                "default_value": [],
                "governance": {"key_attribute": False, "freshness": ""},
            }
        ],
        ensure_ascii=False,
    )
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"_id": 1, "model_name": "主机", "attrs": existing}], 1),
        set_entity_properties=fake_set,
    )

    ModelManage.update_model_attr(
        "host",
        {
            "attr_id": "ip",
            "attr_name": "IP",
            "attr_type": "str",
            "attr_group": "default",
            "is_required": False,
            "editable": True,
            "is_only": False,
            "option": {},
            "user_prompt": "",
            "default_value": [],
            "governance": {"key_attribute": True, "freshness": "occasional"},
        },
        username="admin",
    )

    persisted = json.loads(captured["attrs"])
    assert persisted[0]["governance"] == {"key_attribute": True, "freshness": "occasional"}


def test_build_attr_change_message_for_governance():
    ext = get_model_enterprise_extension()
    message = ext.build_attr_change_message(
        {"governance": {"key_attribute": False, "freshness": ""}},
        {"governance": {"key_attribute": True, "freshness": "timely"}},
    )
    assert message == "治理标记: 关键属性 否 -> 是; 时效性 未设置 -> 需要及时更新(7天)"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py::test_update_model_attr_persists_governance ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py::test_build_attr_change_message_for_governance -q
```

Expected: FAIL，`governance` 未持久化或 diff 文案为空。

- [ ] **Step 3: 实现商业 diff 文案**

在 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py` 中加入：

```python
GOVERNANCE_KEY_LABELS = {False: "否", True: "是"}
GOVERNANCE_FRESHNESS_LABELS = {
    "": "未设置",
    GOVERNANCE_FRESHNESS_TIMELY: "需要及时更新(7天)",
    GOVERNANCE_FRESHNESS_OCCASIONAL: "不频繁更新(90天)",
    GOVERNANCE_FRESHNESS_STABLE: "基本不变(不参与判定)",
}
```

在 `FileFieldModelExtension` 类中加入：

```python
    def _read_governance(self, attr: dict) -> dict:
        raw = attr.get("governance") or {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "key_attribute": raw.get("key_attribute", False) if isinstance(raw.get("key_attribute", False), bool) else False,
            "freshness": raw.get("freshness", "") if raw.get("freshness", "") in GOVERNANCE_FRESHNESS_CHOICES else "",
        }

    def build_attr_change_message(self, before_attr: dict, after_attr: dict) -> str:
        before = self._read_governance(before_attr)
        after = self._read_governance(after_attr)
        changes = []
        if before["key_attribute"] != after["key_attribute"]:
            changes.append(
                f"关键属性 {GOVERNANCE_KEY_LABELS[before['key_attribute']]} -> {GOVERNANCE_KEY_LABELS[after['key_attribute']]}"
            )
        if before["freshness"] != after["freshness"]:
            changes.append(
                f"时效性 {GOVERNANCE_FRESHNESS_LABELS[before['freshness']]} -> {GOVERNANCE_FRESHNESS_LABELS[after['freshness']]}"
            )
        return f"治理标记: {'; '.join(changes)}" if changes else ""
```

- [ ] **Step 4: 修改社区 update 持久化和变更记录**

在 `server/apps/cmdb/services/model.py` 的 `update_model_attr` 中，在更新 attr 时增加 `governance`：

```python
                attr.update(
                    attr_group=attr_info["attr_group"],
                    attr_name=attr_info["attr_name"],
                    is_required=False if is_tag_attr else attr_info["is_required"],
                    editable=True if is_tag_attr else attr_info["editable"],
                    option=attr_info["option"],
                    user_prompt=attr_info["user_prompt"],
                    default_value=attr_info.get("default_value", []),
                    governance=attr_info.get("governance", attr.get("governance")),
                )
```

在 `create_change_record` 前构造 message：

```python
        governance_message = get_model_enterprise_extension().build_attr_change_message(current_attr, attr or {})
        message = f"修改模型属性. 模型名称: {model_info['model_name']}"
        if governance_message:
            message = f"{message}. {governance_message}"
```

并把原先 `message=f"修改模型属性. 模型名称: {model_info['model_name']}"` 替换为：

```python
            message=message,
```

字段创建记录可以追加创建后的治理文案：

```python
        governance_message = get_model_enterprise_extension().build_attr_change_message({}, attr or {})
        message = f"创建模型属性. 模型名称: {model_info['model_name']}"
        if governance_message:
            message = f"{message}. {governance_message}"
```

并将创建记录的 `message=` 替换为 `message=message`。

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py -q
```

Expected: PASS。

### Task 4: 模型配置导入导出支持 governance

**Files:**
- Modify: `server/apps/cmdb/services/model.py`
- Modify: `server/apps/cmdb/model_migrate/migrete_service.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py`

- [ ] **Step 1: 写导入导出规则测试**

在 `enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py` 追加：

```python
def test_export_attr_headers_and_row_include_governance():
    ext = get_model_enterprise_extension()
    cn_headers, en_headers = ext.extra_export_attr_headers()
    assert cn_headers == ["关键属性", "时效性"]
    assert en_headers == ["governance_key_attribute", "governance_freshness"]
    row = ext.extend_export_attr_row(
        {"governance": {"key_attribute": True, "freshness": "stable"}}
    )
    assert row == {"governance_key_attribute": True, "governance_freshness": "stable"}


def test_normalize_import_attr_parses_governance_columns():
    ext = get_model_enterprise_extension()
    attr = ext.normalize_import_attr(
        {
            "attr_id": "ip",
            "attr_type": "str",
            "governance_key_attribute": True,
            "governance_freshness": "occasional",
        }
    )
    assert attr["governance"] == {"key_attribute": True, "freshness": "occasional"}
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py::test_export_attr_headers_and_row_include_governance ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py::test_normalize_import_attr_parses_governance_columns -q
```

Expected: FAIL，导出列为空或导入未生成 `governance`。

- [ ] **Step 3: 实现商业导入导出方法**

在 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py` 的 `FileFieldModelExtension` 类中加入：

```python
    def extra_export_attr_headers(self) -> tuple[list[str], list[str]]:
        return ["关键属性", "时效性"], ["governance_key_attribute", "governance_freshness"]

    def extend_export_attr_row(self, attr: dict) -> dict:
        governance = self._read_governance(attr)
        return {
            "governance_key_attribute": governance["key_attribute"],
            "governance_freshness": governance["freshness"],
        }

    def normalize_import_attr(self, attr: dict) -> dict:
        next_attr = dict(attr)
        raw_key = next_attr.pop("governance_key_attribute", next_attr.pop("关键属性", None))
        raw_freshness = next_attr.pop("governance_freshness", next_attr.pop("时效性", None))

        governance = {}
        if raw_key not in (None, ""):
            if isinstance(raw_key, bool):
                governance["key_attribute"] = raw_key
            elif str(raw_key).strip().lower() in {"true", "1", "yes", "是"}:
                governance["key_attribute"] = True
            elif str(raw_key).strip().lower() in {"false", "0", "no", "否"}:
                governance["key_attribute"] = False
            else:
                raise BaseAppException("关键属性标记必须为布尔值")

        if raw_freshness not in (None, ""):
            governance["freshness"] = str(raw_freshness).strip()

        if governance:
            next_attr["governance"] = governance
        return self.validate_attr(next_attr)
```

- [ ] **Step 4: 接入社区导入流程**

在 `server/apps/cmdb/model_migrate/migrete_service.py` 顶部加入：

```python
from apps.cmdb.model_ops.extensions import get_model_enterprise_extension
```

在 `_prepare_attr` 返回前、`user_prompt` 设置后加入：

```python
        attr = get_model_enterprise_extension().normalize_import_attr(attr)
```

在 `_merge_existing_attr_config` 中，布尔约束循环之后加入：

```python
        if "governance" in incoming_attr and existing_attr.get("governance") != incoming_attr.get("governance"):
            existing_attr["governance"] = incoming_attr.get("governance")
            changed = True
```

- [ ] **Step 5: 接入社区导出流程**

在 `server/apps/cmdb/services/model.py` 的 `export_model_config` 中，定义 headers 后加入：

```python
        extra_attr_headers_cn, extra_attr_headers_en = get_model_enterprise_extension().extra_export_attr_headers()
        ATTR_HEADERS_CN = [*ATTR_HEADERS_CN, *extra_attr_headers_cn]
        ATTR_HEADERS_EN = [*ATTR_HEADERS_EN, *extra_attr_headers_en]
```

生成 `attr_rows.append({...})` 时，将基础行拆成变量并合并企业列：

```python
                row = {
                    "attr_id": attr.get("attr_id", ""),
                    "attr_name": attr.get("attr_name", ""),
                    "attr_type": attr.get("attr_type", ""),
                    "option": option_str,
                    "attr_group": attr.get("attr_group", ""),
                    "is_only": attr.get("is_only", False),
                    "editable": attr.get("editable", True),
                    "is_required": attr.get("is_required", False),
                    "user_prompt": attr.get("user_prompt", ""),
                    "default_value": json.dumps(attr.get("default_value", []), ensure_ascii=False) if attr.get("attr_type") == "enum" else "",
                }
                row.update(get_model_enterprise_extension().extend_export_attr_row(attr))
                attr_rows.append(row)
```

写 Excel 行时改为按 `ATTR_HEADERS_EN` 输出：

```python
                ws_attr.append([row.get(header, "") for header in ATTR_HEADERS_EN])
```

- [ ] **Step 6: 运行导入导出测试**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py -q
```

Expected: PASS。

### Task 5: 增加前端社区扩展 hook 和类型

**Files:**
- Create: `web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`
- Modify: `web/src/app/cmdb/types/assetManage.ts`

- [ ] **Step 1: 新增治理类型**

在 `web/src/app/cmdb/types/assetManage.ts` 中加入：

```ts
export type GovernanceFreshness = '' | 'timely' | 'occasional' | 'stable';

export interface AttrGovernance {
  key_attribute: boolean;
  freshness: GovernanceFreshness;
}
```

在 `AttrFieldType` 和 `FullInfoAttrItem` 中加入：

```ts
  governance?: AttrGovernance;
```

- [ ] **Step 2: 新增社区默认扩展 hook**

创建 `web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`：

```tsx
'use client';

import React from 'react';
import type { ColumnItem } from '@/types';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

export interface AttributeFormContext {
  form: any;
  type: string;
  attrInfo: AttrFieldType;
}

export interface AttributeEnterpriseExtension {
  getExtraColumns: () => ColumnItem[];
  renderExtraFormItems: (context: AttributeFormContext) => React.ReactNode;
  normalizeInitialValues: (values: AttrFieldType) => AttrFieldType;
  normalizeSubmitValues: (values: AttrFieldType) => AttrFieldType;
}

export const useCEAttributeEnterpriseExtension = (): AttributeEnterpriseExtension => ({
  getExtraColumns: () => [],
  renderExtraFormItems: () => null,
  normalizeInitialValues: (values) => values,
  normalizeSubmitValues: (values) => values,
});

const loadEnterpriseExtension = () => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/app/cmdb/(enterprise)/hooks/useAttributeEnterpriseExtension');
    return mod.useAttributeEnterpriseExtension || useCEAttributeEnterpriseExtension;
  } catch {
    return useCEAttributeEnterpriseExtension;
  }
};

export const useAttributeEnterpriseExtension = loadEnterpriseExtension();
```

- [ ] **Step 3: 类型检查**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS 或只出现仓库既有无关类型错误；若出现本任务新增文件相关错误，修正后重跑。

### Task 6: 接入前端社区属性表格和弹窗插槽

**Files:**
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/detail/attributes/page.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/detail/attributes/attributesModal.tsx`

- [ ] **Step 1: 属性表格追加企业列**

在 `page.tsx` import 区加入：

```ts
import { useAttributeEnterpriseExtension } from '@/app/cmdb/hooks/useAttributeEnterpriseExtension';
```

在组件内加入：

```ts
  const attributeEnterpriseExtension = useAttributeEnterpriseExtension();
```

将 columns 定义从：

```ts
  const columns: ColumnItem[] = [
```

改为基础列加合并：

```ts
  const baseColumns: ColumnItem[] = [
```

并在 base columns 结束后加入：

```ts
  const columns: ColumnItem[] = [
    ...baseColumns.slice(0, -1),
    ...attributeEnterpriseExtension.getExtraColumns(),
    baseColumns[baseColumns.length - 1],
  ];
```

- [ ] **Step 2: 属性弹窗加载企业扩展**

在 `attributesModal.tsx` import 区加入：

```ts
import { useAttributeEnterpriseExtension } from '@/app/cmdb/hooks/useAttributeEnterpriseExtension';
```

在组件内 `const { t } = useTranslation();` 后加入：

```ts
    const attributeEnterpriseExtension = useAttributeEnterpriseExtension();
```

编辑回显时，将：

```ts
        formRef.current?.setFieldsValue({
          ...attrInfo,
          group_id: selectedGroup?.id,
          default_value:
            (attrInfo.enum_select_mode || 'single') === 'multiple'
              ? normalizedDefaultValue
              : normalizedDefaultValue[0] ?? undefined,
        });
```

替换为：

```ts
        const normalizedAttrInfo = attributeEnterpriseExtension.normalizeInitialValues(attrInfo);
        formRef.current?.setFieldsValue({
          ...normalizedAttrInfo,
          group_id: selectedGroup?.id,
          default_value:
            (normalizedAttrInfo.enum_select_mode || 'single') === 'multiple'
              ? normalizedDefaultValue
              : normalizedDefaultValue[0] ?? undefined,
        });
```

提交前，将：

```ts
        operateAttr(submitParams as AttrFieldType);
```

替换为：

```ts
        operateAttr(attributeEnterpriseExtension.normalizeSubmitValues(submitParams as AttrFieldType));
```

在类型配置区域与必填/可编辑分隔线之间渲染企业表单块：

```tsx
            {attributeEnterpriseExtension.renderExtraFormItems({
              form: formRef.current,
              type,
              attrInfo,
            })}
```

- [ ] **Step 3: 类型检查**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS 或只出现仓库既有无关类型错误；若出现本任务新增代码相关错误，修正后重跑。

### Task 7: 实现前端商业治理 UI

**Files:**
- Create: `enterprise/web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`

- [ ] **Step 1: 新增商业前端 hook**

创建 `enterprise/web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx`：

```tsx
'use client';

import React, { useMemo } from 'react';
import { Alert, Form, Radio, Select } from 'antd';
import type { ColumnItem } from '@/types';
import type {
  AttrFieldType,
  AttrGovernance,
  GovernanceFreshness,
} from '@/app/cmdb/types/assetManage';
import type {
  AttributeEnterpriseExtension,
  AttributeFormContext,
} from '@/app/cmdb/hooks/useAttributeEnterpriseExtension';

const UNSUPPORTED_GOVERNANCE_TYPES = new Set(['attachment', 'image', 'table', 'pwd']);

const DEFAULT_GOVERNANCE: AttrGovernance = {
  key_attribute: false,
  freshness: '',
};

const FRESHNESS_OPTIONS: Array<{ label: string; value: GovernanceFreshness }> = [
  { label: '未设置', value: '' },
  { label: '需要及时更新（7天）', value: 'timely' },
  { label: '不频繁更新（90天）', value: 'occasional' },
  { label: '基本不变（不参与判定）', value: 'stable' },
];

const getGovernance = (value?: AttrGovernance): AttrGovernance => ({
  key_attribute: value?.key_attribute === true,
  freshness: value?.freshness || '',
});

const getFreshnessLabel = (value?: GovernanceFreshness) => (
  FRESHNESS_OPTIONS.find((item) => item.value === (value || ''))?.label || '未设置'
);

const isUnsupportedType = (attrType?: string) => UNSUPPORTED_GOVERNANCE_TYPES.has(attrType || '');

export const useAttributeEnterpriseExtension = (): AttributeEnterpriseExtension => {
  return useMemo(() => ({
    getExtraColumns: (): ColumnItem[] => [
      {
        title: '关键属性',
        key: 'governance_key_attribute',
        dataIndex: 'governance',
        width: 110,
        render: (governance: AttrGovernance | undefined) => (getGovernance(governance).key_attribute ? '是' : '否'),
      },
      {
        title: '时效性',
        key: 'governance_freshness',
        dataIndex: 'governance',
        width: 180,
        render: (governance: AttrGovernance | undefined) => getFreshnessLabel(getGovernance(governance).freshness),
      },
    ],
    renderExtraFormItems: ({ form }: AttributeFormContext) => (
      <Form.Item noStyle shouldUpdate={(prev, curr) => prev.attr_type !== curr.attr_type}>
        {({ getFieldValue, setFieldsValue }) => {
          const attrType = getFieldValue('attr_type');
          const unsupported = isUnsupportedType(attrType);
          if (unsupported) {
            const current = getGovernance(getFieldValue('governance'));
            if (current.key_attribute || current.freshness) {
              setFieldsValue({ governance: DEFAULT_GOVERNANCE });
            }
          }
          return (
            <div className="border border-[var(--color-border-2)] rounded-md px-4 pt-4 pb-2 mb-4">
              <div className="font-medium mb-3">治理标记</div>
              {unsupported && (
                <Alert
                  className="mb-3"
                  type="info"
                  showIcon
                  message="附件、图片、表格、密码类型不支持治理标记"
                />
              )}
              <Form.Item label="关键属性" name={['governance', 'key_attribute']} initialValue={false}>
                <Radio.Group
                  disabled={unsupported}
                  optionType="button"
                  buttonStyle="solid"
                  options={[
                    { label: '是', value: true },
                    { label: '否', value: false },
                  ]}
                />
              </Form.Item>
              <Form.Item label="时效性" name={['governance', 'freshness']} initialValue="">
                <Select disabled={unsupported} options={FRESHNESS_OPTIONS} />
              </Form.Item>
            </div>
          );
        }}
      </Form.Item>
    ),
    normalizeInitialValues: (values: AttrFieldType): AttrFieldType => ({
      ...values,
      governance: getGovernance(values.governance),
    }),
    normalizeSubmitValues: (values: AttrFieldType): AttrFieldType => ({
      ...values,
      governance: isUnsupportedType(values.attr_type)
        ? DEFAULT_GOVERNANCE
        : getGovernance(values.governance),
    }),
  }), []);
};
```

- [ ] **Step 2: 类型检查**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS 或只出现仓库既有无关类型错误；若出现本任务新增 hook 相关错误，修正后重跑。

### Task 8: 最小质量门禁

**Files:**
- Verify only.

- [ ] **Step 1: 运行后端聚焦测试**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_tags.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行后端 CMDB 模型属性 BDD**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/bdd/test_model_attr_bdd.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行前端类型检查**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS 或只出现仓库既有无关类型错误；本需求新增文件不得出现在错误列表中。

- [ ] **Step 4: 运行前端 lint**

Run:

```bash
cd web && pnpm lint
```

Expected: PASS 或只出现仓库既有无关 lint；本需求新增文件不得出现在错误列表中。

- [ ] **Step 5: 检查 git 状态**

Run:

```bash
git status --short
```

Expected: 只包含本需求相关文件，以及执行前已存在的 `enterprise` 状态。不得出现无关格式化或构建产物。

## 自检结果

- 规格覆盖：计划覆盖字段新增/编辑、商业版前后端分离、`governance` 分组数据结构、不支持字段类型、导入导出、变更记录 diff、测试门禁。
- 占位扫描：本文档不包含未决占位。
- 类型一致性：统一使用 `governance.key_attribute` 与 `governance.freshness`；时效性取值为 `'' | 'timely' | 'occasional' | 'stable'`。

## specs: 2026-06-10-cmdb-field-governance-tags-design.md

日期：2026-06-10

## 背景

CMDB 数据治理需要在字段定义层面回答两个问题：

- 哪些字段是关键属性，用于后续完整性度量。
- 每个字段应多久核实一次，用于后续新鲜度度量。

本阶段只交付模型字段治理标记的定义与维护，不做治理健康度计算，不在实例录入、实例列表、实例详情中暴露治理标记，也不接入运营分析仪表盘。

本需求只面向商业版。社区版代码只保留稳定扩展缝，商业版代码拥有真实治理规则和展示逻辑。

## 目标

- 在模型字段定义中新增系统预定义的治理标记属性族。
- 本期支持两个标记：
  - 关键属性：是/否，默认否。
  - 时效性：未设置、需要及时更新、不频繁更新、基本不变。
- 标记均为可选，未设置时不影响字段现有行为。
- 附件、图片、表格、密码字段不可设置治理标记。
- 治理标记随模型配置导入导出。
- 治理标记变更在模型管理变更记录中可追溯。
- 前后端商业逻辑按仓库现有成熟方式分离。

## 非目标

- 管理员自定义标记维度或选项。
- 时效性时窗配置。
- 治理健康度计算。
- 运营分析仪表盘展示。
- 实例创建、编辑、列表、详情侧暴露治理标记。
- 关系完整性、字段分层等后续治理维度。

## 采用的现有模式

### 后端模式

CMDB 已有社区扩展注册表：`server/apps/cmdb/extensions/registry.py`。

模型能力域已有社区契约：`server/apps/cmdb/model_ops/extensions.py` 中的 `ModelEnterpriseExtension`。

商业版通过 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py` 注册企业实现。

本设计继续扩展模型能力域契约。社区代码只调用契约，不包含商业治理规则。

### 前端模式

前端不参考 CMDB 现有附件/图片字段的社区硬编码方式。

本需求参考 `system-manager` 的企业 hook 增强模式：

- 社区代码定义默认实现。
- 社区代码尝试加载 `@/app/<module>/(enterprise)/...`。
- 企业模块不存在时回退到社区默认实现。
- 企业代码在 `enterprise/web/src/app/...` 下提供真实增强。

参考位置：

- `web/src/app/system-manager/hooks/useUserModalData.ts`
- `web/src/app/system-manager/hooks/useSensitiveFieldEditBehavior.ts`
- `enterprise/web/src/app/system-manager/hooks/useSensitiveFieldEditBehavior.ts`

## 数据模型

在模型字段 `attrs` JSON 的每个字段对象上新增同级属性族 `governance`。

```json
{
  "attr_id": "inst_name",
  "attr_name": "实例名称",
  "attr_type": "str",
  "is_required": true,
  "is_only": true,
  "editable": true,
  "governance": {
    "key_attribute": true,
    "freshness": "timely"
  }
}
```

`governance` 表示治理标记属性族。它与 `is_required`、`is_only`、`editable` 同级；具体治理维度放在 `governance` 内部，便于后续扩展。

### governance 字段

`key_attribute`：

- 类型：布尔值。
- 默认值：`false`。
- 含义：是否为关键属性，供后续完整性度量使用。

`freshness`：

- 类型：字符串。
- 默认值：`""`。
- 可选值：
  - `""`：未设置。
  - `timely`：需要及时更新，固定 7 天判定窗口。
  - `occasional`：不频繁更新，固定 90 天判定窗口。
  - `stable`：基本不变，不参与新鲜度判定。

时效性判定窗口是商业版固定常量，不提供配置入口：

```python
{
    "timely": 7,
    "occasional": 90,
    "stable": None,
}
```

## 不支持的字段类型

以下字段类型不支持治理标记：

- `attachment`
- `image`
- `table`
- `pwd`

商业版后端对这些字段统一规范化为默认治理结构：

```json
{
  "key_attribute": false,
  "freshness": ""
}
```

这里采用规范化而不是报错。这样字段类型切换到不支持类型时，编辑流程更稳定，后端也能兜底清理绕过前端提交的治理值。

## 后端代码分离

社区代码只拥有扩展缝和公共数据流。

`ModelEnterpriseExtension` 增加或复用以下契约：

- 复用现有 `validate_attr(attr)`，在字段新增/编辑时规范化字段元数据。
- 增加模型配置导入行规范化 hook。
- 增加模型配置导出列 hook。
- 增加字段变更记录 diff 文案 hook。

边界要求：

- 社区代码负责调用扩展 hook。
- 商业代码负责治理字段名、枚举值、校验规则、展示文案和导入导出列。
- 社区代码不写死关键属性、时效性等商业语义。

商业版实现位置：

```text
enterprise/server/apps/cmdb_enterprise/model_ops/provider.py
```

商业版 provider 负责：

- 定义 `governance` 字段结构。
- 定义时效性可选值。
- 定义固定时窗。
- 规范化不支持字段类型。
- 输出校验错误信息。
- 输出变更记录治理 diff 文案。
- 输出模型配置导入导出的治理列定义与解析逻辑。

## 后端数据流

### 新增字段

1. `ModelManage.create_model_attr` 接收字段 payload。
2. 现有 tag、enum、default value 等规范化逻辑继续执行。
3. 通过 `get_model_enterprise_extension().validate_attr(attr)` 进入商业版规范化。
4. 商业版规范化 `attr["governance"]`。
5. 规范化后的字段写入模型 `attrs` JSON。
6. 创建模型管理变更记录。
7. 商业版扩展补充治理标记相关 message 片段。

### 编辑字段

1. `ModelManage.update_model_attr` 读取当前字段。
2. 通过 `get_model_enterprise_extension().validate_attr(attr)` 规范化传入字段。
3. 更新字段时必须显式持久化 `governance`，不能只更新现有白名单字段。
4. 治理标记发生变化时，变更记录 message 追加治理 diff。

示例：

```text
治理标记: 关键属性 否 -> 是; 时效性 未设置 -> 需要及时更新(7天)
```

### 查询字段

现有 `attr_list` 和 `field_groups/full_info` 继续返回字段 `attrs`。

旧字段没有 `governance` 时，商业扩展和前端按默认值处理。

### 复制模型

模型复制现有逻辑会整体复制 `attrs` JSON。治理标记自然随字段复制，不需要额外同步表。

### 删除字段

删除字段时从 `attrs` 中移除整个字段对象，治理标记随字段一起消失。

## 前端代码分离

社区 CMDB 属性管理页只增加企业扩展加载点，不包含治理标记 UI。

社区默认扩展接口：

```ts
interface AttributeEnterpriseExtension {
  getExtraColumns: () => ColumnItem[];
  renderExtraFormItems: (context: AttributeFormContext) => React.ReactNode;
  normalizeInitialValues: (values: AttrFieldType) => AttrFieldType;
  normalizeSubmitValues: (values: AttrFieldType) => AttrFieldType;
}
```

社区默认实现：

```ts
{
  getExtraColumns: () => [],
  renderExtraFormItems: () => null,
  normalizeInitialValues: values => values,
  normalizeSubmitValues: values => values,
}
```

社区加载方式参考 `system-manager`：

```ts
try {
  const mod = require('@/app/cmdb/(enterprise)/hooks/useAttributeEnterpriseExtension');
  return mod.useAttributeEnterpriseExtension || useCEAttributeEnterpriseExtension;
} catch {
  return useCEAttributeEnterpriseExtension;
}
```

社区属性页只在稳定扩展点使用该能力：

- 属性表格 columns 追加企业列。
- 属性弹窗渲染企业表单区。
- 编辑回显前调用 `normalizeInitialValues`。
- 提交前调用 `normalizeSubmitValues`。

商业版前端实现位置：

```text
enterprise/web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx
```

商业版前端负责：

- 返回治理标记表格列。
- 返回治理标记表单分组。
- 定义时效性选项与展示文案。
- 处理不支持字段类型的禁用与清空逻辑。

## 前端交互

治理表单按分组展示，分组标题为“治理标记”。

位置：

- 字段类型和类型专属配置之后。
- 必填、可编辑之前。

支持治理标记的字段类型：

- 显示可编辑治理控件。
- 关键属性：是/否。
- 时效性：未设置、需要及时更新、不频繁更新、基本不变。

不支持治理标记的字段类型：

- 显示禁用态或简短提示。
- 当字段类型切换到 `attachment`、`image`、`table`、`pwd` 时清空治理表单值。
- 提交默认治理值。

属性表格商业版追加列：

- 关键属性：是/否。
- 时效性：未设置 / 需要及时更新(7天) / 不频繁更新(90天) / 基本不变(不参与判定)。

## 模型配置迁移

内部存储使用 `governance` 分组 JSON，Excel 导入导出使用平铺列，便于用户维护。

英文列：

- `governance_key_attribute`
- `governance_freshness`

中文列：

- `关键属性`
- `时效性`

导出流程：

1. 社区代码按现有逻辑生成模型字段行。
2. 调用商业扩展追加治理列。
3. 旧字段没有 `governance` 时导出默认值。
4. 无商业扩展时不追加治理列。

导入流程：

1. 社区代码按现有逻辑读取 Excel。
2. 调用商业扩展解析治理列。
3. 商业扩展把平铺列规范化为 `attr["governance"]`。
4. 导入合并已有字段时，把 `governance` 纳入可更新字段。

旧模板没有治理列时仍可正常导入。

## 校验策略

商业版后端是唯一可信校验入口。

校验规则：

- `governance` 缺失：补默认结构。
- `key_attribute` 缺失：补 `false`。
- `key_attribute` 非布尔值：拒绝。
- `freshness` 缺失：补 `""`。
- `freshness` 不在允许范围内：拒绝。
- 不支持字段类型：治理标记清空为默认结构。

错误文案：

- `关键属性标记必须为布尔值`
- `时效性标记不合法`

前端校验只用于改善体验，不能作为唯一防线。

## 测试设计

### 后端社区侧

- 未注册商业实现时，模型企业扩展保持 no-op。
- 字段新增/编辑继续调用企业扩展，不破坏现有行为。
- 旧字段没有 `governance` 时，字段查询与模型配置导出不报错。

### 后端商业侧

- 新增普通字段时补默认 `governance`。
- 新增普通字段时可保存 `key_attribute=true`。
- 新增普通字段时可保存每个合法 `freshness` 值。
- 编辑普通字段时可修改治理标记。
- `attachment`、`image`、`table`、`pwd` 字段保存后治理标记被清空。
- 非法 `freshness` 被拒绝。
- 非法 `key_attribute` 被拒绝。
- 变更记录 message 包含治理标记 diff。
- 模型配置导出包含治理列。
- 模型配置导入能解析治理列。
- 导入合并已有字段时能更新 `governance`。

### 前端社区侧

- 无企业扩展时，属性表格不出现治理列。
- 无企业扩展时，属性弹窗不出现治理标记分组。
- 无企业扩展时，提交 payload 不包含治理标记。

### 前端商业侧

- 企业扩展返回治理表格列。
- 属性弹窗渲染治理标记分组。
- 旧字段没有 `governance` 时按默认值回显。
- 支持字段类型提交 `governance`。
- 不支持字段类型禁用或清空治理标记。
- 切换到不支持字段类型时清空治理标记。
- 时效性文案包含固定窗口。

## 验证命令

后端：

```bash
cd server && make test
```

前端：

```bash
cd web && pnpm lint && pnpm type-check
```

实现过程中可以先跑聚焦测试；最终变更应通过受影响模块的质量门禁。

## 实施注意事项

- 本需求不实现第二阶段治理健康度计算。
- 本需求不实现第三阶段运营分析仪表盘展示。
- 不把整个 CMDB 属性管理页复制到企业版。
- 前端商业分离参考 `system-manager` hook 增强模式。
- 不沿用 CMDB 附件/图片字段当前在社区前端硬编码的做法。
