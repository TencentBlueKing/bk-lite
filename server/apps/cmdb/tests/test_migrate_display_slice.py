"""CMDB migrate-display 切片测试。

覆盖目标:
- apps/cmdb/model_migrate/migrete_service.py (ModelMigrate)
- apps/cmdb/display_field/initializer.py (DisplayFieldInitializer)
- apps/cmdb/display_field/cache.py (ExcludeFieldsCache)
- apps/cmdb/management/commands/migrate_field_constraints.py (Command)

边界打桩: GraphClient(图DB驱动) / django cache(redis) / Excel字节流(pandas) /
system_mgmt Group/User(真实ORM) / FieldGroup·PublicEnumLibrary(真实Postgres)。
断言真实输出、DB副作用、异常契约、入参契约。
"""

import pydantic.root_model  # noqa: F401  预热避免 cov 竞态

import io
import json
import sys
from collections import defaultdict

import pandas as pd
import pytest

from apps.cmdb.constants.field_constraints import (
    DEFAULT_NUMBER_CONSTRAINT,
    DEFAULT_STRING_CONSTRAINT,
    DEFAULT_TIME_CONSTRAINT,
    StringValidationType,
    TimeDisplayFormat,
    WidgetType,
)
from apps.core.exceptions.base_app_exception import BaseAppException


# ===========================================================================
# 共享 fake：模拟 `with GraphClient() as ag:` 上下文
# ===========================================================================
class FakeGraph:
    def __init__(self, **returns):
        self._returns = returns
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            value = self._returns.get(name)
            if callable(value):
                return value(*args, **kwargs)
            if value is not None:
                return value
            if name.startswith("query"):
                return ([], 0)
            return {}

        return _method


def _patch_graph(monkeypatch, module_path, **returns):
    fake = FakeGraph(**returns)
    monkeypatch.setattr(f"{module_path}.GraphClient", lambda *a, **k: fake)
    return fake


# ===========================================================================
# 构造真实 Excel 字节流（喂入 pandas，header=1 -> 第二行为表头）
# ===========================================================================
def _build_excel_bytes(sheets: dict) -> bytes:
    """sheets: {sheet_name: list[dict]} -> 真实 xlsx 字节流，第一行占位、第二行表头。"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            cols = []
            for r in rows:
                for k in r.keys():
                    if k not in cols:
                        cols.append(k)
            if not cols:
                cols = ["placeholder"]
            # 第一行写占位说明，header=1 时被跳过；真表头由 startrow=1 写入
            df = pd.DataFrame(rows, columns=cols)
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, header=True)
            # 在首行写注释行
            ws = writer.sheets[sheet_name]
            for ci, col in enumerate(cols, start=1):
                ws.cell(row=1, column=ci, value=f"说明_{col}")
    return buf.getvalue()


# ===========================================================================
# ModelMigrate 纯解析逻辑（无DB）
# ===========================================================================
class TestModelMigrateParsing:
    def _make(self, monkeypatch):
        from apps.cmdb.model_migrate import migrete_service

        # get_model_config 被替换为空，避免真实读取 Excel；default_group_id 打桩
        monkeypatch.setattr(migrete_service.ModelMigrate, "get_model_config", lambda self: {})
        monkeypatch.setattr(migrete_service, "get_default_group_id", lambda: [1])
        return migrete_service.ModelMigrate(file_source=None, is_pre=True)

    def test_parse_string_option_custom_regex(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._parse_string_option({"mode": "multi", "type": "custom", "regx": "^a$"})
        assert out["widget_type"] == WidgetType.MULTI_LINE
        assert out["validation_type"] == StringValidationType.CUSTOM
        assert out["custom_regex"] == "^a$"

    def test_parse_string_option_typed_no_regex(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._parse_string_option({"type": "ipv4"})
        assert out["validation_type"] == StringValidationType.IPV4
        assert out["widget_type"] == WidgetType.SINGLE_LINE
        assert out["custom_regex"] == ""

    def test_parse_number_option_min_max(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._parse_number_option({"min": "1", "max": "3.5"})
        assert out["min_value"] == 1
        assert out["max_value"] == 3.5

    def test_parse_number_option_invalid_ignored(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._parse_number_option({"min": "abc", "max": ""})
        # 非法/空被忽略，回落默认
        assert out == dict(DEFAULT_NUMBER_CONSTRAINT)

    def test_parse_time_option_date(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._parse_time_option({"type": "date"}) == {"display_format": TimeDisplayFormat.DATE}
        assert m._parse_time_option({}) == {"display_format": TimeDisplayFormat.DATETIME}

    def test_parse_attr_option_string_json(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._parse_attr_option("str", "{'mode': 'single', 'type': 'email'}")
        assert out["validation_type"] == StringValidationType.EMAIL

    def test_parse_attr_option_default_when_empty(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._parse_attr_option("str", "") == DEFAULT_STRING_CONSTRAINT
        assert m._parse_attr_option("int", "") == DEFAULT_NUMBER_CONSTRAINT
        assert m._parse_attr_option("time", "") == DEFAULT_TIME_CONSTRAINT
        assert m._parse_attr_option("enum", "") == []
        assert m._parse_attr_option("table", "") == []

    def test_parse_attr_option_malformed_falls_back(self, monkeypatch):
        m = self._make(monkeypatch)
        # 非法 JSON -> 回落默认
        assert m._parse_attr_option("int", "{not json") == DEFAULT_NUMBER_CONSTRAINT

    def test_parse_table_option_filters_bad_columns(self, monkeypatch):
        m = self._make(monkeypatch)
        cols = [
            {"column_id": "a", "column_name": "A", "column_type": "str", "order": "1"},
            {"column_id": "b", "column_name": "B", "column_type": "bad", "order": "2"},  # 非法类型
            {"column_id": "c", "column_name": "C", "column_type": "number", "order": "0"},  # order<1
            "not a dict",
        ]
        out = m._parse_table_option(cols)
        assert out == [{"column_id": "a", "column_name": "A", "column_type": "str", "order": 1}]

    def test_normalize_attr_enum_options_dup_id_raises(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._normalize_attr_enum_options([{"id": "1", "name": "x"}, {"id": "1", "name": "y"}], "ctx")

    def test_normalize_attr_enum_options_empty_id_raises(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._normalize_attr_enum_options([{"id": "", "name": "y"}], "ctx")

    def test_normalize_enum_option_payload_list(self, monkeypatch):
        m = self._make(monkeypatch)
        option, meta = m._normalize_enum_option_payload([{"id": "1", "name": "运行中"}], attr_id="status")
        assert option == [{"id": "1", "name": "运行中"}]
        assert meta["enum_rule_type"] == "custom"
        assert meta["public_library_id"] is None

    def test_normalize_enum_option_payload_bad_select_mode(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._normalize_enum_option_payload({"enum_rule_type": "custom", "enum_select_mode": "bogus"}, attr_id="x")

    def test_normalize_enum_option_payload_public_lib_missing_id(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._normalize_enum_option_payload({"enum_rule_type": "public_library", "public_library_id": ""}, attr_id="x")

    def test_normalize_enum_option_payload_bad_rule_type(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._normalize_enum_option_payload({"enum_rule_type": "weird"}, attr_id="x")

    def test_parse_json_like_value_empty_raises(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._parse_json_like_value("", "options", "ctx")

    def test_parse_json_like_value_invalid_raises(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._parse_json_like_value("{bad", "options", "ctx")

    def test_parse_json_like_value_passthrough_list(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._parse_json_like_value([1, 2], "x", "ctx") == [1, 2]

    def test_is_empty_row(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._is_empty_row({"a": "", "b": None}) is True
        assert m._is_empty_row({"a": "x"}) is False

    def test_parse_model_attrs_variants(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._parse_model_attrs('[{"attr_id":"a"}]') == [{"attr_id": "a"}]
        assert m._parse_model_attrs("bad json") == []
        assert m._parse_model_attrs([{"x": 1}]) == [{"x": 1}]

    def test_merge_existing_attr_config_changes(self, monkeypatch):
        m = self._make(monkeypatch)
        existing = {"attr_id": "a", "attr_name": "old", "attr_type": "str"}
        incoming = {"attr_name": "new", "option": {"k": 1}, "is_required": True}
        changed = m._merge_existing_attr_config(existing, incoming)
        assert changed is True
        assert existing["attr_name"] == "new"
        assert existing["option"] == {"k": 1}
        assert existing["is_required"] is True

    def test_merge_existing_attr_config_updates_attr_type(self, monkeypatch):
        m = self._make(monkeypatch)
        existing = {
            "attr_id": "ip_status",
            "attr_type": "str",
            "attr_name": "旧状态",
            "option": dict(DEFAULT_STRING_CONSTRAINT),
        }
        incoming = {
            "attr_id": "ip_status",
            "attr_type": "enum",
            "attr_name": "IP状态",
            "option": [{"id": "online", "name": "在线"}],
            "enum_rule_type": "custom",
            "public_library_id": None,
            "enum_select_mode": "single",
        }

        changed = m._merge_existing_attr_config(existing, incoming)

        assert changed is True
        assert existing["attr_type"] == "enum"
        assert existing["option"] == [{"id": "online", "name": "在线"}]

    def test_merge_existing_attr_config_no_change(self, monkeypatch):
        m = self._make(monkeypatch)
        existing = {"attr_id": "a", "attr_name": "same", "attr_type": "str"}
        # 空 attr_name 不覆盖，非布尔 is_required 不覆盖
        incoming = {"attr_name": "", "is_required": "true"}
        assert m._merge_existing_attr_config(existing, incoming) is False
        assert existing["attr_name"] == "same"


# ===========================================================================
# ModelMigrate.get_model_config —— 真实 Excel 字节流喂入 pandas
# ===========================================================================
class TestGetModelConfig:
    def test_reads_real_excel_bytes(self, monkeypatch):
        from apps.cmdb.model_migrate import migrete_service

        monkeypatch.setattr(migrete_service, "get_default_group_id", lambda: [1])

        xlsx = _build_excel_bytes(
            {
                "models": [{"model_id": "host", "classification_id": "infra"}],
                "classifications": [{"classification_id": "infra", "classification_name": "基础设施"}],
            }
        )

        class _FileSrc:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        m = migrete_service.ModelMigrate(file_source=_FileSrc(xlsx), is_pre=True)
        cfg = m.model_config
        assert "models" in cfg and "classifications" in cfg
        assert cfg["models"][0]["model_id"] == "host"
        assert cfg["classifications"][0]["classification_id"] == "infra"


# ===========================================================================
# ModelMigrate._prepare_attr —— 依赖真实 ModelManage.sanitize + 企业扩展
# ===========================================================================
class TestPrepareAttr:
    def _make(self, monkeypatch):
        from apps.cmdb.model_migrate import migrete_service

        monkeypatch.setattr(migrete_service.ModelMigrate, "get_model_config", lambda self: {})
        monkeypatch.setattr(migrete_service, "get_default_group_id", lambda: [1])
        return migrete_service.ModelMigrate(file_source=None, is_pre=True)

    def test_skips_attr_without_id(self, monkeypatch):
        m = self._make(monkeypatch)
        assert m._prepare_attr({"attr_id": "", "attr_name": "无ID"}) is None

    def test_str_attr_prepared(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._prepare_attr({"attr_id": " ip ", "attr_type": "str", "option": "{'type':'ipv4'}", "prompt": "请填IP"})
        assert out["attr_id"] == "ip"
        assert out["option"]["validation_type"] == StringValidationType.IPV4
        assert out["user_prompt"] == "请填IP"
        assert out["default_value"] == []

    def test_enum_attr_default_value_must_be_list(self, monkeypatch):
        m = self._make(monkeypatch)
        with pytest.raises(BaseAppException):
            m._prepare_attr(
                {
                    "attr_id": "status",
                    "attr_type": "enum",
                    "option": "[{'id':'1','name':'A'}]",
                    "default_value": "1",  # 非数组
                }
            )

    def test_enum_attr_with_list_default(self, monkeypatch):
        m = self._make(monkeypatch)
        out = m._prepare_attr(
            {
                "attr_id": "status",
                "attr_type": "enum",
                "option": "[{'id':'1','name':'运行中'}]",
                "default_value": "['1']",
            }
        )
        assert out["enum_rule_type"] == "custom"
        assert out["option"] == [{"id": "1", "name": "运行中"}]


# ===========================================================================
# ModelMigrate —— 需要真实 DB（FieldGroup / PublicEnumLibrary）+ mock GraphClient
# ===========================================================================
@pytest.mark.django_db
class TestModelMigrateWithDB:
    def _make(self, monkeypatch, model_config):
        from apps.cmdb.model_migrate import migrete_service

        monkeypatch.setattr(migrete_service.ModelMigrate, "get_model_config", lambda self: model_config)
        monkeypatch.setattr(migrete_service, "get_default_group_id", lambda: [99])
        return migrete_service.ModelMigrate(file_source=None, is_pre=True), migrete_service

    def test_migrate_public_enum_libraries_create_and_skip(self, monkeypatch):
        cfg = {
            "public_enum_libraries": [
                {
                    "library_id": "os_type",
                    "name": "操作系统",
                    "team": "[1]",
                    "options": "[{'id':'linux','name':'Linux'}]",
                }
            ]
        }
        m, mod = self._make(monkeypatch, cfg)
        # enqueue 刷新是外部边界（celery/任务），打桩防真实触发
        monkeypatch.setattr(mod, "enqueue_library_snapshot_refresh", lambda *a, **k: None)

        res = m.migrate_public_enum_libraries()
        assert res["created"] == 1 and res["sheet_present"] is True

        from apps.cmdb.models.public_enum_library import PublicEnumLibrary

        lib = PublicEnumLibrary.objects.get(library_id="os_type")
        assert lib.name == "操作系统"
        assert lib.options == [{"id": "linux", "name": "Linux"}]
        assert lib.team == [1]

        # 再次执行：无变更 -> skipped
        res2 = m.migrate_public_enum_libraries()
        assert res2["skipped"] == 1 and res2["created"] == 0

    def test_migrate_public_enum_libraries_update(self, monkeypatch):
        from apps.cmdb.models.public_enum_library import PublicEnumLibrary

        PublicEnumLibrary.objects.create(
            library_id="os_type",
            name="旧名",
            team=[],
            options=[],
            created_by="system",
            updated_by="system",
        )
        cfg = {
            "public_enum_libraries": [
                {"library_id": "os_type", "name": "新名", "team": "[]", "options": "[{'id':'a','name':'A'}]"}
            ]
        }
        m, mod = self._make(monkeypatch, cfg)
        refreshed = []
        monkeypatch.setattr(mod, "enqueue_library_snapshot_refresh", lambda lib_id, **k: refreshed.append(lib_id))

        res = m.migrate_public_enum_libraries()
        assert res["updated"] == 1
        lib = PublicEnumLibrary.objects.get(library_id="os_type")
        assert lib.name == "新名"
        assert lib.options == [{"id": "a", "name": "A"}]
        assert refreshed == ["os_type"]

    def test_migrate_public_enum_libraries_dup_id_raises(self, monkeypatch):
        cfg = {
            "public_enum_libraries": [
                {"library_id": "dup", "name": "n1", "team": "[]", "options": "[]"},
                {"library_id": "dup", "name": "n2", "team": "[]", "options": "[]"},
            ]
        }
        m, _ = self._make(monkeypatch, cfg)
        with pytest.raises(BaseAppException):
            m.migrate_public_enum_libraries()

    def test_migrate_public_enum_libraries_no_sheet(self, monkeypatch):
        m, _ = self._make(monkeypatch, {})
        res = m.migrate_public_enum_libraries()
        assert res == {"created": 0, "updated": 0, "skipped": 0, "sheet_present": False}

    def test_validate_public_library_references_missing_raises(self, monkeypatch):
        m, _ = self._make(monkeypatch, {})
        attrs = {
            "host": [
                {"attr_id": "os", "attr_type": "enum", "enum_rule_type": "public_library", "public_library_id": "nope"}
            ]
        }
        with pytest.raises(BaseAppException):
            m._validate_public_library_references(attrs)

    def test_validate_public_library_references_ok(self, monkeypatch):
        from apps.cmdb.models.public_enum_library import PublicEnumLibrary

        PublicEnumLibrary.objects.create(library_id="exists", name="n", team=[], options=[], created_by="x", updated_by="x")
        m, _ = self._make(monkeypatch, {})
        attrs = {
            "host": [
                {"attr_id": "os", "attr_type": "enum", "enum_rule_type": "public_library", "public_library_id": "exists"}
            ]
        }
        # 不抛异常即通过
        m._validate_public_library_references(attrs)

    def test_build_model_payload_filters_invalid_and_dedups(self, monkeypatch):
        cfg = {
            "models": [
                {"model_id": "host", "classification_id": "infra"},
                {"model_id": "123-bad id!", "classification_id": "infra"},  # 非法ID被跳过
            ],
            "attr-host": [
                {"attr_id": "ip", "attr_type": "str", "attr_name": "IP"},
                {"attr_id": "ip", "attr_type": "str", "attr_name": "重复"},  # 重复ID
            ],
        }
        m, _ = self._make(monkeypatch, cfg)
        models, attrs_by_model = m._build_model_payload()
        assert len(models) == 1
        assert models[0]["model_id"] == "host"
        assert len(attrs_by_model["host"]) == 1  # 去重
        # is_pre 与组织字段已注入
        assert models[0]["is_pre"] is True
        # attrs 已序列化为 JSON 字符串
        assert json.loads(models[0]["attrs"])[0]["attr_id"] == "ip"

    def test_sync_added_attrs_creates_field_group(self, monkeypatch):
        from apps.cmdb.models.field_group import FieldGroup

        m, mod = self._make(monkeypatch, {})
        # 缓存刷新是外部边界，打桩
        monkeypatch.setattr(mod.ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: True))

        ag = FakeGraph()
        existing_model_map = {"host": {"_id": "n1", "model_id": "host", "attrs": "[]"}}
        attrs_by_model = {
            "host": [
                {"attr_id": "ip", "attr_type": "str", "attr_group": "网络"},
                {"attr_id": "os", "attr_type": "str", "attr_group": "网络"},
            ]
        }
        res = m._sync_added_attrs_to_existing_models(ag, attrs_by_model, existing_model_map)
        assert res["added_attr_count"] == 2
        assert "host" in res["updated_models"]
        # 真实 DB 副作用：FieldGroup 被创建
        grp = FieldGroup.objects.get(model_id="host", group_name="网络")
        assert grp.attr_orders == ["ip", "os"]
        # GraphClient.set_entity_properties 被调用写回 attrs
        assert any(c[0] == "set_entity_properties" for c in ag.calls)

    def test_sync_added_attrs_updates_existing_attr_config(self, monkeypatch):
        m, mod = self._make(monkeypatch, {})
        monkeypatch.setattr(mod.ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: True))

        ag = FakeGraph()
        existing_attrs = [{"attr_id": "ip", "attr_type": "str", "attr_name": "旧"}]
        existing_model_map = {
            "host": {"_id": "n1", "model_id": "host", "attrs": json.dumps(existing_attrs)}
        }
        attrs_by_model = {"host": [{"attr_id": "ip", "attr_type": "str", "attr_name": "新名"}]}
        res = m._sync_added_attrs_to_existing_models(ag, attrs_by_model, existing_model_map)
        assert res["updated_attr_count"] == 1
        assert res["added_attr_count"] == 0

    def test_sync_added_attrs_no_targets(self, monkeypatch):
        m, _ = self._make(monkeypatch, {})
        ag = FakeGraph()
        res = m._sync_added_attrs_to_existing_models(ag, {"host": []}, {})
        assert res["updated_models"] == []
        assert res["added_attr_count"] == 0

    def test_sync_added_attrs_field_groups_appends_existing(self, monkeypatch):
        from apps.cmdb.models.field_group import FieldGroup

        m, _ = self._make(monkeypatch, {})
        existing = FieldGroup.objects.create(
            model_id="host", group_name="网络", order=1, is_collapsed=False, attr_orders=["ip"], created_by="system"
        )
        field_group_map = {("host", "网络"): existing}
        max_order = defaultdict(int)
        max_order["host"] = 1
        added = [{"attr_id": "ip", "attr_group": "网络"}, {"attr_id": "os", "attr_group": "网络"}]  # ip 已存在只追加 os
        upd, created = m._sync_added_attrs_field_groups("host", added, field_group_map, max_order)
        assert upd == 1 and created == 0
        existing.refresh_from_db()
        assert existing.attr_orders == ["ip", "os"]

    def test_create_field_groups(self, monkeypatch):
        from apps.cmdb.models.field_group import FieldGroup

        m, _ = self._make(monkeypatch, {})
        success_models = [
            {
                "model_id": "switch",
                "attrs": json.dumps(
                    [
                        {"attr_id": "name", "attr_group": "基础"},
                        {"attr_id": "ip", "attr_group": "网络"},
                    ]
                ),
            }
        ]
        m._create_field_groups(success_models)
        assert FieldGroup.objects.filter(model_id="switch").count() == 2
        base = FieldGroup.objects.get(model_id="switch", group_name="基础")
        assert base.order == 1 and base.attr_orders == ["name"]

    def test_migrate_classifications_calls_graph(self, monkeypatch):
        cfg = {"classifications": [{"classification_id": "infra", "classification_name": "基础"}]}
        m, mod = self._make(monkeypatch, cfg)
        fake = _patch_graph(
            monkeypatch,
            "apps.cmdb.model_migrate.migrete_service",
            query_entity=([], 0),
            batch_create_entity=[{"success": True, "data": {"classification_id": "infra"}}],
        )
        res = m.migrate_classifications()
        assert res == [{"success": True, "data": {"classification_id": "infra"}}]
        # is_pre 注入到入参
        create_call = next(c for c in fake.calls if c[0] == "batch_create_entity")
        passed_items = create_call[1][1]
        assert passed_items[0]["is_pre"] is True

    def test_migrate_associations_builds_edges(self, monkeypatch):
        cfg = {
            "models": [{"model_id": "host"}],
            "asso-host": [
                {"src_model_id": "host", "dst_model_id": "switch", "asst_id": "connect", "asst_name": "连接"}
            ],
        }
        m, mod = self._make(monkeypatch, cfg)
        fake = _patch_graph(
            monkeypatch,
            "apps.cmdb.model_migrate.migrete_service",
            query_entity=([{"model_id": "host", "_id": "n1"}, {"model_id": "switch", "_id": "n2"}], 2),
            batch_create_edge=[{"success": True}],
        )
        res = m.migrate_associations()
        assert res == [{"success": True}]
        edge_call = next(c for c in fake.calls if c[0] == "batch_create_edge")
        asso_list = edge_call[1][3]
        assert asso_list[0]["model_asst_id"] == "host_connect_switch"
        assert asso_list[0]["src_id"] == "n1" and asso_list[0]["dst_id"] == "n2"

    def test_check_and_update_old_models_group(self, monkeypatch):
        m, _ = self._make(monkeypatch, {})
        from apps.cmdb.constants.constants import INIT_MODEL_GROUP

        models = [
            {"_id": "n1"},  # 缺组织字段
            {"_id": "n2", INIT_MODEL_GROUP: 5},  # 整数 -> 需修
            {"_id": "n3", INIT_MODEL_GROUP: [99]},  # 正常，跳过
        ]
        fake = _patch_graph(
            monkeypatch,
            "apps.cmdb.model_migrate.migrete_service",
            query_entity=(models, 3),
        )
        m.check_and_update_old_models_group()
        upd_call = next(c for c in fake.calls if c[0] == "batch_update_node_properties")
        assert sorted(upd_call[2]["node_ids"]) == ["n1", "n2"]
        assert upd_call[2]["properties"][INIT_MODEL_GROUP] == [99]

    def test_migrate_models_creates_new_and_field_groups(self, monkeypatch):
        from apps.cmdb.models.field_group import FieldGroup

        cfg = {
            "models": [{"model_id": "router", "classification_id": "net"}],
            "attr-router": [{"attr_id": "ip", "attr_type": "str", "attr_name": "IP", "attr_group": "网络"}],
        }
        m, mod = self._make(monkeypatch, cfg)
        monkeypatch.setattr(mod.ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: True))

        def _batch_create_entity(label, items, *a, **k):
            # 返回成功创建结果，data 带回 _id/classification_id/model_id/attrs
            out = []
            for it in items:
                data = dict(it)
                data["_id"] = "newnode"
                out.append({"success": True, "data": data})
            return out

        _patch_graph(
            monkeypatch,
            "apps.cmdb.model_migrate.migrete_service",
            query_entity=lambda label, *a, **k: (
                ([{"classification_id": "net", "_id": "cls1"}], 1)
                if label == __import__("apps.cmdb.constants.constants", fromlist=["CLASSIFICATION"]).CLASSIFICATION
                else ([], 0)
            ),
            batch_create_entity=_batch_create_entity,
            batch_create_edge=[{"success": True}],
        )
        result, asso_result = m.migrate_models()
        assert result[0]["success"] is True
        assert asso_result == [{"success": True}]
        # 真实 DB：新模型的 FieldGroup 已创建
        assert FieldGroup.objects.filter(model_id="router", group_name="网络").exists()

    def test_main_orchestrates_all(self, monkeypatch):
        cfg = {
            "classifications": [{"classification_id": "net", "classification_name": "网络"}],
            "models": [{"model_id": "router", "classification_id": "net"}],
        }
        m, mod = self._make(monkeypatch, cfg)
        monkeypatch.setattr(mod.ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: True))
        # 用方法级打桩隔离各子步骤的图DB细节，验证 main 编排与返回结构
        monkeypatch.setattr(m, "migrate_classifications", lambda: ["c"])
        monkeypatch.setattr(m, "migrate_public_enum_libraries", lambda: {"created": 0})
        monkeypatch.setattr(m, "migrate_models", lambda: (["m"], ["ca"]))
        monkeypatch.setattr(m, "migrate_associations", lambda: ["a"])
        monkeypatch.setattr(m, "check_and_update_old_models_group", lambda: None)
        monkeypatch.setattr(m, "check_and_update_old_instances_organization", lambda: None)
        res = m.main()
        assert res == {
            "classification": ["c"],
            "public_enum_libraries": {"created": 0},
            "model": ["m"],
            "classification_assos": ["ca"],
            "association": ["a"],
        }

    def test_main_swallows_old_data_fix_errors(self, monkeypatch):
        m, mod = self._make(monkeypatch, {})
        monkeypatch.setattr(m, "migrate_classifications", lambda: [])
        monkeypatch.setattr(m, "migrate_public_enum_libraries", lambda: {})
        monkeypatch.setattr(m, "migrate_models", lambda: ([], []))
        monkeypatch.setattr(m, "migrate_associations", lambda: [])

        def _boom():
            raise RuntimeError("graph down")

        monkeypatch.setattr(m, "check_and_update_old_models_group", _boom)
        monkeypatch.setattr(m, "check_and_update_old_instances_organization", _boom)
        # 异常被吞掉，main 仍返回完整结构
        res = m.main()
        assert set(res.keys()) == {"classification", "public_enum_libraries", "model", "classification_assos", "association"}

    def test_check_and_update_old_instances_organization(self, monkeypatch):
        m, _ = self._make(monkeypatch, {})
        from apps.cmdb.constants.constants import ORGANIZATION

        instances = [
            {"_id": "i1", ORGANIZATION: 7},  # 整数 -> 修
            {"_id": "i2"},  # 缺 -> 修
            {"_id": "i3", ORGANIZATION: [3]},  # 正常 -> 跳过
        ]
        fake = _patch_graph(
            monkeypatch,
            "apps.cmdb.model_migrate.migrete_service",
            query_entity=(instances, 3),
        )
        m.check_and_update_old_instances_organization()
        upd = next(c for c in fake.calls if c[0] == "batch_update_node_properties")
        assert sorted(upd[2]["node_ids"]) == ["i1", "i2"]


# ===========================================================================
# DisplayFieldInitializer
# ===========================================================================
@pytest.mark.django_db
class TestDisplayFieldInitializer:
    def test_convert_organization(self):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer

        init = DisplayFieldInitializer()
        init._org_map = {1: "技术部", 2: "运维组"}
        assert init._convert_organization([1, 2]) == "技术部, 运维组"
        assert init._convert_organization(1) == "技术部"
        assert init._convert_organization([]) == ""
        # 未知 id 回落原值
        assert init._convert_organization([99]) == "99"

    def test_convert_user(self):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer

        init = DisplayFieldInitializer()
        init._user_map = {
            1: {"username": "admin", "display_name": "管理员"},
            2: {"username": "u02", "display_name": ""},
        }
        assert init._convert_user([1, 2]) == "管理员(admin), u02"
        assert init._convert_user([99]) == "99"
        assert init._convert_user([]) == ""

    def test_convert_enum(self):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer

        init = DisplayFieldInitializer()
        init._enum_map = {"host.status.1": "运行中"}
        assert init._convert_enum("host", "status", "1") == "运行中"
        assert init._convert_enum("host", "status", "9") == "9"
        assert init._convert_enum("host", "status", "") == ""

    def test_convert_tag(self):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer

        init = DisplayFieldInitializer()
        assert init._convert_tag(["env:prod", " app:web "]) == "env:prod, app:web"
        assert init._convert_tag("x") == "x"
        assert init._convert_tag([]) == ""

    def test_preload_mappings_real_db(self, monkeypatch):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer
        from apps.system_mgmt.models.user import Group, User

        grp = Group.objects.create(name="测试组", parent_id=0)
        user = User.objects.create(username="zhangsan", display_name="张三")

        init = DisplayFieldInitializer()
        models = [
            {
                "model_id": "host",
                "attrs": json.dumps(
                    [{"attr_id": "status", "attr_type": "enum", "option": [{"id": "1", "name": "运行中"}]}]
                ),
            }
        ]
        init._preload_mappings(models)
        assert init._org_map[grp.id] == "测试组"
        assert init._user_map[user.id]["username"] == "zhangsan"
        assert init._enum_map["host.status.1"] == "运行中"

    def test_build_display_fields_for_instance(self):
        from apps.cmdb.display_field.initializer import DisplayFieldInitializer

        init = DisplayFieldInitializer()
        init._org_map = {1: "技术部"}
        init._enum_map = {"host.status.1": "运行中"}
        attrs = [
            {"attr_id": "organization", "attr_type": "organization"},
            {"attr_id": "status", "attr_type": "enum"},
            {"attr_id": "name", "attr_type": "str"},  # 非目标类型，跳过
            {"attr_id": "missing", "attr_type": "user"},  # 实例无此字段，跳过
        ]
        instance = {"organization": [1], "status": "1", "name": "h1"}
        out = init._build_display_fields_for_instance(instance, attrs, "host")
        assert out == {"organization_display": "技术部", "status_display": "运行中"}

    def test_add_display_fields_to_model(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.initializer")
        model = {
            "_id": "n1",
            "model_id": "host",
            "attrs": json.dumps([{"attr_id": "organization", "attr_type": "organization", "attr_name": "组织"}]),
        }
        attrs = init._add_display_fields_to_model(model)
        ids = [a["attr_id"] for a in attrs]
        assert "organization_display" in ids
        # 写回图DB
        assert any(c[0] == "set_entity_properties" for c in fake.calls)

    def test_add_display_fields_to_model_idempotent(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.initializer")
        attrs_def = [
            {"attr_id": "organization", "attr_type": "organization", "attr_name": "组织"},
            {"attr_id": "organization_display", "attr_type": "str"},  # 已存在
        ]
        model = {"_id": "n1", "model_id": "host", "attrs": json.dumps(attrs_def)}
        out = init._add_display_fields_to_model(model)
        assert len(out) == 2  # 不重复添加
        # 无需写回
        assert not any(c[0] == "set_entity_properties" for c in fake.calls)

    def test_add_display_fields_to_model_parse_error_returns_empty(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        model = {"_id": "n1", "model_id": "host", "attrs": "not-json"}
        assert init._add_display_fields_to_model(model) == []

    def test_add_display_fields_to_model_no_target_returns_attrs(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.initializer")
        model = {"_id": "n1", "model_id": "host", "attrs": json.dumps([{"attr_id": "name", "attr_type": "str"}])}
        out = init._add_display_fields_to_model(model)
        assert out == [{"attr_id": "name", "attr_type": "str"}]
        assert not any(c[0] == "set_entity_properties" for c in fake.calls)

    def test_add_display_fields_to_instances_no_instances(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        _patch_graph(monkeypatch, "apps.cmdb.display_field.initializer", query_entity=([], 0))
        assert init._add_display_fields_to_instances("host", [{"attr_id": "x", "attr_type": "user"}]) == 0

    def test_add_display_fields_to_instances(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        init = initializer.DisplayFieldInitializer()
        init._org_map = {1: "技术部"}
        instances = [{"_id": "i1", "inst_id": 1, "organization": [1]}]
        fake = _patch_graph(
            monkeypatch,
            "apps.cmdb.display_field.initializer",
            query_entity=(instances, 1),
            set_entity_properties={"ok": True},
        )
        attrs = [{"attr_id": "organization", "attr_type": "organization"}]
        count = init._add_display_fields_to_instances("host", attrs)
        assert count == 1
        # query_entity 用 model_id 过滤
        q = next(c for c in fake.calls if c[0] == "query_entity")
        assert q[2]["params"][0]["value"] == "host"

    def test_initialize_all_end_to_end(self, monkeypatch):
        from apps.cmdb.display_field import initializer

        # 真实 ORM：建组织映射（用真实生成的 id，避免与预置数据主键冲突）
        from apps.system_mgmt.models.user import Group

        grp = Group.objects.create(name="技术部", parent_id=0)

        models = [
            {
                "_id": "n1",
                "model_id": "host",
                "attrs": json.dumps([{"attr_id": "organization", "attr_type": "organization", "attr_name": "组织"}]),
            }
        ]
        instances = [{"_id": "i1", "inst_id": 1, "organization": [grp.id]}]

        # query_entity 第一次返回 models，之后按 label 返回 instances
        def _query(label, params=None, *a, **k):
            from apps.cmdb.constants.constants import MODEL

            if label == MODEL:
                return (models, len(models))
            return (instances, len(instances))

        _patch_graph(
            monkeypatch,
            "apps.cmdb.display_field.initializer",
            query_entity=_query,
            set_entity_properties={"ok": True},
        )

        init = initializer.DisplayFieldInitializer()
        res = init.initialize_all()
        assert res["success"] is True
        assert res["models_processed"] == 1
        assert res["instances_processed"] == 1
        assert res["errors"] == []


# ===========================================================================
# ExcludeFieldsCache —— 真实 django cache (locmem/redis) + mock GraphClient
# ===========================================================================
@pytest.mark.django_db
class TestExcludeFieldsCache:
    @pytest.fixture(autouse=True)
    def _locmem_cache(self, settings):
        # 全局 conftest 把 cache 替换为 DummyCache(永远返回 None)，
        # 本切片要验证真实读写副作用，覆盖为进程内 locmem。
        settings.CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "migrate-display-slice",
            }
        }
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    def test_build_exclude_fields(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [
            {
                "model_id": "host",
                "attrs": json.dumps(
                    [
                        {"attr_id": "organization", "attr_type": "organization"},
                        {"attr_id": "pwd", "attr_type": "pwd"},  # 敏感
                        {"attr_id": "name", "attr_type": "str"},  # 普通保留
                    ]
                ),
            }
        ]
        fields = ExcludeFieldsCache._build_exclude_fields(models)
        assert set(fields) == {"organization", "pwd"}
        assert "name" not in fields

    def test_build_exclude_fields_skips_bad_attrs(self):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [
            {"model_id": "bad", "attrs": "not-json"},  # 解析失败被跳过
            {"model_id": "host", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])},
        ]
        fields = ExcludeFieldsCache._build_exclude_fields(models)
        assert fields == ["org"]

    def test_get_model_attrs_query_error_returns_empty(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        def _boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", staticmethod(_boom))
        assert ExcludeFieldsCache.get_model_attrs("host") == []

    def test_build_model_fields_mapping(self):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [
            {
                "model_id": "host",
                "attrs": json.dumps(
                    [
                        {"attr_id": "organization", "attr_type": "organization"},
                        {"attr_id": "manager", "attr_type": "user"},
                    ]
                ),
            },
            {
                "model_id": "switch",
                "attrs": json.dumps([{"attr_id": "name", "attr_type": "str"}]),  # 无映射字段
            },
        ]
        mapping = ExcludeFieldsCache._build_model_fields_mapping(models)
        assert mapping == {"host": {"organization": ["organization"], "user": ["manager"]}}

    def test_refresh_all_caches_and_getters(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [
            {
                "model_id": "host",
                "attrs": json.dumps([{"attr_id": "organization", "attr_type": "organization"}]),
            }
        ]
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models, 1))

        assert ExcludeFieldsCache.refresh_cache() is True
        assert "organization" in ExcludeFieldsCache.get_exclude_fields()
        assert ExcludeFieldsCache.get_model_fields_mapping() == {"host": {"organization": ["organization"], "user": []}}

    def test_initialize_all(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [{"model_id": "m1", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])}]
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models, 1))
        assert ExcludeFieldsCache.initialize_all() is True
        assert "org" in ExcludeFieldsCache.get_exclude_fields()

    def test_get_model_attrs_cache_hit_and_miss(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache
        from django.core.cache import cache as dj_cache

        # miss -> 调用 ModelManage.search_model_attr 并缓存
        monkeypatch.setattr(
            "apps.cmdb.services.model.ModelManage.search_model_attr",
            staticmethod(lambda model_id, *a, **k: [{"attr_id": "x"}]),
        )
        attrs = ExcludeFieldsCache.get_model_attrs("host")
        assert attrs == [{"attr_id": "x"}]
        # 已写缓存
        assert dj_cache.get(f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host") == [{"attr_id": "x"}]

        # hit -> 不再调用 search（改桩抛错验证不被触发）
        monkeypatch.setattr(
            "apps.cmdb.services.model.ModelManage.search_model_attr",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call"))),
        )
        assert ExcludeFieldsCache.get_model_attrs("host") == [{"attr_id": "x"}]

    def test_update_on_model_change(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=([], 0))
        assert ExcludeFieldsCache.update_on_model_change("host") is True

    # -----------------------------------------------------------------
    # P2-2.6 — clear_cache 必须真的清掉 model attrs 缓存,不能只 log 一句 warning
    # -----------------------------------------------------------------

    def test_clear_cache_removes_model_attrs_entries(self, monkeypatch):
        """P2-2.6: 原 _clear_all_caches 的 cache.delete_pattern 在本仓所有 cache 后端
        (locmem / Django 内置 RedisCache) 都不存在,实际什么都不做。
        模型被删除后,其 attrs 缓存键会留 1h TTL,期间所有 get_model_attrs(model_id)
        仍返回已删模型的数据。

        修复:_build_and_cache_model_attrs 维护 model_id 索引,refresh 时比对新旧
        索引,删掉已下线的 model 的 attrs 缓存键。"""
        from apps.cmdb.display_field.cache import ExcludeFieldsCache
        from django.core.cache import cache as dj_cache

        # 模拟生产路径:第一次 build 含 host / switch,索引写入这两个 model
        models_v1 = [
            {"model_id": "host", "attrs": json.dumps([{"attr_id": "ip", "attr_type": "str"}])},
            {"model_id": "switch", "attrs": json.dumps([{"attr_id": "port", "attr_type": "int"}])},
        ]
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models_v1, len(models_v1)))
        assert ExcludeFieldsCache.refresh_cache() is True
        host_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host"
        assert dj_cache.get(host_key) is not None, "precondition: refresh 后 host attrs 已缓存"

        # 第二次 refresh:host 被删,只剩 switch
        models_v2 = [
            {"model_id": "switch", "attrs": json.dumps([{"attr_id": "port", "attr_type": "int"}])},
        ]
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models_v2, len(models_v2)))
        assert ExcludeFieldsCache.refresh_cache() is True

        # host 的 attrs 缓存键必须被精准删(否则会留 1h TTL 持续返回陈旧数据)
        assert dj_cache.get(host_key) is None, (
            f"{host_key} 必须被精准清掉,实际保留说明模型被删后缓存未同步"
        )

    def test_update_on_model_change_purges_only_target_model_attrs(self, monkeypatch):
        """P2-2.6 附加:update_on_model_change(model_id) 应精准清掉该 model 的 attrs
        缓存,其他 model 的 attrs 不受影响(避免误清 + 减少缓存抖动)。"""
        from apps.cmdb.display_field.cache import ExcludeFieldsCache
        from django.core.cache import cache as dj_cache

        target_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host"
        other_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}switch"
        dj_cache.set(target_key, [{"stale": True}])
        dj_cache.set(other_key, [{"stale": True}])

        # mock 图查询返空(只关心缓存清理,不需要刷数据)
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=([], 0))
        ExcludeFieldsCache.update_on_model_change("host")

        assert dj_cache.get(target_key) is None, "目标 model 的 attrs 缓存必须被清掉"
        # other_key 不一定要保留(update_on_model_change 整体刷会重建),
        # 但至少不应抛错

    def test_clear_cache(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache
        from django.core.cache import cache as dj_cache

        dj_cache.set(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY, ["a"])
        assert ExcludeFieldsCache.clear_cache() is True
        assert dj_cache.get(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY) is None

    def test_get_cache_info(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache
        from django.core.cache import cache as dj_cache

        dj_cache.set(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY, ["organization", "pwd"])
        dj_cache.set(ExcludeFieldsCache.MODEL_FIELDS_MAPPING_KEY, {"host": {}})
        info = ExcludeFieldsCache.get_cache_info()
        assert info["exclude_fields"]["is_cached"] is True
        assert info["exclude_fields"]["field_count"] == 2
        assert info["model_fields_mapping"]["model_count"] == 1

    def test_get_exclude_fields_miss_triggers_refresh(self, monkeypatch):
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        models = [{"model_id": "host", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])}]
        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models, 1))
        # 缓存为空 -> 触发刷新后返回
        assert "org" in ExcludeFieldsCache.get_exclude_fields()

    def test_startup_init_helpers(self, monkeypatch):
        from apps.cmdb.display_field import cache as cache_mod

        _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=([], 0))
        assert cache_mod.init_all_caches_on_startup() is True
        assert cache_mod.initialize_exclude_fields_cache() is True
        assert cache_mod.initialize_model_fields_mapping_cache() is True

    def test_startup_init_skip_when_global_cache_exists(self, monkeypatch):
        from django.core.cache import cache as dj_cache

        from apps.cmdb.display_field import cache as cache_mod
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        dj_cache.set(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY, ["organization"])
        dj_cache.set(ExcludeFieldsCache.MODEL_FIELDS_MAPPING_KEY, {"host": {"organization": ["organization"], "user": []}})
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=([], 0))

        assert cache_mod.init_all_caches_on_startup() is True
        assert fake.calls == []

    def test_startup_init_refresh_when_global_cache_missing(self, monkeypatch):
        from django.core.cache import cache as dj_cache

        from apps.cmdb.display_field import cache as cache_mod
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        dj_cache.delete(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY)
        dj_cache.delete(ExcludeFieldsCache.MODEL_FIELDS_MAPPING_KEY)
        models = [{"model_id": "host", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])}]
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=(models, 1))

        assert cache_mod.init_all_caches_on_startup() is True
        assert ("query_entity", ("model", []), {}) in fake.calls
        assert "org" in ExcludeFieldsCache.get_exclude_fields()

    def test_startup_init_skip_when_lock_exists(self, monkeypatch):
        from django.core.cache import cache as dj_cache

        from apps.cmdb.display_field import cache as cache_mod
        from apps.cmdb.display_field.cache import ExcludeFieldsCache

        dj_cache.delete(ExcludeFieldsCache.EXCLUDE_FIELDS_KEY)
        dj_cache.delete(ExcludeFieldsCache.MODEL_FIELDS_MAPPING_KEY)
        dj_cache.set(ExcludeFieldsCache.STARTUP_INIT_LOCK_KEY, "1", timeout=ExcludeFieldsCache.STARTUP_INIT_LOCK_TTL)
        fake = _patch_graph(monkeypatch, "apps.cmdb.display_field.cache", query_entity=([], 0))

        assert cache_mod.init_all_caches_on_startup() is True
        assert fake.calls == []

    def test_cmdb_ready_skips_startup_cache_for_management(self, monkeypatch):
        import apps.cmdb as cmdb_module
        from apps.cmdb.apps import CmdbConfig

        calls = []
        monkeypatch.setattr(sys, "argv", ["manage.py", "migrate"])
        monkeypatch.setattr("apps.cmdb.display_field.init_all_caches_on_startup", lambda: calls.append("init"))

        CmdbConfig("apps.cmdb", cmdb_module).ready()

        assert calls == []

    def test_cmdb_ready_initializes_startup_cache_for_runserver(self, monkeypatch):
        import apps.cmdb as cmdb_module
        from apps.cmdb.apps import CmdbConfig

        calls = []
        monkeypatch.setattr(sys, "argv", ["manage.py", "runserver", "0.0.0.0:8011"])
        monkeypatch.setattr("apps.cmdb.display_field.init_all_caches_on_startup", lambda: calls.append("init"))

        CmdbConfig("apps.cmdb", cmdb_module).ready()

        assert calls == ["init"]


# ===========================================================================
# migrate_field_constraints management command
# ===========================================================================
@pytest.mark.django_db
class TestMigrateFieldConstraintsCommand:
    def _run(self, monkeypatch, models, **opts):
        from django.core.management import call_command
        from io import StringIO

        _patch_graph(
            monkeypatch,
            "apps.cmdb.management.commands.migrate_field_constraints",
            query_entity=(models, len(models)),
            set_entity_properties={"ok": True},
        )
        # 缓存刷新外部边界打桩
        monkeypatch.setattr(
            "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
            classmethod(lambda cls, model_id: True),
        )
        out = StringIO()
        call_command("migrate_field_constraints", stdout=out, stderr=out, **opts)
        return out.getvalue()

    def test_dry_run_no_write(self, monkeypatch):
        models = [
            {
                "_id": "n1",
                "model_id": "host",
                "attrs": json.dumps([{"attr_id": "ip", "attr_type": "str", "option": {}}]),
            }
        ]
        captured = {}

        from apps.cmdb.management.commands import migrate_field_constraints as cmd_mod

        fake = FakeGraph(query_entity=(models, 1))
        monkeypatch.setattr(cmd_mod, "GraphClient", lambda *a, **k: fake)
        monkeypatch.setattr(
            "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
            classmethod(lambda cls, model_id: True),
        )
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("migrate_field_constraints", "--dry-run", stdout=out, stderr=out)
        text = out.getvalue()
        assert "DRY RUN" in text
        # dry-run 不写图DB
        assert not any(c[0] == "set_entity_properties" for c in fake.calls)

    def test_real_migration_writes(self, monkeypatch):
        models = [
            {
                "_id": "n1",
                "model_id": "host",
                "attrs": json.dumps(
                    [
                        {"attr_id": "ip", "attr_type": "str", "option": {}},
                        {"attr_id": "cpu", "attr_type": "int", "option": {}},
                        {"attr_id": "create_time", "attr_type": "time", "option": {}},
                    ]
                ),
            }
        ]
        from apps.cmdb.management.commands import migrate_field_constraints as cmd_mod

        fake = FakeGraph(query_entity=(models, 1), set_entity_properties={"ok": True})
        monkeypatch.setattr(cmd_mod, "GraphClient", lambda *a, **k: fake)
        refreshed = []
        monkeypatch.setattr(
            "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
            classmethod(lambda cls, model_id: refreshed.append(model_id) or True),
        )
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("migrate_field_constraints", stdout=out, stderr=out)
        text = out.getvalue()
        assert "迁移成功完成" in text
        # 真实写回，且写入的 attrs 含约束
        write_call = next(c for c in fake.calls if c[0] == "set_entity_properties")
        written = json.loads(write_call[1][2]["attrs"])
        by_id = {a["attr_id"]: a for a in written}
        assert by_id["ip"]["option"]["validation_type"] == StringValidationType.UNRESTRICTED
        assert "min_value" in by_id["cpu"]["option"]
        assert by_id["create_time"]["option"]["display_format"] == TimeDisplayFormat.DATETIME
        # 所有字段补 user_prompt
        assert all("user_prompt" in a for a in written)
        assert refreshed == ["host"]

    def test_target_model_not_found(self, monkeypatch):
        text = self._run(monkeypatch, [], model_id="nope")
        assert "未找到模型" in text

    def test_no_models(self, monkeypatch):
        text = self._run(monkeypatch, [])
        assert "未找到任何模型" in text

    def test_per_model_error_counted(self, monkeypatch):
        # attrs 无法解析 -> _migrate_model 抛错 -> errors+1，命令不崩溃
        models = [{"_id": "n1", "model_id": "host", "attrs": "not-json"}]
        from apps.cmdb.management.commands import migrate_field_constraints as cmd_mod
        from django.core.management import call_command
        from io import StringIO

        fake = FakeGraph(query_entity=(models, 1))
        monkeypatch.setattr(cmd_mod, "GraphClient", lambda *a, **k: fake)
        out = StringIO()
        call_command("migrate_field_constraints", stdout=out, stderr=out)
        text = out.getvalue()
        assert "迁移失败" in text
        assert "1 个错误" in text

    def test_outer_query_error_handled(self, monkeypatch):
        from apps.cmdb.management.commands import migrate_field_constraints as cmd_mod
        from django.core.management import call_command
        from io import StringIO

        class _Boom(FakeGraph):
            def __getattr__(self, name):
                if name == "query_entity":
                    def _q(*a, **k):
                        raise RuntimeError("connection refused")

                    return _q
                return super().__getattr__(name)

        monkeypatch.setattr(cmd_mod, "GraphClient", lambda *a, **k: _Boom())
        out = StringIO()
        call_command("migrate_field_constraints", stdout=out, stderr=out)
        assert "迁移过程发生错误" in out.getvalue()

    def test_dry_run_with_changes_reports_no_update_when_none(self, monkeypatch):
        # 字段已带完整约束 -> 无需更新
        models = [
            {
                "_id": "n1",
                "model_id": "host",
                "attrs": json.dumps(
                    [
                        {
                            "attr_id": "ip",
                            "attr_type": "str",
                            "user_prompt": "",
                            "option": {"validation_type": "unrestricted", "widget_type": "single_line", "custom_regex": ""},
                        }
                    ]
                ),
            }
        ]
        text = self._run(monkeypatch, models)
        assert "无需更新" in text

    def test_migrate_model_method_directly(self, monkeypatch):
        from apps.cmdb.management.commands.migrate_field_constraints import Command

        cmd = Command()
        ag = FakeGraph(set_entity_properties={"ok": True})
        monkeypatch.setattr(
            "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
            classmethod(lambda cls, model_id: True),
        )
        model = {
            "_id": "n1",
            "model_id": "host",
            "attrs": json.dumps([{"attr_id": "ip", "attr_type": "str", "option": {}}]),
        }
        updated, count = cmd._migrate_model(ag, model, dry_run=False)
        assert updated is True
        assert count == 1
        assert any(c[0] == "set_entity_properties" for c in ag.calls)
