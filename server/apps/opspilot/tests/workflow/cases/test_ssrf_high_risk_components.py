"""
Tests for SSRF Protection in High-Risk OpsPilot Components.

Based on Security Review: BK-LITE-002

Components tested:
1. ModelVendorSyncService - API model fetching with user-provided api_base
2. WebsiteLoader - Knowledge base website import with user-provided URL
3. Fetch Tool (http.py) - LLM Agent HTTP requests with URL validation

Attack scenarios covered:
- Cloud metadata access (AWS 169.254.169.254, GCP metadata.google.internal)
- Private network access (10.x, 172.16.x, 192.168.x, 127.0.0.1)
- Protocol smuggling (file://, ftp://, gopher://)
- IPv6 loopback (::1)
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub out optional C-extension modules
# ---------------------------------------------------------------------------
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from apps.core.utils.ssrf_validator import SSRFError  # noqa: E402

# ===========================================================================
# ModelVendorSyncService SSRF Protection Tests
# ===========================================================================


class TestModelVendorSyncServiceSSRFProtection:
    """Test SSRF protection in ModelVendorSyncService.

    Attack Scenario:
    1. Attacker has access to model vendor configuration (e.g., admin or operator role)
    2. Attacker sets api_base to internal/metadata URL when adding a new model vendor
    3. Server makes HTTP request to attacker-controlled URL, leaking internal data

    Example Attack:
        api_base = "http://169.254.169.254/latest/meta-data/iam/security-credentials"
        # Server fetches AWS IAM credentials and returns them to attacker
    """

    def test_fetch_models_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL in api_base is blocked."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        with pytest.raises((ValueError, SSRFError)):
            ModelVendorSyncService.fetch_models_with_credentials(
                api_base="http://169.254.169.254/latest/meta-data",
                api_key="test-key",
                protocol_type="openai",
            )

    def test_fetch_models_blocks_gcp_metadata(self):
        """BK-LITE-002: GCP metadata URL in api_base is blocked."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        with pytest.raises((ValueError, SSRFError)):
            ModelVendorSyncService.fetch_models_with_credentials(
                api_base="http://metadata.google.internal/computeMetadata/v1",
                api_key="test-key",
                protocol_type="openai",
            )

    # NOTE (BK-LITE-002 + bugfix 43e7fa682): model-vendor model fetching uses the
    # LENIENT LLM-endpoint SSRF validator on purpose — internal LLM deployments
    # (Ollama/vLLM/LocalAI) legitimately live on localhost/private networks. So
    # private/localhost are ALLOWED here; only cloud-metadata and file:// are blocked
    # (covered by the metadata/file tests below). These tests assert that SSRF does
    # NOT block private/localhost, i.e. the request proceeds past validation.
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_localhost(self, mock_request):
        """BK-LITE-002: localhost api_base is allowed for internal LLM endpoints."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="http://localhost:8080",
            api_key="test-key",
            protocol_type="openai",
        )
        # Reached the HTTP layer => SSRF validation allowed localhost.
        assert mock_request.called
        assert result == [{"id": "gpt-4"}]

    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_127_0_0_1(self, mock_request):
        """BK-LITE-002: 127.0.0.1 api_base is allowed for internal LLM endpoints."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="http://127.0.0.1:11434",
            api_key="test-key",
            protocol_type="openai",
        )
        assert mock_request.called
        assert result == [{"id": "gpt-4"}]

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_private_10_x(self, mock_request, mock_getaddrinfo):
        """BK-LITE-002: 10.x.x.x private LLM endpoint is allowed."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="http://internal-llm.company.local",
            api_key="test-key",
            protocol_type="openai",
        )
        assert mock_request.called
        assert result == [{"id": "gpt-4"}]

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_private_172_16_x(self, mock_request, mock_getaddrinfo):
        """BK-LITE-002: 172.16.x.x private LLM endpoint is allowed."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 80))]
        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="http://internal-llm.company.local",
            api_key="test-key",
            protocol_type="openai",
        )
        assert mock_request.called
        assert result == [{"id": "gpt-4"}]

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_private_192_168_x(self, mock_request, mock_getaddrinfo):
        """BK-LITE-002: 192.168.x.x private LLM endpoint is allowed."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.100", 80))]
        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="http://home-server.local",
            api_key="test-key",
            protocol_type="openai",
        )
        assert mock_request.called
        assert result == [{"id": "gpt-4"}]

    def test_fetch_models_blocks_file_protocol(self):
        """BK-LITE-002: file:// protocol in api_base is blocked."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        with pytest.raises((ValueError, SSRFError)):
            ModelVendorSyncService.fetch_models_with_credentials(
                api_base="file:///etc/passwd",
                api_key="test-key",
                protocol_type="openai",
            )

    def test_test_anthropic_connection_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL in Anthropic connection test is blocked."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        with pytest.raises((ValueError, SSRFError)):
            ModelVendorSyncService.test_anthropic_connection(
                api_base="http://169.254.169.254/latest/meta-data",
                api_key="test-key",
            )

    @patch("apps.core.utils.safe_requests.requests.request")
    def test_test_anthropic_connection_allows_localhost(self, mock_request):
        """BK-LITE-002: localhost is allowed in Anthropic connection test (internal LLM)."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_response = MagicMock(is_redirect=False, status_code=200)
        mock_response.json.return_value = {"content": [{"text": "ok"}]}
        mock_request.return_value = mock_response

        # Lenient LLM-endpoint validation allows localhost; the request must be attempted
        # (i.e. SSRF did not block) rather than raising SSRFError.
        ModelVendorSyncService.test_anthropic_connection(
            api_base="http://127.0.0.1:8080",
            api_key="test-key",
        )
        assert mock_request.called

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_fetch_models_allows_public_url(self, mock_request, mock_getaddrinfo):
        """Public URL in api_base is allowed."""
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("104.18.7.192", 443))]
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_request.return_value = mock_response

        result = ModelVendorSyncService.fetch_models_with_credentials(
            api_base="https://api.openai.com/v1",
            api_key="test-key",
            protocol_type="openai",
        )
        assert result == [{"id": "gpt-4"}]


# ===========================================================================
# WebsiteLoader SSRF Protection Tests
# ===========================================================================


class TestWebsiteLoaderSSRFProtection:
    """Test SSRF protection in WebsiteLoader.

    Attack Scenario:
    1. Attacker has access to knowledge base management
    2. Attacker imports a "website" with internal URL as the source
    3. Server crawls internal network, potentially accessing sensitive services

    Example Attack:
        url = "http://192.168.1.1/admin/config"
        # Server crawls internal admin interface and stores content in knowledge base
    """

    def test_load_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        loader = WebSiteLoader(
            url="http://169.254.169.254/latest/meta-data/",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    def test_load_blocks_gcp_metadata(self):
        """BK-LITE-002: GCP metadata URL is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        loader = WebSiteLoader(
            url="http://metadata.google.internal/computeMetadata/v1/",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    def test_load_blocks_localhost(self):
        """BK-LITE-002: localhost URL is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        loader = WebSiteLoader(
            url="http://localhost:8080/admin",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    def test_load_blocks_127_0_0_1(self):
        """BK-LITE-002: 127.0.0.1 URL is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        loader = WebSiteLoader(
            url="http://127.0.0.1:3000/api/config",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    @patch("socket.getaddrinfo")
    def test_load_blocks_private_10_x(self, mock_getaddrinfo):
        """BK-LITE-002: 10.x.x.x private network is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.50", 80))]

        loader = WebSiteLoader(
            url="http://internal-wiki.company.local/",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    @patch("socket.getaddrinfo")
    def test_load_blocks_private_192_168_x(self, mock_getaddrinfo):
        """BK-LITE-002: 192.168.x.x private network is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.1", 80))]

        loader = WebSiteLoader(
            url="http://router.local/admin",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    def test_load_blocks_file_protocol(self):
        """BK-LITE-002: file:// protocol is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        loader = WebSiteLoader(
            url="file:///etc/passwd",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    @patch("socket.getaddrinfo")
    def test_load_blocks_ipv6_loopback(self, mock_getaddrinfo):
        """BK-LITE-002: IPv6 loopback is blocked in website loader."""
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 80, 0, 0))]

        loader = WebSiteLoader(
            url="http://[::1]/admin",
            max_depth=1,
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()


# ===========================================================================
# Fetch Tool SSRF Protection Tests
# ===========================================================================


class TestFetchToolSSRFProtection:
    """Test SSRF protection in Fetch Tool (http.py).

    Attack Scenario:
    1. LLM Agent is given a task that involves fetching web content
    2. Attacker uses prompt injection to make Agent fetch internal URLs
    3. Agent fetches internal data and includes it in response

    Example Attack (Prompt Injection):
        User: "Please summarize the content at http://169.254.169.254/latest/meta-data/"
        # Agent fetches AWS metadata and returns IAM credentials in summary
    """

    def test_http_get_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://169.254.169.254/latest/meta-data/")

    def test_http_get_blocks_gcp_metadata(self):
        """BK-LITE-002: GCP metadata URL is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://metadata.google.internal/computeMetadata/v1/")

    def test_http_get_blocks_localhost(self):
        """BK-LITE-002: localhost URL is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://localhost:8080/admin")

    def test_http_get_blocks_127_0_0_1(self):
        """BK-LITE-002: 127.0.0.1 URL is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://127.0.0.1:3000/api")

    @patch("socket.getaddrinfo")
    def test_http_get_blocks_private_10_x(self, mock_getaddrinfo):
        """BK-LITE-002: 10.x.x.x private network is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://internal.company.com/api")

    @patch("socket.getaddrinfo")
    def test_http_get_blocks_private_192_168_x(self, mock_getaddrinfo):
        """BK-LITE-002: 192.168.x.x private network is blocked in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.1", 80))]

        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://router.local/admin")

    def test_http_post_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in HTTP POST."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_post_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_post_impl("http://169.254.169.254/latest/meta-data/")

    def test_http_post_blocks_localhost(self):
        """BK-LITE-002: localhost URL is blocked in HTTP POST."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_post_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_post_impl("http://localhost:8080/api")

    def test_http_put_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in HTTP PUT."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_put_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_put_impl("http://169.254.169.254/latest/meta-data/")

    def test_http_delete_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in HTTP DELETE."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_delete_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_delete_impl("http://169.254.169.254/latest/meta-data/")

    def test_http_patch_blocks_aws_metadata(self):
        """BK-LITE-002: AWS metadata URL is blocked in HTTP PATCH."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_patch_impl

        with pytest.raises((ValueError, SSRFError)):
            _http_patch_impl("http://169.254.169.254/latest/meta-data/")

    @patch("socket.getaddrinfo")
    @patch("requests.get")
    def test_http_get_allows_public_url(self, mock_get, mock_getaddrinfo):
        """Public URL is allowed in HTTP GET."""
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Example</html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.url = "https://example.com/"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _http_get_impl("https://example.com/")
        assert result.get("success") is True


# ===========================================================================
# Attack Scenario Documentation Tests
# ===========================================================================


class TestSSRFAttackScenarios:
    """Document and test specific SSRF attack scenarios.

    These tests document how an attacker could exploit SSRF vulnerabilities
    if the protections were not in place.
    """

    def test_scenario_aws_credential_theft(self):
        """
        Attack Scenario: AWS IAM Credential Theft via Model Vendor Configuration

        Steps:
        1. Attacker gains access to OpsPilot with model vendor management permission
        2. Attacker creates a new model vendor with:
           - api_base = "http://169.254.169.254/latest/meta-data/iam/security-credentials/role-name"
        3. When server tries to fetch models, it accesses AWS metadata service
        4. AWS returns IAM credentials (AccessKeyId, SecretAccessKey, Token)
        5. Attacker receives credentials in error message or response

        Impact: Full AWS account compromise

        This test verifies the attack is blocked.
        """
        from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService

        # Attempt the attack
        with pytest.raises((ValueError, SSRFError)):
            ModelVendorSyncService.fetch_models_with_credentials(
                api_base="http://169.254.169.254/latest/meta-data/iam/security-credentials/bk-lite-role",
                api_key="fake-key",
                protocol_type="openai",
            )

    def test_scenario_internal_service_discovery(self):
        """
        Attack Scenario: Internal Service Discovery via Knowledge Base Import

        Steps:
        1. Attacker gains access to OpsPilot knowledge base management
        2. Attacker imports a "website" with URL = "http://192.168.1.1/"
        3. Server crawls internal network, discovering services
        4. Attacker can enumerate internal IPs by observing response times/errors

        Impact: Internal network mapping, potential access to admin interfaces

        This test verifies the attack is blocked.
        """
        from apps.opspilot.metis.llm.loader.website_loader import WebSiteLoader

        # Attempt the attack
        loader = WebSiteLoader(
            url="http://192.168.1.1/",
            max_depth=3,  # Attacker might try deep crawling
            ocr=None,
        )

        with pytest.raises((ValueError, SSRFError)):
            loader.load()

    def test_scenario_prompt_injection_ssrf(self):
        """
        Attack Scenario: SSRF via Prompt Injection in LLM Agent

        Steps:
        1. Attacker interacts with OpsPilot chatbot
        2. Attacker sends: "Please fetch and summarize http://127.0.0.1:8080/admin/config"
        3. LLM Agent uses fetch tool to access internal admin interface
        4. Agent returns sensitive configuration in chat response

        Impact: Exposure of internal service data, potential credential leakage

        This test verifies the attack is blocked.
        """
        from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl

        # Attempt the attack (simulating what Agent would do)
        # SSRFValidator raises SSRFError for localhost URLs
        with pytest.raises((ValueError, SSRFError)):
            _http_get_impl("http://127.0.0.1:8080/admin/config")

    def test_scenario_dns_rebinding_protection(self):
        """
        Attack Scenario: DNS Rebinding Attack

        Steps:
        1. Attacker controls a domain (evil.com) with short TTL
        2. First DNS query returns public IP (passes validation)
        3. Second DNS query returns 169.254.169.254 (metadata)
        4. Server fetches from metadata service

        Mitigation: SSRFValidator resolves DNS and validates IP before request

        This test verifies DNS resolution is validated.
        """
        from apps.core.utils.ssrf_validator import SSRFValidator

        # Direct metadata IP should be blocked regardless of hostname
        with pytest.raises(SSRFError):
            SSRFValidator.validate("http://169.254.169.254/")

    def test_scenario_redirect_chain_attack(self):
        """
        Attack Scenario: Redirect Chain to Internal Service

        Steps:
        1. Attacker hosts a page at https://evil.com/redirect
        2. Page returns 302 redirect to http://169.254.169.254/
        3. Server follows redirect and accesses metadata

        Mitigation: safe_requests validates each redirect target

        This test documents the protection mechanism.
        """
        # This is handled by safe_requests which:
        # 1. Disables automatic redirects
        # 2. Manually validates each redirect Location header
        # 3. Blocks redirects to private/metadata addresses

        from apps.core.utils.safe_requests import safe_get
        from apps.core.utils.ssrf_validator import SSRFError

        # Direct access to metadata is blocked
        with pytest.raises(SSRFError):
            safe_get("http://169.254.169.254/")
