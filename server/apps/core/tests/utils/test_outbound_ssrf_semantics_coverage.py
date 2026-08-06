"""出站 SSRF 语义 — 行为覆盖（公开 seam）。

Seams（与 specs/changes/outbound-ssrf-whitelist-semantics 一致）:
- SSRFValidator.validate / validate_llm_endpoint / validate_callback
- is_valid_webhook_url
- network_whitelist_cache 读写与失效
- 0044 迁移 remove / restore
"""

from __future__ import annotations

import ipaddress
import socket
from importlib import import_module
from unittest import mock

import pytest

from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.system_mgmt.utils.channel_utils import is_valid_webhook_url

PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE = [(2, 1, 6, "", ("10.1.2.3", 443))]
EMPTY_ADDR = []
BAD_THEN_GOOD = [
    (2, 1, 6, "", ("not-an-ip", 80)),
    (2, 1, 6, "", ("93.184.216.34", 80)),
]
ONLY_BAD = [(2, 1, 6, "", ("not-an-ip", 80))]


class TestValidateCoverageGaps:
    def test_rejects_percent_encoded_hostname(self):
        with pytest.raises(SSRFError, match="非法编码"):
            SSRFValidator.validate("https://qyapi%2eweixin.qq.com/hook")

    def test_optional_allowlist_rejects_other_hosts(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLIC):
            with pytest.raises(SSRFError, match="不在允许列表"):
                SSRFValidator.validate("https://example.com/", allowlist={"other.com"})

    def test_optional_allowlist_accepts_listed_host(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLIC):
            assert SSRFValidator.validate("https://example.com/", allowlist={"EXAMPLE.com"}) == "https://example.com/"

    def test_dns_failure_raises(self):
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror("nxdomain")):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate("https://missing.example/")

    def test_empty_addrinfo_raises(self):
        with mock.patch("socket.getaddrinfo", return_value=EMPTY_ADDR):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate("https://empty.example/")

    def test_skips_unparseable_addr_then_accepts_public(self):
        with mock.patch("socket.getaddrinfo", return_value=BAD_THEN_GOOD):
            assert SSRFValidator.validate("https://mixed.example/") == "https://mixed.example/"

    def test_all_unparseable_addrs_rejected(self):
        with mock.patch("socket.getaddrinfo", return_value=ONLY_BAD):
            with pytest.raises(SSRFError, match="未返回可解析 IP"):
                SSRFValidator.validate("https://bad.example/")

    def test_ipv6_literal_requires_whitelist(self):
        with mock.patch.object(SSRFValidator, "_get_allowed_networks", return_value=[]):
            with pytest.raises(SSRFError) as exc:
                SSRFValidator.validate("http://[2001:db8::1]/")
            assert exc.value.code == "NETWORK_WHITELIST_REQUIRED"

    def test_ipv6_literal_allowed_when_whitelisted(self):
        nets = [ipaddress.ip_network("2001:db8::1/128")]
        with mock.patch.object(SSRFValidator, "_get_allowed_networks", return_value=nets):
            assert SSRFValidator.validate("http://[2001:db8::1]/") == "http://[2001:db8::1]/"

    def test_overflow_decimal_host_treated_as_domain(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLIC):
            assert SSRFValidator.validate("http://999999999999999999999/") == "http://999999999999999999999/"

    def test_invalid_cidr_in_whitelist_skipped_still_blocks_private(self):
        with (
            mock.patch(
                "apps.system_mgmt.utils.network_whitelist_cache.get_network_whitelist_cidrs",
                return_value=["not-a-cidr", "10.1.2.0/24"],
            ),
            mock.patch(
                "apps.system_mgmt.utils.network_whitelist_cache.get_network_whitelist_domains",
                return_value=[],
            ),
            mock.patch("socket.getaddrinfo", return_value=PRIVATE),
        ):
            assert SSRFValidator.validate("https://corp.example/hook") == "https://corp.example/hook"

    def test_whitelist_loader_exception_fail_closed(self):
        with (
            mock.patch(
                "apps.system_mgmt.utils.network_whitelist_cache.get_network_whitelist_cidrs",
                side_effect=RuntimeError("db down"),
            ),
            mock.patch(
                "apps.system_mgmt.utils.network_whitelist_cache.get_network_whitelist_domains",
                side_effect=RuntimeError("db down"),
            ),
        ):
            with pytest.raises(SSRFError) as exc:
                SSRFValidator.validate("http://10.0.0.1/")
            assert exc.value.code == "NETWORK_WHITELIST_REQUIRED"

    def test_domain_whitelist_loader_exception_still_blocks_private(self):
        with (
            mock.patch.object(SSRFValidator, "_get_allowed_networks", return_value=[]),
            mock.patch(
                "apps.system_mgmt.utils.network_whitelist_cache.get_network_whitelist_domains",
                side_effect=RuntimeError("db down"),
            ),
            mock.patch("socket.getaddrinfo", return_value=PRIVATE),
        ):
            with pytest.raises(SSRFError, match="禁止的网段"):
                SSRFValidator.validate("https://corp.example/hook")

    def test_private_allowed_via_cidr_on_resolved_domain(self):
        with (
            mock.patch.object(
                SSRFValidator,
                "_get_allowed_networks",
                return_value=[ipaddress.ip_network("10.1.2.0/24")],
            ),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value=set()),
            mock.patch("socket.getaddrinfo", return_value=PRIVATE),
        ):
            assert SSRFValidator.validate("https://corp.example/hook") == "https://corp.example/hook"


class TestLlmAndCallbackCoverageGaps:
    def test_llm_rejects_empty(self):
        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate_llm_endpoint("")

    def test_llm_rejects_bad_scheme(self):
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_llm_endpoint("ftp://vllm.local/v1")

    def test_llm_rejects_missing_host(self):
        with pytest.raises(SSRFError, match="有效主机名"):
            SSRFValidator.validate_llm_endpoint("http:///v1")

    def test_llm_dns_failure(self):
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror("x")):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate_llm_endpoint("http://vllm.local/v1")

    def test_llm_empty_addrinfo(self):
        with mock.patch("socket.getaddrinfo", return_value=[]):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate_llm_endpoint("http://vllm.local/v1")

    def test_llm_blocks_metadata_ip_via_dns(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 80))]):
            with pytest.raises(SSRFError, match="云元数据"):
                SSRFValidator.validate_llm_endpoint("http://vllm.local/v1")

    def test_llm_skips_bad_ip_strings(self):
        with mock.patch("socket.getaddrinfo", return_value=ONLY_BAD + PRIVATE):
            assert SSRFValidator.validate_llm_endpoint("http://vllm.local/v1") == "http://vllm.local/v1"

    def test_callback_rejects_bad_scheme(self):
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_callback("gopher://x/")

    def test_callback_rejects_missing_host(self):
        with pytest.raises(SSRFError, match="有效主机名"):
            SSRFValidator.validate_callback("http:///cb")

    def test_callback_dns_failure(self):
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror("x")):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate_callback("http://cb.example/")

    def test_callback_empty_addrinfo(self):
        with mock.patch("socket.getaddrinfo", return_value=[]):
            with pytest.raises(SSRFError, match="无法解析"):
                SSRFValidator.validate_callback("http://cb.example/")

    def test_callback_blocks_metadata_ip(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 80))]):
            with pytest.raises(SSRFError, match="云元数据"):
                SSRFValidator.validate_callback("http://cb.example/")

    def test_callback_blocks_loopback_ip(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with pytest.raises(SSRFError, match="localhost"):
                SSRFValidator.validate_callback("http://cb.example/")


class TestWebhookUrlSeam:
    def test_validator_exception_other_than_ssrf_returns_false(self):
        with mock.patch(
            "apps.system_mgmt.utils.channel_utils.SSRFValidator.validate",
            side_effect=RuntimeError("boom"),
        ):
            assert is_valid_webhook_url("https://example.com/") is False

    def test_true_when_validate_ok(self):
        with mock.patch(
            "apps.system_mgmt.utils.channel_utils.SSRFValidator.validate",
            return_value="https://example.com/",
        ):
            assert is_valid_webhook_url("https://example.com/") is True


class TestNetworkWhitelistCacheCoverage:
    """全部 mock，避免本机 test DB / DummyCache 干扰。"""

    def test_load_filters_empty_values(self):
        from apps.system_mgmt.utils.network_whitelist_cache import _load_whitelist_from_db

        rows = [
            {"network": "10.0.0.0/8", "domain_name": ""},
            {"network": "", "domain_name": "corp.example.com"},
            {"network": None, "domain_name": None},
        ]
        fake_qs = mock.Mock()
        fake_qs.values.return_value = rows
        with mock.patch(
            "apps.system_mgmt.models.network_white_list.NetworkWhiteList.objects.filter",
            return_value=fake_qs,
        ):
            cidrs, domains = _load_whitelist_from_db()
        assert cidrs == ["10.0.0.0/8"]
        assert domains == ["corp.example.com"]

    def test_legacy_list_cache_discarded_then_reload(self):
        from apps.system_mgmt.utils import network_whitelist_cache as mod

        with (
            mock.patch.object(mod.cache, "get", return_value=["legacy"]),
            mock.patch.object(mod.cache, "delete") as delete_mock,
            mock.patch.object(mod, "_load_whitelist_from_db", return_value=(["10.1.0.0/16"], ["d.example.com"])),
            mock.patch.object(mod.cache, "set") as set_mock,
        ):
            assert mod.get_network_whitelist_cidrs() == ["10.1.0.0/16"]
            delete_mock.assert_called()
            set_mock.assert_called()

    def test_invalid_cache_payload_reloads(self):
        from apps.system_mgmt.utils import network_whitelist_cache as mod

        with (
            mock.patch.object(mod.cache, "get", return_value={"bad": True}),
            mock.patch.object(mod, "_load_whitelist_from_db", return_value=([], ["a.example.com"])),
            mock.patch.object(mod.cache, "set"),
        ):
            assert mod.get_network_whitelist_domains() == ["a.example.com"]

    def test_tuple_cache_hit_returns_without_db(self):
        from apps.system_mgmt.utils import network_whitelist_cache as mod

        with (
            mock.patch.object(mod.cache, "get", return_value=(["10.0.0.0/8"], ["x.example.com"])),
            mock.patch.object(mod, "_load_whitelist_from_db") as load_mock,
        ):
            assert mod.get_network_whitelist_cidrs() == ["10.0.0.0/8"]
            assert mod.get_network_whitelist_domains() == ["x.example.com"]
            load_mock.assert_not_called()

    def test_load_db_exception_fail_closed(self):
        from apps.system_mgmt.utils.network_whitelist_cache import _load_whitelist_from_db

        with mock.patch(
            "apps.system_mgmt.models.network_white_list.NetworkWhiteList.objects.filter",
            side_effect=RuntimeError("db"),
        ):
            assert _load_whitelist_from_db() == ([], [])

    def test_invalidate_clears_key(self):
        from apps.system_mgmt.utils import network_whitelist_cache as mod

        with mock.patch.object(mod.cache, "delete") as delete_mock:
            mod.invalidate_network_whitelist_cache()
            delete_mock.assert_called_once_with(mod.NETWORK_WHITELIST_CACHE_KEY)

    def test_malformed_tuple_cache_reloads(self):
        from apps.system_mgmt.utils import network_whitelist_cache as mod

        with (
            mock.patch.object(mod.cache, "get", return_value=("only-one",)),
            mock.patch.object(mod, "_load_whitelist_from_db", return_value=(["9.9.9.0/24"], [])),
            mock.patch.object(mod.cache, "set"),
        ):
            assert mod.get_network_whitelist_cidrs() == ["9.9.9.0/24"]


class TestMigration0044:
    def test_remove_deletes_builtin_rows(self):
        mig = import_module("apps.system_mgmt.migrations.0044_remove_builtin_webhook_domains")
        fake_model = mock.Mock()
        apps = mock.Mock()
        apps.get_model.return_value = fake_model
        mig.remove_builtin_webhook_domains(apps, None)
        fake_model.objects.filter.assert_called_once()
        fake_model.objects.filter.return_value.delete.assert_called_once()

    def test_restore_get_or_create_each_domain(self):
        mig = import_module("apps.system_mgmt.migrations.0044_remove_builtin_webhook_domains")
        fake_model = mock.Mock()
        apps = mock.Mock()
        apps.get_model.return_value = fake_model
        mig.restore_builtin_webhook_domains(apps, None)
        assert fake_model.objects.get_or_create.call_count == len(mig.BUILTIN_WEBHOOK_DOMAINS)
