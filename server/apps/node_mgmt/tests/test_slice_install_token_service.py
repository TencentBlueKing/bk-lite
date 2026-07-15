from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pydantic.root_model  # noqa
import pytest

from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.services.install_token import InstallTokenService

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    # 全局 conftest 强制 DummyCache，本切片需要真实读写语义，改用 locmem
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "node-mgmt-install-token-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


class TestGenerateInstallToken:
    def test_token_is_uuid_and_cache_payload_complete(self):
        token = InstallTokenService.generate_install_token(
            node_id="node-1",
            ip="10.0.0.5",
            user="alice",
            os="linux",
            package_id="pkg-7",
            cloud_region_id="3",
            organizations=[1, 2],
            node_name="web-01",
            cpu_architecture="amd64",
        )
        # uuid4 形态
        assert len(token) == 36 and token.count("-") == 4

        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        payload = cache.get(cache_key)
        assert payload["node_id"] == "node-1"
        assert payload["ip"] == "10.0.0.5"
        assert payload["user"] == "alice"
        assert payload["os"] == "linux"
        assert payload["package_id"] == "pkg-7"
        assert payload["cloud_region_id"] == "3"
        assert payload["organizations"] == [1, 2]
        assert payload["node_name"] == "web-01"
        assert payload["cpu_architecture"] == "amd64"
        assert payload["usage_count"] == 0
        assert payload["max_usage"] == InstallerConstants.INSTALL_TOKEN_MAX_USAGE


class TestValidateInstallToken:
    def _gen(self, **kw):
        params = dict(
            node_id="n1",
            ip="1.1.1.1",
            user="bob",
            os="linux",
            package_id="p1",
            cloud_region_id="1",
            organizations=[9],
            node_name="host",
            cpu_architecture="",
        )
        params.update(kw)
        return InstallTokenService.generate_install_token(**params)

    def test_first_validation_returns_data_and_increments_usage(self):
        token = self._gen()
        result = InstallTokenService.validate_and_get_token_data(token)

        assert result["node_id"] == "n1"
        assert result["organizations"] == [9]
        # 第一次使用后剩余 = max - 1
        assert result["remaining_usage"] == InstallerConstants.INSTALL_TOKEN_MAX_USAGE - 1

        # payload 不再改写，独立计数键原子递增
        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        usage_cache_key = f"{cache_key}:{InstallTokenService.USAGE_COUNT_CACHE_SUFFIX}"
        assert cache.get(cache_key)["usage_count"] == 0
        assert cache.get(usage_cache_key) == 1

    def test_validation_does_not_extend_token_ttl(self):
        token = self._gen()

        with patch.object(cache, "set", wraps=cache.set) as cache_set:
            InstallTokenService.validate_and_get_token_data(token)

        cache_set.assert_not_called()

    def test_concurrent_validation_never_exceeds_max_usage(self):
        token = self._gen()

        def consume():
            try:
                InstallTokenService.validate_and_get_token_data(token)
                return True
            except BaseAppException:
                return False

        attempts = InstallerConstants.INSTALL_TOKEN_MAX_USAGE * 2
        with ThreadPoolExecutor(max_workers=attempts) as executor:
            results = list(executor.map(lambda _: consume(), range(attempts)))

        assert sum(results) == InstallerConstants.INSTALL_TOKEN_MAX_USAGE

    def test_legacy_payload_usage_count_seeds_atomic_counter(self):
        token = self._gen()
        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        payload = cache.get(cache_key)
        payload["usage_count"] = 2
        cache.set(cache_key, payload, timeout=InstallerConstants.INSTALL_TOKEN_EXPIRE_TIME)

        result = InstallTokenService.validate_and_get_token_data(token)

        usage_cache_key = f"{cache_key}:{InstallTokenService.USAGE_COUNT_CACHE_SUFFIX}"
        assert cache.get(usage_cache_key) == 3
        assert result["remaining_usage"] == InstallerConstants.INSTALL_TOKEN_MAX_USAGE - 3

    def test_stale_inflight_payload_cannot_recreate_exhausted_counter(self):
        token = self._gen()
        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        stale_payload = cache.get(cache_key)

        for _ in range(InstallerConstants.INSTALL_TOKEN_MAX_USAGE):
            InstallTokenService.validate_and_get_token_data(token)
        with pytest.raises(BaseAppException):
            InstallTokenService.validate_and_get_token_data(token)

        usage_cache_key = f"{cache_key}:{InstallTokenService.USAGE_COUNT_CACHE_SUFFIX}"
        assert cache.get(cache_key) is None
        assert cache.get(usage_cache_key) == InstallerConstants.INSTALL_TOKEN_MAX_USAGE + 1

        with pytest.raises(BaseAppException) as exc:
            InstallTokenService._consume_token_usage(
                cache_key=cache_key,
                data=stale_payload,
                max_usage=InstallerConstants.INSTALL_TOKEN_MAX_USAGE,
                timeout=InstallerConstants.INSTALL_TOKEN_EXPIRE_TIME,
                invalid_message="Invalid or expired token",
                exceeded_message="Token has exceeded maximum usage limit",
            )

        assert "exceeded maximum usage" in str(exc.value)
        assert cache.get(usage_cache_key) == InstallerConstants.INSTALL_TOKEN_MAX_USAGE + 2

    def test_invalid_token_raises(self):
        with pytest.raises(BaseAppException) as exc:
            InstallTokenService.validate_and_get_token_data("does-not-exist")
        assert "Invalid or expired token" in str(exc.value)

    def test_exceeding_max_usage_deletes_and_raises(self):
        token = self._gen()
        # 用满 max_usage 次
        for _ in range(InstallerConstants.INSTALL_TOKEN_MAX_USAGE):
            InstallTokenService.validate_and_get_token_data(token)

        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        # 此时 usage_count == max_usage，下一次应抛错并删 key
        with pytest.raises(BaseAppException) as exc:
            InstallTokenService.validate_and_get_token_data(token)
        assert "exceeded maximum usage" in str(exc.value)
        assert cache.get(cache_key) is None

    def test_remaining_usage_decrements_each_call(self):
        token = self._gen()
        first = InstallTokenService.validate_and_get_token_data(token)
        second = InstallTokenService.validate_and_get_token_data(token)
        assert second["remaining_usage"] == first["remaining_usage"] - 1


class TestDownloadToken:
    def test_generate_and_validate_download_token(self):
        token = InstallTokenService.generate_download_token(package_id="pkg-99", node_id="node-x")
        cache_key = f"{InstallerConstants.DOWNLOAD_TOKEN_CACHE_PREFIX}:{token}"
        payload = cache.get(cache_key)
        assert payload["package_id"] == "pkg-99"
        assert payload["node_id"] == "node-x"
        assert payload["usage_count"] == 0

        result = InstallTokenService.validate_and_get_download_token_data(token)
        assert result["package_id"] == "pkg-99"
        assert result["node_id"] == "node-x"
        assert result["remaining_usage"] == InstallerConstants.DOWNLOAD_TOKEN_MAX_USAGE - 1

    def test_invalid_download_token_raises(self):
        with pytest.raises(BaseAppException) as exc:
            InstallTokenService.validate_and_get_download_token_data("nope")
        assert "Invalid or expired download token" in str(exc.value)

    def test_download_validation_does_not_extend_token_ttl(self):
        token = InstallTokenService.generate_download_token(package_id="p", node_id="n")

        with patch.object(cache, "set", wraps=cache.set) as cache_set:
            InstallTokenService.validate_and_get_download_token_data(token)

        cache_set.assert_not_called()

    def test_download_token_exhaustion_deletes_and_raises(self):
        token = InstallTokenService.generate_download_token(package_id="p", node_id="n")
        for _ in range(InstallerConstants.DOWNLOAD_TOKEN_MAX_USAGE):
            InstallTokenService.validate_and_get_download_token_data(token)

        cache_key = f"{InstallerConstants.DOWNLOAD_TOKEN_CACHE_PREFIX}:{token}"
        with pytest.raises(BaseAppException) as exc:
            InstallTokenService.validate_and_get_download_token_data(token)
        assert "exceeded maximum usage" in str(exc.value)
        assert cache.get(cache_key) is None
