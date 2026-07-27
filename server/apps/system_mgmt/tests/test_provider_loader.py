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

    assert {manifest.key for manifest in manifests} == {"ad", "feishu", "wechat"}


def test_adapter_registry_get_lazily_loads_builtin_providers():
    adapter_cls = capability_adapter_registry.get("feishu.login_auth")

    assert adapter_cls is not None
    assert adapter_cls.__name__ == "FeishuLoginAuthAdapter"


def test_builtin_provider_loading_is_thread_safe(monkeypatch):
    monkeypatch.setattr(loader, "BUILTIN_PROVIDER_MODULES", ("fake.provider",))

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

    assert {manifest.key for manifest in manifests} == {"ad", "feishu", "wechat"}


def test_builtin_provider_loading_rolls_back_all_registries_on_failure(monkeypatch):
    monkeypatch.setattr(loader, "BUILTIN_PROVIDER_MODULES", ("fake.good", "fake.bad"))

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

    with pytest.raises(RuntimeError, match="provider import failed"):
        loader.load_builtin_providers()

    assert loader._providers_loaded is False
    assert provider_registry._providers == {}
    assert capability_adapter_registry._adapters == {}


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
