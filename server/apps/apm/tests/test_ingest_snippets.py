import pytest

from apps.apm.services import DjangoIngestSourceService
from apps.apm.services.contracts import IngestSnippetRequest


@pytest.mark.parametrize(
    ("runtime", "expected_identity"),
    [
        ("kubernetes", "${POD_UID:?POD_UID is required}"),
        ("docker", "${HOSTNAME:?container instance id is required}"),
        ("host", "${BK_INSTANCE_ID:?stable platform instance id is required}"),
        ("other", "${APM_INSTANCE_ID:-$(uuidgen)}"),
    ],
)
def test_snippet_uses_a_runtime_instance_identity_instead_of_a_shared_constant(runtime, expected_identity):
    snippet = DjangoIngestSourceService().render_snippet(
        IngestSnippetRequest(
            language="python",
            runtime=runtime,
            endpoint="https://apm.example.com/",
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            credential="bkapm_secret",
        )
    )

    assert expected_identity in snippet.code
    assert "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}" in snippet.code
    assert snippet.environment["OTEL_EXPORTER_OTLP_HEADERS"] == "Authorization=Bearer bkapm_secret"
    assert snippet.environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://apm.example.com"


def test_grpc_snippet_uses_grpc_protocol_and_language_specific_launch_command():
    snippet = DjangoIngestSourceService().render_snippet(
        IngestSnippetRequest(
            language="java",
            runtime="kubernetes",
            endpoint="https://apm.example.com",
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            credential="bkapm_secret",
            ingest_type="otlp_grpc",
        )
    )

    assert snippet.environment["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"
    assert "opentelemetry-javaagent.jar" in snippet.code
