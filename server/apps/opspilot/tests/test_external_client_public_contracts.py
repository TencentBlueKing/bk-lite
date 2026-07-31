"""MCP、Elasticsearch 与 Jenkins 公共客户端契约。"""

from types import SimpleNamespace as NS
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.elasticsearch import connection as es
from apps.opspilot.metis.llm.tools.jenkins import connection as jenkins_conn
from apps.opspilot.services import mcp_client


pytestmark = pytest.mark.unit


class ExternalMCPRuntime:
    received = None

    def __init__(self, config):
        self.__class__.received = config

    async def get_tools(self):
        return [
            NS(
                name="inspect_cluster",
                description="Inspect cluster health",
                input_schema={
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Kubernetes namespace",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                        },
                    },
                    "required": ["namespace"],
                },
            ),
            NS(
                name="freeform",
                description=None,
                input_schema={
                    "anyOf": [
                        {
                            "type": "object",
                            "additionalProperties": True,
                        }
                    ]
                },
            ),
        ]


def test_mcp_client_context_resolves_transport_auth_and_tool_schema():
    with patch.object(
        mcp_client,
        "MultiServerMCPClient",
        ExternalMCPRuntime,
    ):
        with mcp_client.MCPClient(
            "https://93.184.216.34/mcp?transport=streamable_http",
            timeout=5,
            enable_auth=True,
            auth_token="token-value",
        ) as client:
            tools = client.get_tools()

    assert ExternalMCPRuntime.received == {
        "default": {
            "url": (
                "https://93.184.216.34/mcp"
                "?transport=streamable_http"
            ),
            "timeout": 5,
            "transport": "streamable_http",
            "headers": {"Authorization": "Basic token-value"},
        }
    }
    assert tools[0] == {
        "name": "inspect_cluster",
        "description": "Inspect cluster health",
        "parameters": {
            "namespace": {
                "type": "string",
                "required": True,
                "description": "Kubernetes namespace",
            },
            "limit": {
                "type": "integer",
                "required": False,
                "description": "",
                "default": 20,
            },
        },
    }
    assert tools[1]["parameters"]["__any__"]["required"] is False


def test_mcp_client_requires_context_and_rejects_stdio_protocol():
    client = mcp_client.MCPClient("https://93.184.216.34/sse")
    with pytest.raises(RuntimeError, match="context manager"):
        client.get_tools()
    with pytest.raises(ValueError, match="stdio-mcp protocol"):
        with mcp_client.MCPClient("stdio-mcp:filesystem"):
            pass


def test_mcp_transport_resolution_supports_explicit_and_path_modes():
    assert (
        mcp_client.MCPClient(
            "https://example.com/anything",
            transport="streamable_http",
        )._resolve_transport()
        == "streamable_http"
    )
    assert (
        mcp_client.MCPClient(
            "https://example.com/streamable_http"
        )._resolve_transport()
        == "streamable_http"
    )
    assert (
        mcp_client.MCPClient(
            "https://example.com/events/sse"
        )._resolve_transport()
        == "sse"
    )


def test_elasticsearch_multi_instance_selection_and_prompt():
    config = {
        "configurable": {
            "es_instances": [
                {
                    "id": "es-a",
                    "name": "primary",
                    "url": "https://es-a.example.com",
                    "api_key": "api-key",
                    "verify_certs": "false",
                },
                {
                    "id": "es-b",
                    "name": "archive",
                    "url": "https://es-b.example.com",
                    "username": "reader",
                    "password": "secret",
                },
            ],
            "es_default_instance_id": "es-b",
        }
    }

    normalized = es.build_es_normalized_from_runnable(config)
    selected = es.build_es_normalized_from_runnable(
        config,
        instance_name="primary",
    )
    prompt = es.get_es_instances_prompt(config["configurable"])

    assert normalized["mode"] == "multi"
    assert [item["name"] for item in normalized["items"]] == [
        "primary",
        "archive",
    ]
    assert selected["mode"] == "single"
    assert selected["items"][0]["config"]["api_key"] == "api-key"
    assert selected["items"][0]["config"]["verify_certs"] is False
    assert "默认实例为「archive」" in prompt


def test_elasticsearch_client_maps_auth_tls_and_closes_after_ping():
    clients = []

    class ExternalElasticsearch:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            clients.append(self)

        def ping(self):
            return True

        def close(self):
            self.closed = True

    with patch.object(es, "Elasticsearch", ExternalElasticsearch):
        result = es.test_es_instance(
            {
                "url": "https://es.example.com",
                "username": "reader",
                "password": "secret",
                "verify_certs": True,
                "ca_certs": "/certs/ca.pem",
                "client_cert": "/certs/client.pem",
                "client_key": "/certs/client.key",
            }
        )

    assert result is True
    assert clients[0].kwargs == {
        "hosts": ["https://es.example.com"],
        "verify_certs": True,
        "http_auth": ("reader", "secret"),
        "ca_certs": "/certs/ca.pem",
        "client_cert": "/certs/client.pem",
        "client_key": "/certs/client.key",
    }
    assert clients[0].closed is True


def test_jenkins_multi_instance_selection_and_prompt():
    config = {
        "configurable": {
            "jenkins_instances": [
                {
                    "id": "jenkins-a",
                    "name": "delivery",
                    "jenkins_url": "https://ci-a.example.com",
                    "jenkins_username": "builder",
                    "jenkins_password": "secret-a",
                },
                {
                    "id": "jenkins-b",
                    "name": "release",
                    "jenkins_url": "https://ci-b.example.com",
                    "jenkins_username": "releaser",
                    "jenkins_password": "secret-b",
                },
            ],
            "jenkins_default_instance_id": "jenkins-b",
        }
    }

    normalized = jenkins_conn.build_jenkins_normalized_from_runnable(config)
    selected = jenkins_conn.build_jenkins_normalized_from_runnable(
        config,
        instance_id="jenkins-a",
    )
    prompt = jenkins_conn.get_jenkins_instances_prompt(
        config["configurable"]
    )

    assert normalized["mode"] == "multi"
    assert selected["items"][0]["name"] == "delivery"
    assert (
        selected["items"][0]["config"]["jenkins_username"] == "builder"
    )
    assert "默认实例为「release」" in prompt


def test_jenkins_connection_probe_uses_selected_credentials():
    instances = []

    class ExternalJenkins:
        def __init__(self, url, username, password):
            self.url = url
            self.username = username
            self.password = password
            instances.append(self)

        def get_jobs(self):
            return [{"name": "deploy"}]

    with patch.object(jenkins_conn.jenkins, "Jenkins", ExternalJenkins):
        result = jenkins_conn.test_jenkins_instance(
            {
                "jenkins_url": "https://ci.example.com",
                "jenkins_username": "builder",
                "jenkins_password": "secret",
            }
        )

    assert result is True
    assert vars(instances[0]) == {
        "url": "https://ci.example.com",
        "username": "builder",
        "password": "secret",
    }
