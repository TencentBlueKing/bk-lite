import shlex
from apps.apm.services.contracts import IngestSnippet, IngestSnippetRequest


class DjangoIntegrationConfigurationService:
    """无状态生成 SDK/探针配置；不创建接入源，也不持久化表单内容。"""

    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet:
        instance_expression = {
            "kubernetes": "${POD_UID:?POD_UID is required}",
            "docker": "${HOSTNAME:?container instance id is required}",
            "host": "${BK_INSTANCE_ID:?stable platform instance id is required}",
        }.get(request.runtime, "${APM_INSTANCE_ID:-$(uuidgen)}")
        protocol = "http/protobuf"

        def shell_literal(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")

        resource = ",".join(
            (
                f"service.namespace={shell_literal(request.service_namespace)}",
                f"service.name={shell_literal(request.service_name)}",
                f"service.version={shell_literal(request.service_version)}",
                "service.instance.id=${OTEL_SERVICE_INSTANCE_ID}",
                f"deployment.environment={shell_literal(request.environment)}",
            )
        )
        environment = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": request.endpoint.rstrip("/"),
            "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
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
                    "# 2. 配置上报（端点与资源属性通过容器环境注入）",
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
                    "# 2. 配置上报（端点与资源属性使用标准 OTEL_* 环境变量）",
                    *export_lines,
                    "",
                    "# 3. 启动应用",
                    start_commands.get(request.language, "# Start the instrumented application."),
                )
            )
        return IngestSnippet(environment=environment, code=code)
