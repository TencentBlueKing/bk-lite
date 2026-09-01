import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from apps.system_mgmt.apps import HandleConfig
from apps.system_mgmt.providers import loader
from apps.system_mgmt.providers.registry import (
    capability_adapter_registry,
    provider_registry,
)
from apps.system_mgmt.providers.schemas import ProviderManifest


@pytest.fixture(autouse=True)
def clean_provider_state():
    loader.reset_builtin_providers()
    yield
    loader.reset_builtin_providers()


def test_system_mgmt_ready_does_not_load_providers(monkeypatch):
    def fail_if_loaded():
        raise AssertionError("SystemMgmtConfig.ready() 不应主动加载 provider")

    monkeypatch.setattr(loader, "load_builtin_providers", fail_if_loaded)

    HandleConfig("apps.system_mgmt", __import__("apps.system_mgmt")).ready()


def test_provider_registry_list_lazily_loads_builtin_providers():
    manifests = provider_registry.list()

    assert {manifest.key for manifest in manifests} == {"ad", "feishu", "wechat", "wecom"}


def test_adapter_registry_get_lazily_loads_builtin_providers():
    adapter_cls = capability_adapter_registry.get("feishu.login_auth")

    assert adapter_cls is not None
    assert adapter_cls.__name__ == "FeishuLoginAuthAdapter"


def test_builtin_provider_loading_is_thread_safe(monkeypatch):
    monkeypatch.setattr(loader, "discover_builtin_provider_packs", lambda: (("fake.provider", None),))

    import_count = 0
    import_count_lock = Lock()
    fake_module = SimpleNamespace(PROVIDER_MANIFEST={"key": "fake", "name": "Fake"})

    def slow_import_module(module_path):
        nonlocal import_count
        assert module_path == "fake.provider"
        with import_count_lock:
            import_count += 1
        time.sleep(0.05)
        return fake_module

    monkeypatch.setattr(loader, "import_module", slow_import_module)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: provider_registry.list(), range(2)))

    assert import_count == 1
    assert [[manifest.key for manifest in manifests] for manifests in results] == [["fake"], ["fake"]]


def test_provider_read_waits_for_force_reload(monkeypatch):
    provider_registry.list()

    clear_started = Event()
    release_reload = Event()
    original_clear = provider_registry.clear

    def blocking_clear():
        original_clear()
        clear_started.set()
        assert release_reload.wait(timeout=1)

    monkeypatch.setattr(provider_registry, "clear", blocking_clear)

    with ThreadPoolExecutor(max_workers=2) as executor:
        reload_future = executor.submit(loader.load_builtin_providers, force=True)
        assert clear_started.wait(timeout=1)

        read_future = executor.submit(provider_registry.list)
        try:
            time.sleep(0.05)
            assert not read_future.done()
        finally:
            release_reload.set()

        reload_future.result(timeout=1)
        manifests = read_future.result(timeout=1)

    assert {manifest.key for manifest in manifests} == {"ad", "feishu", "wechat", "wecom"}


def test_provider_loading_keeps_healthy_packs_when_one_pack_fails(monkeypatch):
    monkeypatch.setattr(
        loader,
        "discover_builtin_provider_packs",
        lambda: (("fake.good", None), ("fake.bad", None)),
    )

    fake_manifest = {
        "key": "fake",
        "name": "Fake",
        "capabilities": [
            {
                "key": "login_auth",
                "name": "登录认证",
                "adapter_key": "fake.login_auth",
                "adapter_path": "fake.Adapter",
            }
        ],
    }

    def import_module_with_failure(module_path):
        if module_path == "fake.good":
            return SimpleNamespace(PROVIDER_MANIFEST=fake_manifest)
        raise RuntimeError("provider import failed")

    monkeypatch.setattr(loader, "import_module", import_module_with_failure)
    monkeypatch.setattr(loader, "import_string", lambda _: object)

    loader.load_builtin_providers()

    assert loader._providers_loaded is True
    assert set(provider_registry._providers) == {"fake"}
    assert set(capability_adapter_registry._adapters) == {"fake.login_auth"}


def test_reset_builtin_providers_clears_loaded_state(monkeypatch):
    provider_registry.register(ProviderManifest.model_validate({"key": "fake", "name": "Fake"}))
    capability_adapter_registry.register("fake.login_auth", object)
    monkeypatch.setattr(loader, "_providers_loaded", True)

    reset_builtin_providers = getattr(loader, "reset_builtin_providers", None)
    assert callable(reset_builtin_providers)

    reset_builtin_providers()

    assert loader._providers_loaded is False
    assert provider_registry._providers == {}
    assert capability_adapter_registry._adapters == {}


def test_discover_builtin_provider_packs_scans_directories_not_a_fixed_name_list(tmp_path):
    pack = tmp_path / "custom_idp"
    pack.mkdir()
    (pack / "__init__.py").write_text("")
    (pack / "adapters").mkdir()
    (pack / "adapters" / "client.py").write_text("")
    (pack / "adapters" / "base_connection.py").write_text("")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "notes.txt").write_text("ignore")

    packs = loader.discover_builtin_provider_packs(tmp_path)

    assert packs == [("apps.system_mgmt.providers.builtin.custom_idp", pack)]


def test_validate_pack_layout_requires_adapters_client(tmp_path):
    pack = tmp_path / "custom_idp"
    pack.mkdir()
    (pack / "__init__.py").write_text("")
    (pack / "adapters").mkdir()
    (pack / "adapters" / "base_connection.py").write_text("")

    with pytest.raises(ValueError, match="adapters/client.py"):
        loader.validate_pack_layout(pack)


def test_validate_pack_layout_requires_base_connection(tmp_path):
    pack = tmp_path / "custom_idp"
    pack.mkdir()
    (pack / "__init__.py").write_text("")
    (pack / "adapters").mkdir()
    (pack / "adapters" / "client.py").write_text("")

    with pytest.raises(ValueError, match="adapters/base_connection.py"):
        loader.validate_pack_layout(pack)


def test_builtin_packs_all_have_required_adapter_modules():
    packs = loader.discover_builtin_provider_packs()

    assert {module_path.rsplit(".", 1)[-1] for module_path, _ in packs} == {
        "ad",
        "feishu",
        "wechat",
        "wecom",
    }
    for _, pack_dir in packs:
        assert (pack_dir / "adapters" / "client.py").is_file()
        assert (pack_dir / "adapters" / "base_connection.py").is_file()


def test_builtin_pack_code_logs_through_provider_sdk():
    banned = "from apps.core.logger import"
    offenders = []
    scan_roots = [
        loader.BUILTIN_PROVIDER_ROOT,
        loader.BUILTIN_PROVIDER_ROOT.parent / "base.py",
    ]
    for root in scan_roots:
        paths = [root] if root.is_file() else root.rglob("*.py")
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            if banned in path.read_text(encoding="utf-8"):
                offenders.append(str(path))
    assert offenders == []


def test_missing_language_file_skips_that_pack_only(monkeypatch, tmp_path):
    pack = tmp_path / "feishu"
    pack.mkdir()
    (pack / "__init__.py").write_text("")
    (pack / "adapters").mkdir()
    (pack / "adapters" / "client.py").write_text("")
    (pack / "adapters" / "base_connection.py").write_text("")

    monkeypatch.setattr(
        loader,
        "discover_builtin_provider_packs",
        lambda: (("apps.system_mgmt.providers.builtin.feishu", pack),),
    )

    loader.load_builtin_providers()

    assert loader._providers_loaded is True
    assert provider_registry._providers == {}
    assert capability_adapter_registry._adapters == {}


def test_load_builtin_providers_only_scans_builtin_root(monkeypatch):
    scanned_roots = []
    original = loader.discover_provider_packs

    def tracking_discover(root, import_prefix, *, required=True):
        scanned_roots.append(root)
        return original(root, import_prefix, required=required)

    monkeypatch.setattr(loader, "discover_provider_packs", tracking_discover)

    loader.load_builtin_providers()

    assert scanned_roots == [loader.BUILTIN_PROVIDER_ROOT]
    assert not hasattr(loader, "discover_custom_provider_packs")
    assert not hasattr(loader, "CUSTOM_PROVIDER_ROOT")


def test_pack_directory_resolves_relative_adapter_paths(monkeypatch, tmp_path):
    pack = tmp_path / "acme"
    pack.mkdir()
    (pack / "__init__.py").write_text("")
    (pack / "adapters").mkdir()
    (pack / "adapters" / "client.py").write_text("")
    (pack / "adapters" / "base_connection.py").write_text("")

    imported_paths = []

    monkeypatch.setattr(loader, "discover_builtin_provider_packs", lambda: (("pack.acme", pack),))
    monkeypatch.setattr(
        loader,
        "import_module",
        lambda _: SimpleNamespace(
            PROVIDER_MANIFEST={
                "key": "acme",
                "name": "Acme",
                "base_connection_adapter_key": "acme.base_connection",
                "base_connection_adapter_path": "adapters.base_connection.AcmeBaseConnectionAdapter",
                "capabilities": [
                    {
                        "key": "login_auth",
                        "name": "登录认证",
                        "adapter_key": "acme.login_auth",
                        "adapter_path": "adapters.login_auth.AcmeLoginAuthAdapter",
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(loader, "load_language_catalog", lambda _: {"en": {"description": "Acme"}})

    def capture_import_string(dotted_path):
        imported_paths.append(dotted_path)
        return type(dotted_path.rsplit(".", 1)[-1], (), {})

    monkeypatch.setattr(loader, "import_string", capture_import_string)

    loader.load_builtin_providers()

    manifest = provider_registry.get("acme")
    assert manifest.capabilities[0].adapter_path == "adapters.login_auth.AcmeLoginAuthAdapter"
    assert manifest.base_connection_adapter_path == "adapters.base_connection.AcmeBaseConnectionAdapter"
    assert imported_paths == [
        "pack.acme.adapters.login_auth.AcmeLoginAuthAdapter",
        "pack.acme.adapters.base_connection.AcmeBaseConnectionAdapter",
    ]


def test_pack_directory_rejects_absolute_adapter_path_and_keeps_other_packs(monkeypatch, tmp_path):
    good_pack = tmp_path / "good"
    bad_pack = tmp_path / "bad"
    for pack in (good_pack, bad_pack):
        pack.mkdir()
        (pack / "__init__.py").write_text("")
        (pack / "adapters").mkdir()
        (pack / "adapters" / "client.py").write_text("")
        (pack / "adapters" / "base_connection.py").write_text("")

    monkeypatch.setattr(
        loader,
        "discover_builtin_provider_packs",
        lambda: (("pack.good", good_pack), ("pack.bad", bad_pack)),
    )

    def import_module_by_path(module_path):
        if module_path == "pack.good":
            return SimpleNamespace(
                PROVIDER_MANIFEST={
                    "key": "good",
                    "name": "Good",
                    "capabilities": [
                        {
                            "key": "login_auth",
                            "name": "登录认证",
                            "adapter_key": "good.login_auth",
                            "adapter_path": "adapters.login_auth.GoodAdapter",
                        }
                    ],
                }
            )
        return SimpleNamespace(
            PROVIDER_MANIFEST={
                "key": "bad",
                "name": "Bad",
                "capabilities": [
                    {
                        "key": "login_auth",
                        "name": "登录认证",
                        "adapter_key": "bad.login_auth",
                        "adapter_path": "pack.bad.adapters.login_auth.BadAdapter",
                    }
                ],
            }
        )

    monkeypatch.setattr(loader, "import_module", import_module_by_path)
    monkeypatch.setattr(loader, "load_language_catalog", lambda _: {"en": {"description": "ok"}})
    monkeypatch.setattr(loader, "import_string", lambda _: object)

    loader.load_builtin_providers()

    assert set(provider_registry._providers) == {"good"}
    assert set(capability_adapter_registry._adapters) == {"good.login_auth"}


def test_adapter_key_must_use_manifest_key_prefix(monkeypatch):
    monkeypatch.setattr(
        loader,
        "discover_builtin_provider_packs",
        lambda: (("fake.good", None), ("fake.bad", None)),
    )

    def import_module_by_path(module_path):
        if module_path == "fake.good":
            return SimpleNamespace(
                PROVIDER_MANIFEST={
                    "key": "good",
                    "name": "Good",
                    "capabilities": [
                        {
                            "key": "login_auth",
                            "name": "登录认证",
                            "adapter_key": "good.login_auth",
                            "adapter_path": "good.Adapter",
                        }
                    ],
                }
            )
        return SimpleNamespace(
            PROVIDER_MANIFEST={
                "key": "bad",
                "name": "Bad",
                "capabilities": [
                    {
                        "key": "login_auth",
                        "name": "登录认证",
                        "adapter_key": "other.login_auth",
                        "adapter_path": "other.Adapter",
                    }
                ],
            }
        )

    monkeypatch.setattr(loader, "import_module", import_module_by_path)
    monkeypatch.setattr(loader, "import_string", lambda _: object)

    loader.load_builtin_providers()

    assert set(provider_registry._providers) == {"good"}
    assert set(capability_adapter_registry._adapters) == {"good.login_auth"}


def test_manifest_without_pack_directory_keeps_absolute_import_path(monkeypatch):
    monkeypatch.setattr(loader, "discover_builtin_provider_packs", lambda: (("fake.provider", None),))
    imported_paths = []
    monkeypatch.setattr(
        loader,
        "import_module",
        lambda _: SimpleNamespace(
            PROVIDER_MANIFEST={
                "key": "fake",
                "name": "Fake",
                "capabilities": [
                    {
                        "key": "login_auth",
                        "name": "登录认证",
                        "adapter_key": "fake.login_auth",
                        "adapter_path": "apps.elsewhere.FakeAdapter",
                    }
                ],
            }
        ),
    )

    def capture_import_string(dotted_path):
        imported_paths.append(dotted_path)
        return object

    monkeypatch.setattr(loader, "import_string", capture_import_string)

    loader.load_builtin_providers()

    assert imported_paths == ["apps.elsewhere.FakeAdapter"]
    assert provider_registry.get("fake").capabilities[0].adapter_path == "apps.elsewhere.FakeAdapter"


def test_builtin_manifests_keep_pack_relative_adapter_paths():
    loader.load_builtin_providers()

    for key in ("ad", "feishu", "wechat", "wecom"):
        manifest = provider_registry.get(key)
        assert manifest.base_connection_adapter_path.startswith("adapters.")
        assert not manifest.base_connection_adapter_path.startswith("apps.")
        for capability in manifest.capabilities:
            assert capability.adapter_path.startswith("adapters.")
            assert not capability.adapter_path.startswith("apps.")
            assert capability.adapter_key.startswith(f"{key}.")
        assert capability_adapter_registry.get(f"{key}.base_connection") is not None


def test_builtin_language_catalog_is_required_for_successful_load():
    loader.load_builtin_providers()

    feishu = provider_registry.get("feishu")
    assert feishu.pack_i18n["zh-Hans"]["name"] == "飞书"
    assert "登录认证" in feishu.pack_i18n["zh-Hans"]["description"]
    assert feishu.pack_i18n["en"]["name"] == "Feishu"
