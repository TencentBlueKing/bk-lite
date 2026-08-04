import secrets
import shlex
from collections.abc import Sequence
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction

from apps.apm.models import (
    ApmIngestSource,
    ApmIngestSourceOrganization,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
)
from apps.apm.services.contracts import CreatedIngestSource, IngestSnippet, IngestSnippetRequest


def _normalized_organization_ids(organization_ids: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(item) for item in organization_ids}))
    if not result:
        raise ValueError("接入源至少需要一个组织")
    return result


def _new_credential() -> tuple[str, str, str]:
    credential = f"bkapm_{secrets.token_urlsafe(32)}"
    return credential, credential[:16], make_password(credential)


class DjangoIngestSourceService:
    """接入源深模块的 Django ORM 实现。"""

    @transaction.atomic
    def create(
        self,
        *,
        name: str,
        ingest_type: str,
        organization_ids: Sequence[int],
        actor: str,
        cloud_region_id: int | None = None,
        environment_hint: str = "",
    ) -> CreatedIngestSource:
        organizations = _normalized_organization_ids(organization_ids)
        credential, prefix, digest = _new_credential()
        source = ApmIngestSource.objects.create(
            name=name.strip(),
            ingest_type=ingest_type,
            cloud_region_id=cloud_region_id,
            environment_hint=environment_hint.strip(),
            credential_prefix=prefix,
            credential_digest=digest,
            created_by=actor,
            updated_by=actor,
        )
        ApmIngestSourceOrganization.objects.bulk_create(
            [
                ApmIngestSourceOrganization(
                    ingest_source=source,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for organization in organizations
            ]
        )
        return CreatedIngestSource(source=source, credential=credential)

    @transaction.atomic
    def rotate(self, source_id: UUID, *, actor: str) -> CreatedIngestSource:
        source = ApmIngestSource.objects.select_for_update().get(id=source_id)
        credential, prefix, digest = _new_credential()
        source.credential_prefix = prefix
        source.credential_digest = digest
        source.is_enabled = True
        source.updated_by = actor
        source.save(
            update_fields=(
                "credential_prefix",
                "credential_digest",
                "is_enabled",
                "updated_by",
                "updated_at",
            )
        )
        return CreatedIngestSource(source=source, credential=credential)

    @transaction.atomic
    def disable(self, source_id: UUID, *, actor: str) -> ApmIngestSource:
        source = ApmIngestSource.objects.select_for_update().get(id=source_id)
        source.is_enabled = False
        source.updated_by = actor
        source.save(update_fields=("is_enabled", "updated_by", "updated_at"))
        return source

    @transaction.atomic
    def set_organizations(
        self,
        source_id: UUID,
        organization_ids: Sequence[int],
        *,
        actor: str,
    ) -> ApmIngestSource:
        organizations = _normalized_organization_ids(organization_ids)
        source = ApmIngestSource.objects.select_for_update().get(id=source_id)
        ApmIngestSourceOrganization.objects.filter(ingest_source=source).delete()
        ApmIngestSourceOrganization.objects.bulk_create(
            [
                ApmIngestSourceOrganization(
                    ingest_source=source,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for organization in organizations
            ]
        )

        inherited_instances = ApmServiceInstance.objects.filter(
            ingest_source=source,
            permission_mode=ApmServiceInstance.PermissionMode.INHERITED,
        )
        ApmServiceInstanceOrganization.objects.filter(instance__in=inherited_instances).delete()
        ApmServiceInstanceOrganization.objects.bulk_create(
            [
                ApmServiceInstanceOrganization(
                    instance=instance,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for instance in inherited_instances
                for organization in organizations
            ],
            ignore_conflicts=True,
        )
        source.updated_by = actor
        source.save(update_fields=("updated_by", "updated_at"))
        return source

    def validate_credential(self, credential: str) -> ApmIngestSource | None:
        if not credential:
            return None
        prefix = credential[:16]
        candidates = ApmIngestSource.objects.filter(
            credential_prefix=prefix,
            is_enabled=True,
        )
        return next(
            (source for source in candidates if check_password(credential, source.credential_digest)),
            None,
        )

    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet:
        if not request.credential:
            raise ValueError("生成接入片段需要一次性明文凭证")
        instance_expression = {
            "kubernetes": "${POD_UID:?POD_UID is required}",
            "docker": "${HOSTNAME:?container instance id is required}",
            "host": "${BK_INSTANCE_ID:?stable platform instance id is required}",
        }.get(request.runtime, "${APM_INSTANCE_ID:-$(uuidgen)}")
        protocol = "grpc" if request.ingest_type == ApmIngestSource.IngestType.OTLP_GRPC else "http/protobuf"

        def shell_literal(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")

        resource = ",".join(
            (
                f"service.namespace={shell_literal(request.service_namespace)}",
                f"service.name={shell_literal(request.service_name)}",
                "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}",
                f"deployment.environment={shell_literal(request.environment)}",
            )
        )
        environment = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": request.endpoint.rstrip("/"),
            "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
            "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Bearer {request.credential}",
            "OTEL_PROPAGATORS": "tracecontext,baggage",
            "OTEL_RESOURCE_ATTRIBUTES": resource,
        }
        shell_continuation = " \\" + "\n  "
        install_commands = {
            "python": '\n'.join((
                'python -m pip install "opentelemetry-distro[otlp]"',
                "opentelemetry-bootstrap -a install",
            )),
            "nodejs": "npm install --save @opentelemetry/auto-instrumentations-node",
            "java": shell_continuation.join((
                "curl --fail --silent --show-error --location",
                "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar",
                "--output opentelemetry-javaagent.jar",
            )),
            "go": shell_continuation.join((
                "go get go.opentelemetry.io/otel",
                "go.opentelemetry.io/otel/sdk",
                "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
            )),
        }
        start_commands = {
            "python": "opentelemetry-instrument python app.py",
            "nodejs": "node --require @opentelemetry/auto-instrumentations-node/register app.js",
            "java": "java -javaagent:./opentelemetry-javaagent.jar -jar app.jar",
            "go": "# Initialize the OpenTelemetry Go SDK in your application, then start it normally.\ngo run .",
        }

        if request.runtime == "docker":
            image_install_commands = {
                "python": 'RUN python -m pip install "opentelemetry-distro[otlp]" && opentelemetry-bootstrap -a install',
                "nodejs": "RUN npm install --save @opentelemetry/auto-instrumentations-node",
                "java": shell_continuation.join((
                    "RUN curl --fail --silent --show-error --location",
                    "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar",
                    "--output /opt/opentelemetry-javaagent.jar",
                )),
                "go": "# Go SDK must be added during the application build; keep the final image command unchanged.",
            }
            docker_start_commands = {
                "python": "opentelemetry-instrument python app.py",
                "nodejs": "node app.js",
                "java": "java -jar app.jar",
                "go": "./app",
            }
            runtime_environment = {
                "nodejs": {"NODE_OPTIONS": "--require @opentelemetry/auto-instrumentations-node/register"},
                "java": {"JAVA_TOOL_OPTIONS": "-javaagent:/opt/opentelemetry-javaagent.jar"},
            }.get(request.language, {})
            docker_environment = [
                f"  -e {key}={shlex.quote(value)} \\" + "\n"
                for key, value in {**environment, **runtime_environment}.items()
                if key != "OTEL_RESOURCE_ATTRIBUTES"
            ]
            docker_environment_text = "".join(docker_environment).rstrip(" \\\n")
            start_command = docker_start_commands.get(request.language, "./app")
            code = "\n".join(
                (
                    "# 1. 安装探针（将以下命令写入应用 Dockerfile）",
                    image_install_commands.get(request.language, "# Install the selected OpenTelemetry SDK in the image."),
                    "",
                    "# 2. 配置上报（端点、Token 与资源属性通过容器环境注入）",
                    "docker run \\",
                    docker_environment_text + " \\",
                    "  your-image:latest sh -c \\",
                    "  'export OTEL_SERVICE_INSTANCE_ID=\"${HOSTNAME:?container instance id is required}\"; "
                    f"export OTEL_RESOURCE_ATTRIBUTES=\"{resource}\"; exec {start_command}'",
                    "",
                    "# 3. 启动应用（上面的 docker run 已使用自动探针启动应用）",
                )
            )
        else:
            export_lines = [f'export OTEL_SERVICE_INSTANCE_ID="{instance_expression}"']
            for key, value in environment.items():
                if key == "OTEL_RESOURCE_ATTRIBUTES":
                    export_lines.append(f'export {key}="{value}"')
                else:
                    export_lines.append(f"export {key}={shlex.quote(value)}")
            code = "\n".join(
                (
                    "# 1. 安装探针",
                    install_commands.get(request.language, "# Install the selected OpenTelemetry SDK."),
                    "",
                    "# 2. 配置上报（端点、Token 与资源属性使用标准 OTEL_* 环境变量）",
                    *export_lines,
                    "",
                    "# 3. 启动应用",
                    start_commands.get(request.language, "# Start the instrumented application."),
                )
            )
        return IngestSnippet(environment=environment, code=code)
