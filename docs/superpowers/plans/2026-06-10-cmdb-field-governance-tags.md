# CMDB Field Governance Tags Implementation Plan

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
