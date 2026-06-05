"""
Tests for Security Controls in OpsPilot Workflow Nodes.

Based on Security Review: bk-lite-security-review-2026-05-27.md

Vulnerabilities covered:
- BK-LITE-001: Jinja2 SSTI (Server-Side Template Injection) in HttpActionNode, AgentNode, NotifyNode
- BK-LITE-002: SSRF (Server-Side Request Forgery) in HttpActionNode, Fetch Tool

Test categories:
1. HttpActionNode SSTI Protection - requestBody, headers, params template injection blocked
2. HttpActionNode SSRF Protection - private IPs, cloud metadata, localhost blocked
3. AgentNode SSTI Protection - prompt template injection blocked
4. NotifyNode SSTI Protection - notification content template injection blocked
5. Fetch Tool SSRF Protection - private IPs, cloud metadata blocked
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def variable_manager():
    """Create a mock VariableManager with common template variables."""
    vm = MagicMock()
    vm.get_all_variables.return_value = {
        "last_message": "Hello, world!",
        "memory_context": "Previous conversation context",
        "user_name": "Alice",
    }
    return vm


@pytest.fixture
def http_action_node(variable_manager):
    """Create HttpActionNode instance with mocked variable_manager."""
    from apps.opspilot.utils.chat_flow_utils.nodes.action.action import HttpActionNode

    node = HttpActionNode(variable_manager)
    return node


@pytest.fixture
def agent_node(variable_manager):
    """Create AgentNode instance with mocked variable_manager."""
    from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

    node = AgentNode(variable_manager)
    return node


@pytest.fixture
def notify_node(variable_manager):
    """Create NotifyNode instance with mocked variable_manager."""
    from apps.opspilot.utils.chat_flow_utils.nodes.action.action import NotifyNode

    node = NotifyNode(variable_manager)
    return node


# ===========================================================================
# BK-LITE-001: HttpActionNode SSTI Protection Tests
# ===========================================================================


class TestHttpActionNodeSSTIProtection:
    """Test SSTI protection in HttpActionNode template rendering."""

    # -----------------------------------------------------------------------
    # requestBody SSTI Tests
    # -----------------------------------------------------------------------

    def test_ssti_in_request_body_cycler_exploit_blocked(self, http_action_node):
        """BK-LITE-001: cycler.__init__.__globals__.os.popen exploit in requestBody is blocked."""
        malicious_body = '{"cmd":"{{ cycler.__init__.__globals__.os.popen(\'id\').read() }}"}'
        template_context = {"last_message": "test"}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_dunder_class_blocked(self, http_action_node):
        """BK-LITE-001: __class__ access in requestBody is blocked."""
        malicious_body = '{"data":"{{ foo.__class__.__mro__ }}"}'
        template_context = {"foo": "bar"}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_dunder_globals_blocked(self, http_action_node):
        """BK-LITE-001: __globals__ access in requestBody is blocked."""
        malicious_body = '{"data":"{{ foo.__init__.__globals__ }}"}'
        template_context = {"foo": "bar"}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_joiner_blocked(self, http_action_node):
        """BK-LITE-001: joiner object access in requestBody is blocked."""
        malicious_body = '{"data":"{{ joiner.__init__.__globals__ }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_namespace_blocked(self, http_action_node):
        """BK-LITE-001: namespace object access in requestBody is blocked."""
        malicious_body = '{"data":"{{ namespace.__init__.__globals__ }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_lipsum_blocked(self, http_action_node):
        """BK-LITE-001: lipsum object access in requestBody is blocked."""
        malicious_body = '{"data":"{{ lipsum.__globals__ }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_os_module_blocked(self, http_action_node):
        """BK-LITE-001: os module access in requestBody is blocked."""
        malicious_body = '{"cmd":"{{ os.popen(\'whoami\').read() }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_subprocess_blocked(self, http_action_node):
        """BK-LITE-001: subprocess module access in requestBody is blocked."""
        malicious_body = '{"cmd":"{{ subprocess.check_output(\'id\') }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_eval_blocked(self, http_action_node):
        """BK-LITE-001: eval function in requestBody is blocked."""
        malicious_body = '{"data":"{{ eval(\'1+1\') }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_exec_blocked(self, http_action_node):
        """BK-LITE-001: exec function in requestBody is blocked."""
        malicious_body = '{"data":"{{ exec(\'import os\') }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_import_blocked(self, http_action_node):
        """BK-LITE-001: import statement in requestBody is blocked."""
        malicious_body = '{"data":"{{ import os }}"}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_jinja2_control_blocked(self, http_action_node):
        """BK-LITE-001: Jinja2 control statements in requestBody are blocked."""
        malicious_body = "{% for i in range(10) %}{{ i }}{% endfor %}"
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_filter_blocked(self, http_action_node):
        """BK-LITE-001: Jinja2 filters in requestBody are blocked."""
        malicious_body = '{{ "test"|upper }}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_subscript_blocked(self, http_action_node):
        """BK-LITE-001: subscript/slice access in requestBody is blocked."""
        malicious_body = "{{ foo[0] }}"
        template_context = {"foo": ["a", "b"]}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_function_call_blocked(self, http_action_node):
        """BK-LITE-001: function calls in requestBody are blocked."""
        malicious_body = "{{ foo() }}"
        template_context = {"foo": lambda: "bar"}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_mro_blocked(self, http_action_node):
        """BK-LITE-001: MRO chain access in requestBody is blocked."""
        malicious_body = '{{ "".__class__.mro() }}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_subclasses_blocked(self, http_action_node):
        """BK-LITE-001: subclasses enumeration in requestBody is blocked."""
        malicious_body = '{{ "".__class__.__subclasses__() }}'
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_getattr_blocked(self, http_action_node):
        """BK-LITE-001: getattr function in requestBody is blocked."""
        malicious_body = '{{ getattr(foo, "__class__") }}'
        template_context = {"foo": "bar"}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_builtins_blocked(self, http_action_node):
        """BK-LITE-001: builtins access in requestBody is blocked."""
        malicious_body = "{{ __builtins__ }}"
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_request_object_blocked(self, http_action_node):
        """BK-LITE-001: request object access in requestBody is blocked."""
        malicious_body = "{{ request.environ }}"
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    def test_ssti_in_request_body_config_object_blocked(self, http_action_node):
        """BK-LITE-001: config object access in requestBody is blocked."""
        malicious_body = "{{ config.items() }}"
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._render_template(malicious_body, "node_001", template_context)

    # -----------------------------------------------------------------------
    # Safe Template Variable Tests (Positive Cases)
    # -----------------------------------------------------------------------

    def test_safe_variable_in_request_body_allowed(self, http_action_node):
        """Safe simple variable substitution in requestBody works correctly."""
        safe_body = '{"message":"{{ last_message }}"}'
        template_context = {"last_message": "Hello, world!"}

        result = http_action_node._render_template(safe_body, "node_001", template_context)
        assert result == '{"message":"Hello, world!"}'

    def test_safe_nested_variable_in_request_body_allowed(self, http_action_node):
        """Safe nested property access in requestBody works correctly."""
        safe_body = '{"user":"{{ user.name }}"}'
        template_context = {"user": {"name": "Alice"}}

        result = http_action_node._render_template(safe_body, "node_001", template_context)
        assert result == '{"user":"Alice"}'

    def test_safe_multiple_variables_in_request_body_allowed(self, http_action_node):
        """Multiple safe variables in requestBody work correctly."""
        safe_body = '{"msg":"{{ last_message }}","ctx":"{{ memory_context }}"}'
        template_context = {"last_message": "Hello", "memory_context": "Previous context"}

        result = http_action_node._render_template(safe_body, "node_001", template_context)
        assert result == '{"msg":"Hello","ctx":"Previous context"}'

    def test_empty_template_returns_empty(self, http_action_node):
        """Empty template returns empty string."""
        result = http_action_node._render_template("", "node_001", {})
        assert result == ""

    def test_none_template_returns_none(self, http_action_node):
        """None template returns None."""
        result = http_action_node._render_template(None, "node_001", {})
        assert result is None

    def test_template_without_variables_unchanged(self, http_action_node):
        """Template without variables is returned unchanged."""
        plain_body = '{"static":"value"}'
        result = http_action_node._render_template(plain_body, "node_001", {})
        assert result == plain_body

    # -----------------------------------------------------------------------
    # Header SSTI Tests
    # -----------------------------------------------------------------------

    def test_ssti_in_header_value_blocked(self, http_action_node):
        """BK-LITE-001: SSTI payload in header value is blocked."""
        headers = [{"key": "X-Custom", "value": "{{ cycler.__init__.__globals__ }}"}]
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._process_key_value_pairs(headers, "header", "node_001", template_context)

    def test_safe_variable_in_header_allowed(self, http_action_node):
        """Safe variable in header value works correctly."""
        headers = [{"key": "X-User", "value": "{{ user_name }}"}]
        template_context = {"user_name": "Alice"}

        result = http_action_node._process_key_value_pairs(headers, "header", "node_001", template_context)
        assert result == {"X-User": "Alice"}

    # -----------------------------------------------------------------------
    # Params SSTI Tests
    # -----------------------------------------------------------------------

    def test_ssti_in_param_value_blocked(self, http_action_node):
        """BK-LITE-001: SSTI payload in param value is blocked."""
        params = [{"key": "query", "value": "{{ os.popen('id').read() }}"}]
        template_context = {}

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node._process_key_value_pairs(params, "参数", "node_001", template_context)

    def test_safe_variable_in_param_allowed(self, http_action_node):
        """Safe variable in param value works correctly."""
        params = [{"key": "q", "value": "{{ last_message }}"}]
        template_context = {"last_message": "search query"}

        result = http_action_node._process_key_value_pairs(params, "参数", "node_001", template_context)
        assert result == {"q": "search query"}


# ===========================================================================
# BK-LITE-002: HttpActionNode SSRF Protection Tests
# ===========================================================================


class TestHttpActionNodeSSRFProtection:
    """Test SSRF protection in HttpActionNode HTTP requests."""

    @patch("socket.getaddrinfo")
    def test_ssrf_localhost_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: localhost URL is blocked."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://localhost/admin",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    def test_ssrf_127_0_0_1_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: 127.0.0.1 URL is blocked."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 8000))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://127.0.0.1:8000/admin/",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    def test_ssrf_aws_metadata_blocked(self, http_action_node):
        """BK-LITE-002: AWS metadata URL (169.254.169.254) is blocked."""
        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://169.254.169.254/latest/meta-data/",
                    "timeout": 3,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    def test_ssrf_gcp_metadata_blocked(self, http_action_node):
        """BK-LITE-002: GCP metadata URL (metadata.google.internal) is blocked."""
        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://metadata.google.internal/computeMetadata/v1/",
                    "timeout": 3,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    def test_ssrf_10_x_x_x_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: 10.x.x.x private network is blocked."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://internal.company.com/api",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    def test_ssrf_172_16_x_x_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: 172.16.x.x private network is blocked."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 80))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://internal.company.com/api",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    def test_ssrf_192_168_x_x_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: 192.168.x.x private network is blocked."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.1", 80))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://router.local/admin",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    def test_ssrf_ipv6_loopback_blocked(self, mock_getaddrinfo, http_action_node):
        """BK-LITE-002: IPv6 loopback (::1) is blocked."""
        mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 80, 0, 0))]

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://[::1]/admin",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    def test_ssrf_file_protocol_blocked(self, http_action_node):
        """BK-LITE-002: file:// protocol is blocked."""
        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "file:///etc/passwd",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    def test_ssrf_ftp_protocol_blocked(self, http_action_node):
        """BK-LITE-002: ftp:// protocol is blocked."""
        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "ftp://internal.server/file",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_public_url_allowed(self, mock_request, mock_getaddrinfo, http_action_node):
        """Public URL is allowed through SSRF validation."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response

        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "https://example.com/api",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        result = http_action_node.execute("node_001", node_config, {})
        assert result == {"result": {"status": "ok"}}


# ===========================================================================
# BK-LITE-001: AgentNode SSTI Protection Tests
# ===========================================================================


class TestAgentNodeSSTIProtection:
    """Test SSTI protection in AgentNode prompt rendering."""

    def test_ssti_in_prompt_cycler_exploit_blocked(self, agent_node):
        """BK-LITE-001: cycler exploit in prompt is blocked."""
        malicious_prompt = "Execute: {{ cycler.__init__.__globals__.os.popen('id').read() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_dunder_class_blocked(self, agent_node):
        """BK-LITE-001: __class__ access in prompt is blocked."""
        malicious_prompt = "Data: {{ foo.__class__.__mro__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_dunder_globals_blocked(self, agent_node):
        """BK-LITE-001: __globals__ access in prompt is blocked."""
        malicious_prompt = "Data: {{ foo.__init__.__globals__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_joiner_blocked(self, agent_node):
        """BK-LITE-001: joiner object in prompt is blocked."""
        malicious_prompt = "{{ joiner.__init__.__globals__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_namespace_blocked(self, agent_node):
        """BK-LITE-001: namespace object in prompt is blocked."""
        malicious_prompt = "{{ namespace.__init__.__globals__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_lipsum_blocked(self, agent_node):
        """BK-LITE-001: lipsum object in prompt is blocked."""
        malicious_prompt = "{{ lipsum.__globals__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_os_module_blocked(self, agent_node):
        """BK-LITE-001: os module access in prompt is blocked."""
        malicious_prompt = "{{ os.popen('whoami').read() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_subprocess_blocked(self, agent_node):
        """BK-LITE-001: subprocess module in prompt is blocked."""
        malicious_prompt = "{{ subprocess.check_output('id') }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_eval_blocked(self, agent_node):
        """BK-LITE-001: eval function in prompt is blocked."""
        malicious_prompt = '{{ eval(\'__import__("os").system("id")\') }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_exec_blocked(self, agent_node):
        """BK-LITE-001: exec function in prompt is blocked."""
        malicious_prompt = "{{ exec('import os') }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_import_blocked(self, agent_node):
        """BK-LITE-001: import statement in prompt is blocked."""
        malicious_prompt = "{{ import os }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_jinja2_control_blocked(self, agent_node):
        """BK-LITE-001: Jinja2 control statements in prompt are blocked."""
        malicious_prompt = "{% for i in range(10) %}{{ i }}{% endfor %}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_filter_blocked(self, agent_node):
        """BK-LITE-001: Jinja2 filters in prompt are blocked."""
        malicious_prompt = '{{ "test"|upper }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_subscript_blocked(self, agent_node):
        """BK-LITE-001: subscript access in prompt is blocked."""
        malicious_prompt = "{{ foo[0] }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_function_call_blocked(self, agent_node):
        """BK-LITE-001: function calls in prompt are blocked."""
        malicious_prompt = "{{ foo() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_mro_blocked(self, agent_node):
        """BK-LITE-001: MRO chain access in prompt is blocked."""
        malicious_prompt = '{{ "".__class__.mro() }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_subclasses_blocked(self, agent_node):
        """BK-LITE-001: subclasses enumeration in prompt is blocked."""
        malicious_prompt = '{{ "".__class__.__subclasses__() }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_getattr_blocked(self, agent_node):
        """BK-LITE-001: getattr function in prompt is blocked."""
        malicious_prompt = '{{ getattr(foo, "__class__") }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_builtins_blocked(self, agent_node):
        """BK-LITE-001: builtins access in prompt is blocked."""
        malicious_prompt = "{{ __builtins__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_request_object_blocked(self, agent_node):
        """BK-LITE-001: request object access in prompt is blocked."""
        malicious_prompt = "{{ request.environ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    def test_ssti_in_prompt_config_object_blocked(self, agent_node):
        """BK-LITE-001: config object access in prompt is blocked."""
        malicious_prompt = "{{ config.items() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            agent_node._render_prompt(malicious_prompt, "agent_001")

    # -----------------------------------------------------------------------
    # Safe Template Variable Tests (Positive Cases)
    # -----------------------------------------------------------------------

    def test_safe_variable_in_prompt_allowed(self, agent_node):
        """Safe simple variable in prompt works correctly."""
        safe_prompt = "User said: {{ last_message }}"

        result = agent_node._render_prompt(safe_prompt, "agent_001")
        assert result == "User said: Hello, world!"

    def test_safe_nested_variable_in_prompt_allowed(self, agent_node):
        """Safe nested property in prompt works correctly."""
        agent_node.variable_manager.get_all_variables.return_value = {"user": {"name": "Alice"}}
        safe_prompt = "Hello, {{ user.name }}!"

        result = agent_node._render_prompt(safe_prompt, "agent_001")
        assert result == "Hello, Alice!"

    def test_safe_memory_context_in_prompt_allowed(self, agent_node):
        """memory_context variable in prompt works correctly (real ChatFlow use case)."""
        safe_prompt = "Context: {{ memory_context }}\nUser: {{ last_message }}"

        result = agent_node._render_prompt(safe_prompt, "agent_001")
        assert "Previous conversation context" in result
        assert "Hello, world!" in result

    def test_empty_prompt_returns_empty(self, agent_node):
        """Empty prompt returns empty string."""
        result = agent_node._render_prompt("", "agent_001")
        assert result == ""

    def test_none_prompt_returns_empty(self, agent_node):
        """None prompt returns empty string."""
        result = agent_node._render_prompt(None, "agent_001")
        assert result == ""

    def test_prompt_without_variables_unchanged(self, agent_node):
        """Prompt without variables is returned unchanged."""
        plain_prompt = "You are a helpful assistant."
        result = agent_node._render_prompt(plain_prompt, "agent_001")
        assert result == plain_prompt


# ===========================================================================
# BK-LITE-001: NotifyNode SSTI Protection Tests
# ===========================================================================


class TestNotifyNodeSSTIProtection:
    """Test SSTI protection in NotifyNode content rendering."""

    def test_ssti_in_notification_content_cycler_blocked(self, notify_node):
        """BK-LITE-001: cycler exploit in notification content is blocked."""
        malicious_content = "Alert: {{ cycler.__init__.__globals__.os.popen('id').read() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_ssti_in_notification_content_dunder_blocked(self, notify_node):
        """BK-LITE-001: dunder access in notification content is blocked."""
        malicious_content = "Data: {{ foo.__class__.__mro__ }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_ssti_in_notification_content_os_blocked(self, notify_node):
        """BK-LITE-001: os module in notification content is blocked."""
        malicious_content = "{{ os.popen('whoami').read() }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_ssti_in_notification_content_eval_blocked(self, notify_node):
        """BK-LITE-001: eval function in notification content is blocked."""
        malicious_content = "{{ eval('1+1') }}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_ssti_in_notification_content_jinja2_control_blocked(self, notify_node):
        """BK-LITE-001: Jinja2 control statements in notification content are blocked."""
        malicious_content = "{% for i in range(10) %}{{ i }}{% endfor %}"

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_ssti_in_notification_content_filter_blocked(self, notify_node):
        """BK-LITE-001: Jinja2 filters in notification content are blocked."""
        malicious_content = '{{ "test"|upper }}'

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            notify_node._render_content(malicious_content, "notify_001")

    def test_safe_variable_in_notification_content_allowed(self, notify_node):
        """Safe variable in notification content works correctly."""
        safe_content = "User {{ user_name }} sent: {{ last_message }}"

        result = notify_node._render_content(safe_content, "notify_001")
        assert result == "User Alice sent: Hello, world!"

    def test_empty_notification_content_returns_empty(self, notify_node):
        """Empty notification content returns empty string."""
        result = notify_node._render_content("", "notify_001")
        assert result == ""

    def test_none_notification_content_returns_none(self, notify_node):
        """None notification content returns None."""
        result = notify_node._render_content(None, "notify_001")
        assert result is None


# ===========================================================================
# BK-LITE-002: Fetch Tool SSRF Protection Tests
# ===========================================================================


class TestFetchToolSSRFProtection:
    """Test SSRF protection in Fetch Tool URL validation."""

    def test_fetch_validate_url_localhost_blocked(self):
        """BK-LITE-002: localhost URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://localhost/admin")

    def test_fetch_validate_url_127_0_0_1_blocked(self):
        """BK-LITE-002: 127.0.0.1 URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://127.0.0.1:8000/api")

    def test_fetch_validate_url_aws_metadata_blocked(self):
        """BK-LITE-002: AWS metadata URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_fetch_validate_url_gcp_metadata_blocked(self):
        """BK-LITE-002: GCP metadata URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://metadata.google.internal/computeMetadata/v1/")

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_10_x_x_x_blocked(self, mock_getaddrinfo):
        """BK-LITE-002: 10.x.x.x private network is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://internal.company.com/api")

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_172_16_x_x_blocked(self, mock_getaddrinfo):
        """BK-LITE-002: 172.16.x.x private network is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 80))]

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://internal.company.com/api")

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_192_168_x_x_blocked(self, mock_getaddrinfo):
        """BK-LITE-002: 192.168.x.x private network is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.1", 80))]

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://router.local/admin")

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_ipv6_loopback_blocked(self, mock_getaddrinfo):
        """BK-LITE-002: IPv6 loopback is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 80, 0, 0))]

        with pytest.raises((ValueError, SSRFError)):
            validate_url("http://[::1]/admin")

    def test_fetch_validate_url_file_protocol_blocked(self):
        """BK-LITE-002: file:// protocol is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises((ValueError, SSRFError)):
            validate_url("file:///etc/passwd")

    def test_fetch_validate_url_empty_blocked(self):
        """Empty URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises(ValueError, match="URL不能为空"):
            validate_url("")

    def test_fetch_validate_url_none_blocked(self):
        """None URL is blocked in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        with pytest.raises(ValueError, match="URL不能为空"):
            validate_url(None)

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_public_allowed(self, mock_getaddrinfo):
        """Public URL is allowed in Fetch tool."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        result = validate_url("https://example.com/api")
        assert result == "https://example.com/api"

    @patch("socket.getaddrinfo")
    def test_fetch_validate_url_adds_https_prefix(self, mock_getaddrinfo):
        """URL without protocol gets https:// prefix added."""
        from apps.opspilot.metis.llm.tools.fetch.utils import validate_url

        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        result = validate_url("example.com/api")
        assert result == "https://example.com/api"


# ===========================================================================
# Integration Tests: Full Node Execution with Security Controls
# ===========================================================================


class TestSecurityIntegration:
    """Integration tests verifying security controls in full node execution."""

    @patch("socket.getaddrinfo")
    @patch("apps.core.utils.safe_requests.requests.request")
    def test_http_action_node_full_execution_with_safe_template_and_public_url(self, mock_request, mock_getaddrinfo, http_action_node):
        """Full HttpActionNode execution with safe template and public URL succeeds."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        mock_response = MagicMock()
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"echo": "Hello, world!"}
        mock_request.return_value = mock_response

        node_config = {
            "data": {
                "config": {
                    "method": "POST",
                    "url": "https://example.com/api",
                    "timeout": 5,
                    "requestBody": '{"message":"{{ last_message }}"}',
                    "headers": [{"key": "X-User", "value": "{{ user_name }}"}],
                    "outputParams": "result",
                }
            }
        }

        result = http_action_node.execute("node_001", node_config, {})
        assert result == {"result": {"echo": "Hello, world!"}}

    def test_http_action_node_rejects_ssti_in_full_execution(self, http_action_node):
        """Full HttpActionNode execution rejects SSTI payload."""
        node_config = {
            "data": {
                "config": {
                    "method": "POST",
                    "url": "https://example.com/api",
                    "timeout": 5,
                    "requestBody": '{"cmd":"{{ cycler.__init__.__globals__.os.popen(\'id\').read() }}"}',
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises(ValueError, match="模板包含不安全内容"):
            http_action_node.execute("node_001", node_config, {})

    def test_http_action_node_rejects_ssrf_in_full_execution(self, http_action_node):
        """Full HttpActionNode execution rejects SSRF URL."""
        node_config = {
            "data": {
                "config": {
                    "method": "GET",
                    "url": "http://169.254.169.254/latest/meta-data/",
                    "timeout": 5,
                    "outputParams": "result",
                }
            }
        }

        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})

    def test_combined_ssti_and_ssrf_attack_blocked(self, http_action_node):
        """Combined SSTI + SSRF attack is blocked (SSTI checked first)."""
        node_config = {
            "data": {
                "config": {
                    "method": "POST",
                    "url": "http://169.254.169.254/latest/meta-data/",
                    "timeout": 5,
                    "requestBody": '{"cmd":"{{ cycler.__init__.__globals__.os.popen(\'id\').read() }}"}',
                    "outputParams": "result",
                }
            }
        }

        # Either SSTI or SSRF error is acceptable - both attacks are blocked
        with pytest.raises((ValueError, SSRFError)):
            http_action_node.execute("node_001", node_config, {})
