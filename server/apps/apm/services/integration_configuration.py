import json
import shlex
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from apps.apm.services.contracts import IngestSnippet, IngestSnippetRequest
from apps.apm.services.probe_artifacts import (
    GO_SDK_ARTIFACT_NAME,
    JAVA_AGENT_ARTIFACT_NAME,
    LANGUAGE_PROBE_ARTIFACTS,
    NODEJS_AUTO_ARTIFACT_NAME,
    PYTHON_WHEELS_ARTIFACT_NAME,
    ProbeArtifactNotFound,
    build_probe_artifact_download_url,
)


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
    probe_download_url: str = ""


OTLP_HTTP_PORT = 4318
MAX_INSTANCE_ID_LENGTH = 512

_GO_SDK_GUIDE = """# Go 无通用零代码探针；下面生成完整初始化示例，不会覆盖应用源码。
mkdir -p telemetry
if [ -e telemetry/otel.go.example ]; then
  printf "%s\\n" "telemetry/otel.go.example already exists; refusing to overwrite" >&2
  exit 1
fi
cat > telemetry/otel.go.example <<'GO'
package telemetry

import (
    "context"
    "fmt"

    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
    "go.opentelemetry.io/otel/sdk/resource"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func NewTracerProvider(ctx context.Context) (*sdktrace.TracerProvider, error) {
    exporter, err := otlptracehttp.New(ctx)
    if err != nil {
        return nil, fmt.Errorf("create OTLP trace exporter: %w", err)
    }
    detected, err := resource.New(ctx, resource.WithFromEnv(), resource.WithTelemetrySDK())
    if err != nil {
        return nil, fmt.Errorf("detect OpenTelemetry resource: %w", err)
    }
    return sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exporter),
        sdktrace.WithResource(detected),
    ), nil
}
GO
cat <<'GO'
审阅 telemetry/otel.go.example 后将其改名为 telemetry/otel.go，并在 main 中加入：

tracerProvider, err := telemetry.NewTracerProvider(context.Background())
if err != nil {
    log.Fatal(err)
}
otel.SetTracerProvider(tracerProvider)
defer tracerProvider.Shutdown(context.Background())
GO"""


@dataclass(frozen=True)
class RuntimeProfile:
    """单个运行时的身份来源、启动校验和面向操作者的提示。"""

    identity_setup: tuple[str, ...]
    guidance: str
    docker_environment: tuple[str, ...] = ()


_INSTANCE_ID_VALIDATION = (
    'case "${OTEL_SERVICE_INSTANCE_ID:-}" in',
    '  ""|*[!A-Za-z0-9._:-]*) printf "%s\\n" "APM service.instance.id is empty or invalid" >&2; exit 1 ;;',
    "esac",
    f'if [ "${{#OTEL_SERVICE_INSTANCE_ID}}" -gt {MAX_INSTANCE_ID_LENGTH} ]; then',
    '  printf "%s\\n" "APM service.instance.id exceeds 512 characters" >&2',
    "  exit 1",
    "fi",
    "export OTEL_SERVICE_INSTANCE_ID",
)


_RUNTIME_PROFILES = {
    "host": RuntimeProfile(
        identity_setup=(
            "_bk_apm_valid_uuid() {",
            '  case "$1" in',
            "    ????????-????-4???-[89aAbB]???-????????????)",
            '      case "$1" in *[!0-9A-Fa-f-]*) return 1 ;; *) return 0 ;; esac',
            "      ;;",
            "  esac",
            "  return 1",
            "}",
            "OTEL_SERVICE_INSTANCE_ID=${APM_INSTANCE_ID:-}",
            'if [ -z "$OTEL_SERVICE_INSTANCE_ID" ]; then',
            "  _bk_apm_generated_id=",
            "  if command -v cat >/dev/null 2>&1; then",
            "    _bk_apm_generated_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null) || _bk_apm_generated_id=",
            "  fi",
            '  if ! _bk_apm_valid_uuid "$_bk_apm_generated_id"; then',
            "    _bk_apm_generated_id=",
            "  fi",
            '  if [ -z "$_bk_apm_generated_id" ] && command -v uuidgen >/dev/null 2>&1; then',
            "    _bk_apm_generated_id=$(uuidgen 2>/dev/null) || _bk_apm_generated_id=",
            '    if ! _bk_apm_valid_uuid "$_bk_apm_generated_id"; then',
            "      _bk_apm_generated_id=",
            "    fi",
            "  fi",
            "  OTEL_SERVICE_INSTANCE_ID=$_bk_apm_generated_id",
            "fi",
            *_INSTANCE_ID_VALIDATION,
        ),
        guidance="实例 ID 在应用进程启动时生成；每个副本必须唯一。显式设置 APM_INSTANCE_ID 时，请为每个并发副本使用不同值。",
    ),
    "docker": RuntimeProfile(
        identity_setup=(
            "OTEL_SERVICE_INSTANCE_ID=${APM_INSTANCE_ID:-${HOSTNAME:-}}",
            *_INSTANCE_ID_VALIDATION,
        ),
        guidance="实例 ID 默认使用容器身份；每个副本必须唯一。显式设置 APM_INSTANCE_ID 时，请为每个并发副本使用不同值。",
        docker_environment=("APM_INSTANCE_ID",),
    ),
    "kubernetes": RuntimeProfile(
        identity_setup=(
            "OTEL_SERVICE_INSTANCE_ID=${APM_INSTANCE_ID:-${POD_UID:-}}",
            *_INSTANCE_ID_VALIDATION,
        ),
        guidance="实例 ID 默认使用 Pod UID；每个副本必须唯一。显式设置 APM_INSTANCE_ID 时，请为每个并发副本使用不同值。",
    ),
    "other": RuntimeProfile(
        identity_setup=(
            "OTEL_SERVICE_INSTANCE_ID=${APM_INSTANCE_ID:-}",
            *_INSTANCE_ID_VALIDATION,
        ),
        guidance="此运行方式需要设置 APM_INSTANCE_ID；每个并发副本必须使用不同值。",
    ),
}


def _otel_resource_value(value: str) -> str:
    """按 OTEL_RESOURCE_ATTRIBUTES 语法编码值；Shell literal 由调用方另行处理。"""

    return quote(value, safe="-._~")


def _kubernetes_snippet(language: str, environment: dict[str, str], probe_download_url: str) -> str:
    """生成可作为 strategic merge patch 使用的容器环境片段。"""

    image_guidance = {
        "python": f"应用镜像需预装 opentelemetry-distro[otlp] 并使用 opentelemetry-instrument 启动。离线包：{probe_download_url}",
        "nodejs": f"应用镜像需预装 @opentelemetry/auto-instrumentations-node。离线包：{probe_download_url}",
        "java": f"应用镜像需包含 /opt/opentelemetry-javaagent.jar。离线包：{probe_download_url}",
        "go": f"Go 无通用自动探针；应用二进制需先完成 OpenTelemetry Go SDK 初始化。离线包：{probe_download_url}",
    }
    runtime_environment = {
        "nodejs": {"NODE_OPTIONS": "--require @opentelemetry/auto-instrumentations-node/register"},
        "java": {"JAVA_TOOL_OPTIONS": "-javaagent:/opt/opentelemetry-javaagent.jar"},
    }.get(language, {})
    kubernetes_environment = {
        **environment,
        **runtime_environment,
    }
    kubernetes_environment["OTEL_RESOURCE_ATTRIBUTES"] = kubernetes_environment["OTEL_RESOURCE_ATTRIBUTES"].replace(
        "${OTEL_SERVICE_INSTANCE_ID}",
        "$(OTEL_SERVICE_INSTANCE_ID)",
    )
    lines = [
        f"# {image_guidance.get(language, '应用镜像需预装所选 OpenTelemetry SDK。')}",
        "# 把 YOUR_CONTAINER_NAME 替换为应用容器名，保存后执行：",
        "# kubectl patch deployment YOUR_DEPLOYMENT_NAME --type strategic --patch-file apm-env.yaml",
        "spec:",
        "  template:",
        "    spec:",
        "      containers:",
        "        - name: YOUR_CONTAINER_NAME",
        "          env:",
        "            - name: POD_UID",
        "              valueFrom:",
        "                fieldRef:",
        "                  apiVersion: v1",
        "                  fieldPath: metadata.uid",
        "            - name: OTEL_SERVICE_INSTANCE_ID",
        '              value: "$(POD_UID)"',
    ]
    for key, value in kubernetes_environment.items():
        lines.extend(
            (
                f"            - name: {key}",
                f"              value: {json.dumps(value, ensure_ascii=False)}",
            )
        )
    return "\n".join(lines)


def _curl_download(url: str, output: str) -> str:
    return " \\\n  ".join(
        (
            "curl --fail --silent --show-error --location",
            shlex.quote(url),
            f"--output {output}",
        )
    )


def _python_offline_install(wheels_dir: str) -> tuple[str, str, str]:
    return (
        f'python -m pip install --no-index --find-links {wheels_dir} "opentelemetry-distro[otlp]"',
        "opentelemetry-bootstrap -a requirements > otel-bootstrap-requirements.txt",
        f"python -m pip install --no-index --find-links {wheels_dir} -r otel-bootstrap-requirements.txt",
    )


def _host_install_commands(language: str, probe_download_url: str) -> str:
    if language == "python":
        pip_install, bootstrap_requirements, bootstrap_install = _python_offline_install("otel-python-wheels")
        return "\n".join(
            (
                _curl_download(probe_download_url, PYTHON_WHEELS_ARTIFACT_NAME),
                "mkdir -p otel-python-wheels",
                f"tar -xf {PYTHON_WHEELS_ARTIFACT_NAME} -C otel-python-wheels",
                pip_install,
                bootstrap_requirements,
                bootstrap_install,
            )
        )
    if language == "nodejs":
        return "\n".join(
            (
                _curl_download(probe_download_url, NODEJS_AUTO_ARTIFACT_NAME),
                f"npm install --offline --save ./{NODEJS_AUTO_ARTIFACT_NAME}",
            )
        )
    if language == "java":
        return _curl_download(probe_download_url, JAVA_AGENT_ARTIFACT_NAME)
    if language == "go":
        return "\n".join(
            (
                _curl_download(probe_download_url, GO_SDK_ARTIFACT_NAME),
                "mkdir -p .otel-go-sdk",
                f"unzip -o -q {GO_SDK_ARTIFACT_NAME} -d .otel-go-sdk",
                'export GOPROXY="file://$(pwd)/.otel-go-sdk"',
                "export GOSUMDB=off",
                "go mod download go.opentelemetry.io/otel go.opentelemetry.io/otel/sdk go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
            )
        )
    return "# Install the selected OpenTelemetry SDK."


def _docker_install_commands(language: str, probe_download_url: str) -> str:
    quoted_url = shlex.quote(probe_download_url)
    if language == "python":
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location {quoted_url} --output /tmp/{PYTHON_WHEELS_ARTIFACT_NAME}",
                "mkdir -p /opt/otel-python-wheels",
                f"tar -xf /tmp/{PYTHON_WHEELS_ARTIFACT_NAME} -C /opt/otel-python-wheels",
                'python -m pip install --no-index --find-links /opt/otel-python-wheels "opentelemetry-distro[otlp]"',
                "opentelemetry-bootstrap -a requirements > /tmp/otel-bootstrap-requirements.txt",
                "python -m pip install --no-index --find-links /opt/otel-python-wheels -r /tmp/otel-bootstrap-requirements.txt",
            )
        )
    if language == "nodejs":
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location {quoted_url} --output /tmp/{NODEJS_AUTO_ARTIFACT_NAME}",
                f"npm install --offline --save /tmp/{NODEJS_AUTO_ARTIFACT_NAME}",
            )
        )
    if language == "java":
        return " \\\n  ".join(
            (
                "RUN curl --fail --silent --show-error --location",
                quoted_url,
                f"--output /opt/{JAVA_AGENT_ARTIFACT_NAME}",
            )
        )
    if language == "go":
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location {quoted_url} --output /tmp/{GO_SDK_ARTIFACT_NAME}",
                "mkdir -p /opt/otel-go-sdk",
                f"unzip -o -q /tmp/{GO_SDK_ARTIFACT_NAME} -d /opt/otel-go-sdk",
                "GOPROXY=file:///opt/otel-go-sdk GOSUMDB=off go mod download go.opentelemetry.io/otel go.opentelemetry.io/otel/sdk go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
            )
        )
    return "# Install the selected OpenTelemetry SDK in the image."


def _normalize_proxy_address(value: object) -> str:
    raw = str(value or "").strip()
    if not raw or "://" in raw or any(character in raw for character in ("\r", "\n", "\0")):
        raise ValueError("empty or contains control characters")
    try:
        parsed = urlsplit(f"http://{raw}")
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid proxy address") from exc
    if parsed.username or parsed.password or parsed.port is not None or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("proxy address must only contain a host")
    try:
        URLValidator(schemes=("http",))(f"http://{raw}")
    except ValidationError as exc:
        raise ValueError("invalid proxy address") from exc
    return raw.lower()


def _receiver_host_from_node_server_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid NODE_SERVER_URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("NODE_SERVER_URL must contain a trusted HTTP host")
    return f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname


def _download_base_from_node_server_url(value: object) -> str:
    """从 NODE_SERVER_URL 提取 scheme://host[:port]，作为系统内下载地址前缀。"""
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid NODE_SERVER_URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("NODE_SERVER_URL must contain a trusted HTTP host")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    base = f"{parsed.scheme}://{host}"
    if port is not None:
        base = f"{base}:{port}"
    return base


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

    def resolve_region(
        self,
        node_mgmt,
        cloud_region_id: int,
        *,
        organization_ids: list[int],
        include_probe_download: bool = False,
        probe_artifact_name: str = "",
    ) -> CloudRegionEndpoints:
        if not organization_ids:
            raise CloudRegionConfigurationError(
                "cloud_region_receiver_unavailable",
                "当前组织无法使用所选云区域的被动接收地址。",
            )
        regions = self.list_regions(node_mgmt)
        region = next((item for item in regions if item["id"] == cloud_region_id), None)
        if region is None:
            raise CloudRegionConfigurationError("cloud_region_not_found", "云区域不存在或已不可用。")

        env_config_cache: dict[str, dict] = {}

        def _node_server_url() -> object:
            if "value" not in env_config_cache:
                env_config = node_mgmt.get_cloud_region_public_config(cloud_region_id)
                env_config_cache["value"] = env_config if isinstance(env_config, dict) else {}
            return env_config_cache["value"].get("NODE_SERVER_URL")

        # APM SDK/Agent 不要求先成为节点管理中的节点；这里不能用 NodeOrganization
        # 过滤，否则新接入区域会形成“先有关联节点，才能获取接入地址”的循环依赖。
        proxy_address = node_mgmt.get_cloud_region_proxy_address(cloud_region_id)
        if not str(proxy_address or "").strip():
            node_server_url = _node_server_url()
            if not str(node_server_url or "").strip():
                raise CloudRegionConfigurationError(
                    "cloud_region_receiver_unavailable",
                    "所选云区域没有可用的被动接收地址。",
                )
            try:
                proxy_address = _receiver_host_from_node_server_url(node_server_url)
            except ValueError as exc:
                raise CloudRegionConfigurationError(
                    "invalid_cloud_region_proxy_address",
                    "云区域接收地址格式无效，请联系管理员检查配置。",
                ) from exc
        try:
            proxy_address = _normalize_proxy_address(proxy_address)
        except ValueError as exc:
            raise CloudRegionConfigurationError(
                "invalid_cloud_region_proxy_address",
                "云区域接收地址格式无效，请联系管理员检查配置。",
            ) from exc

        probe_download_url = ""
        if include_probe_download:
            node_server_url = _node_server_url()
            if not str(node_server_url or "").strip():
                raise CloudRegionConfigurationError(
                    "probe_download_unavailable",
                    "所选云区域缺少 NODE_SERVER_URL，无法生成探针下载地址，请联系管理员配置。",
                )
            try:
                download_base = _download_base_from_node_server_url(node_server_url)
                probe_download_url = build_probe_artifact_download_url(download_base, probe_artifact_name)
            except (ValueError, ProbeArtifactNotFound) as exc:
                raise CloudRegionConfigurationError(
                    "probe_download_unavailable",
                    "云区域 NODE_SERVER_URL 格式无效，无法生成探针下载地址，请联系管理员检查配置。",
                ) from exc

        return CloudRegionEndpoints(
            region_id=region["id"],
            region_name=region["name"],
            http_endpoint=f"http://{proxy_address}:{OTLP_HTTP_PORT}",
            probe_download_url=probe_download_url,
        )

    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet:
        runtime_profile = _RUNTIME_PROFILES[request.runtime]
        protocol = "http/protobuf"
        if request.language in LANGUAGE_PROBE_ARTIFACTS and not request.probe_download_url:
            raise ValueError("snippets require a resolved probe_download_url")

        static_resource = ",".join(
            (
                f"service.namespace={_otel_resource_value(request.service_namespace)}",
                f"service.name={_otel_resource_value(request.service_name)}",
                f"service.version={_otel_resource_value(request.service_version)}",
                f"deployment.environment={_otel_resource_value(request.environment)}",
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
        install_commands = {
            language: _host_install_commands(language, request.probe_download_url)
            for language in LANGUAGE_PROBE_ARTIFACTS
        }
        start_commands = {
            "python": "opentelemetry-instrument python app.py",
            "nodejs": "node --require @opentelemetry/auto-instrumentations-node/register app.js",
            "java": "java -javaagent:./opentelemetry-javaagent.jar -jar app.jar",
            "go": _GO_SDK_GUIDE,
        }

        if request.runtime == "kubernetes":
            code = _kubernetes_snippet(request.language, environment, request.probe_download_url)
        elif request.runtime == "docker":
            image_install_commands = {
                language: _docker_install_commands(language, request.probe_download_url)
                for language in LANGUAGE_PROBE_ARTIFACTS
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
            docker_environment.extend(f"  -e {key} \\\n" for key in runtime_profile.docker_environment)
            docker_environment_text = "".join(docker_environment).rstrip(" \\\n")
            start_command = docker_start_commands.get(request.language, "./app")
            docker_start_script = "\n".join(
                (
                    *runtime_profile.identity_setup,
                    f"export OTEL_RESOURCE_ATTRIBUTES={resource_assignment}; exec {start_command}",
                )
            )
            code = "\n".join(
                (
                    "# 1. 安装探针（将以下命令写入应用 Dockerfile）",
                    image_install_commands.get(request.language, "# Install the selected OpenTelemetry SDK in the image."),
                    "",
                    "# 2. 配置上报（端点与资源属性通过容器环境注入）",
                    f"# {runtime_profile.guidance}",
                    "docker run \\",
                    docker_environment_text + " \\",
                    "  your-image:latest sh -c \\",
                    "  " + shlex.quote(docker_start_script),
                    "",
                    "# 3. 启动应用（上面的 docker run 已使用自动探针启动应用）",
                )
            )
        else:
            export_lines = [f"# {runtime_profile.guidance}", *runtime_profile.identity_setup]
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
