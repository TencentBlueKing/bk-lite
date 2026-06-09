"""CMDB 企业版 facade 契约与共享 loader 的纯单测（无 DB、无图库）。

覆盖：
- load_provider 的回退 / 成功 / 契约缺失三态
- model_ops / instance_ops 社区默认契约的空行为（add-only：缺 provider 即退社区版）
"""

import importlib.util
import sys
import types

import pytest

from apps.cmdb.extensions.loader import load_provider

# 部分测试断言企业 provider 已激活；缺 overlay 时单独跳过这些（其余社区契约测试照常）
_HAS_ENTERPRISE = importlib.util.find_spec("apps.cmdb.enterprise.model_ops.provider") is not None
_requires_enterprise = pytest.mark.skipif(not _HAS_ENTERPRISE, reason="enterprise overlay absent")


def test_load_provider_returns_default_when_module_missing():
    # 指向一个确实不存在的能力域 provider，验证回退到 default
    factory = load_provider(
        "apps.cmdb.enterprise.nonexistent_capability.provider",
        "get_whatever_extension",
        default=lambda: "fallback",
    )
    assert factory() == "fallback"


def test_load_provider_returns_provider_when_present(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.model_ops.provider")
    fake.get_model_enterprise_extension = lambda: "enterprise"
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.model_ops.provider", fake)
    factory = load_provider(
        "apps.cmdb.enterprise.model_ops.provider",
        "get_model_enterprise_extension",
        default=lambda: "fallback",
    )
    assert factory() == "enterprise"


def test_load_provider_raises_when_contract_attr_missing(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.instance_ops.provider")
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.instance_ops.provider", fake)
    with pytest.raises(AttributeError, match="get_instance_enterprise_extension"):
        load_provider(
            "apps.cmdb.enterprise.instance_ops.provider",
            "get_instance_enterprise_extension",
            default=lambda: "fallback",
        )


# ---- model_ops 社区默认契约 ----


def test_model_extension_default_has_no_file_attr_types():
    from apps.cmdb.model_ops.extensions import ModelEnterpriseExtension

    ext = ModelEnterpriseExtension()
    assert ext.file_attr_types() == set()
    # 默认 validate_attr 不抛、不改
    attr = {"attr_id": "a", "attr_type": "str"}
    assert ext.validate_attr(attr) == attr


def test_file_attr_types_empty_when_provider_absent(monkeypatch):
    # add-only：模拟企业 provider 缺失 → 社区识别不出任何文件字段
    import apps.cmdb.model_ops.extensions as ext_mod

    monkeypatch.setattr(ext_mod, "get_model_enterprise_extension", lambda: ext_mod.ModelEnterpriseExtension())
    assert ext_mod.file_attr_types() == set()
    assert ext_mod.is_file_attr_type("attachment") is False
    assert ext_mod.is_file_attr_type("image") is False


# ---- instance_ops 社区默认契约 ----


def test_model_extension_default_unsupported_sets_empty():
    from apps.cmdb.model_ops.extensions import ModelEnterpriseExtension

    ext = ModelEnterpriseExtension()
    assert ext.unsupported_unique_attr_types() == set()
    assert ext.unsupported_auto_relation_attr_types() == set()


@_requires_enterprise
def test_enterprise_model_provider_declares_file_types():
    # 本仓库企业 provider 存在 → 声明附件/图片为文件类型且不支持唯一/自动关联
    from apps.cmdb.model_ops.extensions import get_model_enterprise_extension

    ext = get_model_enterprise_extension()
    assert {"attachment", "image"} <= ext.file_attr_types()
    assert {"attachment", "image"} <= ext.unsupported_unique_attr_types()
    assert {"attachment", "image"} <= ext.unsupported_auto_relation_attr_types()


# ---- collect 域门面 ----


def test_collect_extension_default_empty_when_provider_absent(monkeypatch):
    import apps.cmdb.collect.extensions as cext

    monkeypatch.setattr(
        cext, "load_provider", lambda *a, **k: lambda: cext._EMPTY_COLLECT_EXTENSION
    )
    ext = cext.get_collect_enterprise_extension()
    assert ext.collect_tree == []
    assert ext.plugin_packages == ()
    assert ext.node_param_packages == ()


@_requires_enterprise
def test_collect_extension_present_exposes_scoped_packages():
    # 企业 collect provider 存在 → 仅扫描 enterprise.collect 包（不扫整个 enterprise）
    from apps.cmdb.collect.extensions import get_collect_enterprise_extension

    ext = get_collect_enterprise_extension()
    assert ext.plugin_packages == ("apps.cmdb.enterprise.collect",)
    assert ext.node_param_packages == ("apps.cmdb.enterprise.collect",)
    assert ext.collect_tree  # 达梦树非空


def test_instance_extension_default_is_noop():
    from apps.cmdb.instance_ops.extensions import InstanceEnterpriseExtension

    ext = InstanceEnterpriseExtension()
    data = {"inst_name": "h"}
    attrs = [{"attr_id": "f", "attr_type": "str"}]
    # 默认 normalize_file_fields 原样返回
    assert ext.normalize_file_fields("host", data, attrs, operator="admin") == data
    # 默认上传/下载/临时删除均报「未启用」
    with pytest.raises(Exception):
        ext.handle_upload(request=None, model_id="host", attr_id="f", uploaded_file=None)
    with pytest.raises(Exception):
        ext.handle_download(request=None, file_id="x")
    with pytest.raises(Exception):
        ext.handle_delete_temp(request=None, file_id="x")
