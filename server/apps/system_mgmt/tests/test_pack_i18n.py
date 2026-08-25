from types import SimpleNamespace

import pytest

from apps.system_mgmt.providers.pack_i18n import (
    localize_public_manifest,
    normalize_locale,
    request_locale,
    resolve_bound_instance_provider_name,
    resolve_provider_copy,
)
from apps.system_mgmt.providers.schemas import ProviderManifest


def test_normalize_locale_maps_zh_aliases_to_zh_hans():
    assert normalize_locale("zh") == "zh-Hans"
    assert normalize_locale("zh-CN") == "zh-Hans"
    assert normalize_locale("zh-Hans") == "zh-Hans"
    assert normalize_locale("en") == "en"
    assert normalize_locale("ja") == "en"
    assert normalize_locale(None) == "en"


@pytest.mark.django_db
def test_request_locale_prefers_account_user_over_request_user():
    from apps.system_mgmt.models import User as AccountUser

    AccountUser.objects.create(username="alice", domain="domain.com", locale="en", email="a@b.com", display_name="alice", password="x")
    request = SimpleNamespace(
        user=SimpleNamespace(username="alice", domain="domain.com", locale="zh-Hans")
    )
    assert request_locale(request) == "en"


@pytest.mark.django_db
def test_request_locale_queries_account_user_once_per_request(django_assert_num_queries):
    from apps.system_mgmt.models import User as AccountUser

    AccountUser.objects.create(
        username="alice",
        domain="domain.com",
        locale="en",
        email="a@b.com",
        display_name="alice",
        password="x",
    )
    request = SimpleNamespace(user=SimpleNamespace(username="alice", domain="domain.com", locale="zh-Hans"))
    with django_assert_num_queries(1):
        assert request_locale(request) == "en"
        assert request_locale(request) == "en"


@pytest.mark.django_db
def test_request_locale_falls_back_to_request_user_without_account():
    request = SimpleNamespace(
        user=SimpleNamespace(username="nobody", domain="domain.com", locale="zh-Hans")
    )
    assert request_locale(request) == "zh-Hans"


def test_resolve_bound_instance_provider_name_returns_empty_without_instance():
    assert resolve_bound_instance_provider_name(SimpleNamespace(integration_instance_id=None), None) == ""
    assert resolve_bound_instance_provider_name(SimpleNamespace(integration_instance_id=1, integration_instance=None), None) == ""


def test_resolve_provider_copy_falls_back_to_manifest_then_key():
    manifest = ProviderManifest.model_validate({"key": "custom", "name": "Custom IDP", "description": "English fallback"})
    name, description = resolve_provider_copy(manifest, "zh-Hans")
    assert name == "Custom IDP"
    assert description == "English fallback"


def _form_i18n_manifest() -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "key": "ad",
            "name": "Active Directory",
            "description": "Manifest fallback description",
            "instance_templates": {
                "base_connection": {
                    "title": "Base Connection",
                    "groups": [
                        {
                            "key": "connection",
                            "title": "Connection",
                            "fields": [
                                {
                                    "key": "connection_url",
                                    "label": "Server IP",
                                    "placeholder": "127.0.0.1",
                                    "help_text": "Manifest help",
                                }
                            ],
                        }
                    ],
                }
            },
            "business_templates": {
                "login_auth_form": {
                    "title": "Login authentication",
                    "groups": [
                        {
                            "key": "mapping",
                            "title": "Field mapping",
                            "fields": [{"key": "display_name", "label": "Display name"}],
                        }
                    ],
                }
            },
            "capabilities": [
                {
                    "key": "login_auth",
                    "name": "Login Auth",
                    "description": "Login",
                    "adapter_key": "ad.login_auth",
                    "adapter_path": "apps.system_mgmt.providers.builtin.ad.adapters.login_auth.ADLoginAuthAdapter",
                    "connection_template": [
                        {
                            "key": "login_auth_identity_field",
                            "label": "Login account type",
                            "field_type": "select",
                            "options": [
                                {"value": "sAMAccountName", "label": "Username (sAMAccountName)"},
                                {"value": "none", "label": "None"},
                            ],
                        }
                    ],
                    "business_template": "login_auth_form",
                }
            ],
            "pack_i18n": {
                "en": {
                    "name": "Active Directory",
                    "description": "EN description",
                    "templates": {
                        "base_connection": {
                            "title": "Base Connection",
                            "groups": {
                                "connection": {
                                    "title": "Connection",
                                    "fields": {
                                        "connection_url": {
                                            "label": "Server IP",
                                            "help_text": "EN help",
                                        }
                                    },
                                }
                            },
                        },
                        "login_auth_form": {
                            "title": "Login authentication",
                            "groups": {
                                "mapping": {
                                    "title": "Field mapping",
                                    "fields": {"display_name": {"label": "Display name"}},
                                }
                            },
                        },
                    },
                    "capabilities": {
                        "login_auth": {
                            "fields": {
                                "login_auth_identity_field": {
                                    "label": "Login account type",
                                    "options": {
                                        "sAMAccountName": "Username (sAMAccountName)",
                                        "none": "None",
                                    },
                                }
                            }
                        }
                    },
                },
                "zh-Hans": {
                    "name": "Active Directory",
                    "description": "中文简介",
                    "templates": {
                        "base_connection": {
                            "title": "基础连接",
                            "groups": {
                                "connection": {
                                    "title": "连接配置",
                                    "fields": {
                                        "connection_url": {
                                            "label": "服务器 IP",
                                            "help_text": "中文帮助",
                                        }
                                    },
                                }
                            },
                        },
                        "login_auth_form": {
                            "title": "登录认证配置",
                            "groups": {
                                "mapping": {
                                    "title": "字段映射",
                                    "fields": {"display_name": {"label": "显示名称"}},
                                }
                            },
                        },
                    },
                    "capabilities": {
                        "login_auth": {
                            "fields": {
                                "login_auth_identity_field": {
                                    "label": "登录账号类型",
                                    "options": {
                                        "sAMAccountName": "用户名（sAMAccountName）",
                                        "none": "无",
                                    },
                                }
                            }
                        }
                    },
                },
            },
        }
    )


def test_localize_public_manifest_overlays_form_copy_for_zh_hans():
    payload = localize_public_manifest(_form_i18n_manifest(), "zh-Hans")
    template = payload["instance_templates"]["base_connection"]
    field = template["groups"][0]["fields"][0]

    assert payload["description"] == "中文简介"
    assert template["title"] == "基础连接"
    assert template["groups"][0]["title"] == "连接配置"
    assert field["label"] == "服务器 IP"
    assert field["help_text"] == "中文帮助"
    assert field["placeholder"] == "127.0.0.1"
    assert payload["instance_template"][0]["label"] == "服务器 IP"
    assert payload["business_templates"]["login_auth_form"]["title"] == "登录认证配置"
    assert payload["business_templates"]["login_auth_form"]["groups"][0]["fields"][0]["label"] == "显示名称"

    identity = payload["capabilities"][0]["connection_template"][0]
    assert identity["label"] == "登录账号类型"
    options = {item["value"]: item["label"] for item in identity["options"]}
    assert options["sAMAccountName"] == "用户名（sAMAccountName）"
    assert options["none"] == "无"


def test_localize_public_manifest_falls_back_to_en_then_manifest():
    manifest = _form_i18n_manifest()
    manifest.pack_i18n["zh-Hans"]["templates"]["base_connection"]["groups"]["connection"]["fields"].pop(
        "connection_url"
    )
    payload = localize_public_manifest(manifest, "zh-Hans")
    field = payload["instance_templates"]["base_connection"]["groups"][0]["fields"][0]
    assert field["label"] == "Server IP"
    assert field["help_text"] == "EN help"
    assert field["placeholder"] == "127.0.0.1"

    del manifest.pack_i18n["en"]["templates"]["base_connection"]["groups"]["connection"]["fields"]["connection_url"]
    payload = localize_public_manifest(manifest, "zh-Hans")
    field = payload["instance_templates"]["base_connection"]["groups"][0]["fields"][0]
    assert field["label"] == "Server IP"
    assert field["help_text"] == "Manifest help"
    assert field["placeholder"] == "127.0.0.1"
