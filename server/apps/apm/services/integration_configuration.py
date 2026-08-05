import shlex
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from apps.apm.services.contracts import IngestSnippet, IngestSnippetRequest


class CloudRegionConfigurationError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CloudRegionEndpoints:
    region_id: int
    region_name: str
    http_endpoint: str
    grpc_endpoint: str


def _normalize_otlp_endpoint(value: object, *, protocol: str) -> str:
    raw = str(value or "").strip()
    if not raw or any(character in raw for character in ("\r", "\n", "\0")):
        raise ValueError("empty or contains control characters")
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("scheme and host are required")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("userinfo, query and fragment are not allowed")
    path = parsed.path.rstrip("/")
    if protocol == "grpc" and path:
        raise ValueError("gRPC endpoint must not contain a path")
    if protocol == "http" and path.endswith("/v1/traces"):
        path = path.removesuffix("/v1/traces")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class DjangoIntegrationConfigurationService:
    """无状态生成 SDK/探针配置；不创建接入源，也不持久化表单内容。"""

    @staticmethod
    def list_regions(node_mgmt) -> list[dict]:
        regions = node_mgmt.cloud_region_list()
        normalized = []
        for region in regions or []:
            try:
                region_id = int(region["id"])
                region_name = str(region["name"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise CloudRegionConfigurationError(
                    "invalid_cloud_region",
                    "云区域目录返回了无效数据，请联系运维检查 NodeMgmt。",
                ) from exc
            if region_id < 1 or not region_name:
                raise CloudRegionConfigurationError(
                    "invalid_cloud_region",
                    "云区域目录返回了无效数据，请联系运维检查 NodeMgmt。",
                )
            normalized.append({"id": region_id, "name": region_name})
        return normalized

    def resolve_region(self, node_mgmt, cloud_region_id: int) -> CloudRegionEndpoints:
        regions = self.list_regions(node_mgmt)
        region = next((item for item in regions if item["id"] == cloud_region_id), None)
        if region is None:
            raise CloudRegionConfigurationError("cloud_region_not_found", "云区域不存在或已不可用。")
        env = node_mgmt.get_cloud_region_envconfig(cloud_region_id) or {}
        required = ("APM_OTLP_HTTP_ENDPOINT", "APM_OTLP_GRPC_ENDPOINT")
        missing = [key for key in required if not str(env.get(key, "")).strip()]
        if missing:
            raise CloudRegionConfigurationError(
                "cloud_region_endpoint_missing",
                f"云区域缺少 APM 接入端点配置：{', '.join(missing)}。",
            )
        try:
            http_endpoint = _normalize_otlp_endpoint(env["APM_OTLP_HTTP_ENDPOINT"], protocol="http")
            grpc_endpoint = _normalize_otlp_endpoint(env["APM_OTLP_GRPC_ENDPOINT"], protocol="grpc")
        except ValueError as exc:
            raise CloudRegionConfigurationError(
                "invalid_cloud_region_endpoint",
                "云区域 APM 接入端点格式无效，请联系运维检查配置。",
            ) from exc
        return CloudRegionEndpoints(
            region_id=region["id"],
            region_name=region["name"],
            http_endpoint=http_endpoint,
            grpc_endpoint=grpc_endpoint,
        )

    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet:
        instance_expression = {
            "kubernetes": "${POD_UID:?POD_UID is required}",
            "docker": "${HOSTNAME:?container instance id is required}",
            "host": "${BK_INSTANCE_ID:?stable platform instance id is required}",
        }.get(request.runtime, "${APM_INSTANCE_ID:-$(uuidgen)}")
        protocol = "http/protobuf"

        static_resource = ",".join(
            (
                f"service.namespace={request.service_namespace}",
                f"service.name={request.service_name}",
                f"service.version={request.service_version}",
                f"deployment.environment={request.environment}",
            )
        )
        resource = f"{static_resource},service.instance.id=${{OTEL_SERVICE_INSTANCE_ID}}"
        resource_assignment = shlex.quote(f"{static_resource},service.instance.id=") + '"${OTEL_SERVICE_INSTANCE_ID}"'
        environment = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": request.endpoint.rstrip("/"),
            "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
            "OTEL_PROPAGATORS": "tracecontext,baggage",
            "OTEL_RESOURCE_ATTRIBUTES": resource,
        }
        shell_continuation = " \\" + "\n  "
        install_commands = {
            "python": "\n".join(
                (
                    'python -m pip install "opentelemetry-distro[otlp]"',
                    "opentelemetry-bootstrap -a install",
                )
            ),
            "nodejs": "npm install --save @opentelemetry/auto-instrumentations-node",
            "java": shell_continuation.join(
                (
                    "curl --fail --silent --show-error --location",
                    "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar",
                    "--output opentelemetry-javaagent.jar",
                )
            ),
            "go": shell_continuation.join(
                (
                    "go get go.opentelemetry.io/otel",
                    "go.opentelemetry.io/otel/sdk",
                    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
                )
            ),
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
                "java": shell_continuation.join(
                    (
                        "RUN curl --fail --silent --show-error --location",
                        "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar",
                        "--output /opt/opentelemetry-javaagent.jar",
                    )
                ),
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
                    "# 2. 配置上报（端点与资源属性通过容器环境注入）",
                    "docker run \\",
                    docker_environment_text + " \\",
                    "  your-image:latest sh -c \\",
                    "  "
                    + shlex.quote(
                        'export OTEL_SERVICE_INSTANCE_ID="${HOSTNAME:?container instance id is required}"; '
                        f"export OTEL_RESOURCE_ATTRIBUTES={resource_assignment}; exec {start_command}"
                    ),
                    "",
                    "# 3. 启动应用（上面的 docker run 已使用自动探针启动应用）",
                )
            )
        else:
            export_lines = [f'export OTEL_SERVICE_INSTANCE_ID="{instance_expression}"']
            for key, value in environment.items():
                if key == "OTEL_RESOURCE_ATTRIBUTES":
                    export_lines.append(f"export {key}={resource_assignment}")
                else:
                    export_lines.append(f"export {key}={shlex.quote(value)}")
            code = "\n".join(
                (
                    "# 1. 安装探针",
                    install_commands.get(request.language, "# Install the selected OpenTelemetry SDK."),
                    "",
                    "# 2. 配置上报（端点与资源属性使用标准 OTEL_* 环境变量）",
                    *export_lines,
                    "",
                    "# 3. 启动应用",
                    start_commands.get(request.language, "# Start the instrumented application."),
                )
            )
        return IngestSnippet(environment=environment, code=code)
