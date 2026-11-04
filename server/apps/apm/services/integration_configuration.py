import json
import shlex
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote, urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from apps.apm.services.contracts import IngestSnippet, IngestSnippetRequest
from apps.apm.services.probe_artifacts import (
    CPP_SDK_ARTIFACT_NAME,
    DOTNET_AUTO_ARTIFACT_NAME,
    DOTNET_WINDOWS_ARTIFACT_NAME,
    ERLANG_SDK_ARTIFACT_NAME,
    GO_SDK_ARTIFACT_NAME,
    JAVA_AGENT_ARTIFACT_NAME,
    LANGUAGE_PROBE_ARTIFACTS,
    NODEJS_AUTO_ARTIFACT_NAME,
    OBI_ARTIFACT_NAME,
    PHP_AUTO_ARTIFACT_NAME,
    PYTHON_WHEELS_ARTIFACT_NAME,
    RUBY_SDK_ARTIFACT_NAME,
    SWIFT_SDK_ARTIFACT_NAME,
    ProbeArtifactNotFound,
    build_probe_artifact_download_url,
    get_probe_artifact_sha256,
    validate_probe_selection,
)
from apps.apm.utils.locale_text import apm_text


class CloudRegionConfigurationError(ValueError):
    def __init__(self, code: str, detail: str, *, message_key: str | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.message_key = message_key
        self.message_values = {}


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

_RUBY_SDK_GUIDE = """# Ruby 无通用零代码探针；下面生成 Rack 初始化示例，不会覆盖应用源码。
# opentelemetry-sdk 1.13.1
# opentelemetry-exporter-otlp 0.37.0
# opentelemetry-instrumentation-rack 0.31.2
mkdir -p telemetry
if [ -e telemetry/otel.rb.example ]; then
  printf "%s\\n" "telemetry/otel.rb.example already exists; refusing to overwrite" >&2
  exit 1
fi
cat > telemetry/otel.rb.example <<'RUBY'
require "opentelemetry/sdk"
require "opentelemetry/exporter/otlp"
require "opentelemetry/instrumentation/rack"

OpenTelemetry::SDK.configure do |c|
  c.use "OpenTelemetry::Instrumentation::Rack"
end
RUBY
cat <<'RUBY'
审阅 telemetry/otel.rb.example 后将其加入应用启动，并在 config.ru 中加入：

use *OpenTelemetry::Instrumentation::Rack::Instrumentation.instance.middleware_args
RUBY"""

_CPP_SDK_GUIDE = """# C++ 无通用零代码探针；下面生成最小入口 Span 示例，不会覆盖应用源码。
# opentelemetry-cpp v1.30.0
mkdir -p telemetry
if [ -e telemetry/otel.cpp.example ]; then
  printf "%s\\n" "telemetry/otel.cpp.example already exists; refusing to overwrite" >&2
  exit 1
fi
cat > telemetry/otel.cpp.example <<'CPP'
#include <cstdlib>
#include <memory>
#include <string>

#include "opentelemetry/exporters/otlp/otlp_http_exporter_factory.h"
#include "opentelemetry/sdk/trace/simple_processor_factory.h"
#include "opentelemetry/sdk/trace/tracer_provider_factory.h"
#include "opentelemetry/trace/provider.h"

int main() {
    opentelemetry::exporter::otlp::OtlpHttpExporterOptions options;
    if (const char* endpoint = std::getenv("OTEL_EXPORTER_OTLP_ENDPOINT")) {
        options.url = std::string(endpoint) + "/v1/traces";
    }
    auto exporter = opentelemetry::exporter::otlp::OtlpHttpExporterFactory::Create(options);
    auto processor = opentelemetry::sdk::trace::SimpleSpanProcessorFactory::Create(std::move(exporter));
    std::shared_ptr<opentelemetry::trace::TracerProvider> provider =
        opentelemetry::sdk::trace::TracerProviderFactory::Create(std::move(processor));
    opentelemetry::trace::Provider::SetTracerProvider(provider);
    auto tracer = provider->GetTracer("app");
    opentelemetry::trace::StartSpanOptions span_options;
    span_options.kind = opentelemetry::trace::SpanKind::kServer;
    auto span = tracer->StartSpan("GET /", {}, span_options);
    span->End();
    return 0;
}
CPP
cat <<'CPP'
审阅 telemetry/otel.cpp.example 后，对着 .otel-cpp-sdk/prefix 编译并启动进程。
CPP"""

_ERLANG_SDK_GUIDE = """# Erlang/Elixir 无通用零代码探针；下面生成示例，不会覆盖应用源码。
# opentelemetry 1.7.0
# opentelemetry_exporter 1.11.0
mkdir -p telemetry
if [ -e telemetry/rebar.config.example ] || [ -e telemetry/mix.exs.example ] \
  || [ -e telemetry/otel.erl.example ] || [ -e telemetry/otel.ex.example ]; then
  printf "%s\\n" "telemetry example already exists; refusing to overwrite" >&2
  exit 1
fi
cat > telemetry/rebar.config.example <<'ERL'
{deps, [
  opentelemetry_api,
  opentelemetry,
  opentelemetry_exporter,
  grpcbox,
  chatterbox,
  hpack,
  ctx,
  acceptor_pool,
  gproc,
  tls_certificate_check,
  ssl_verify_fun
]}.
{overrides, [
  {override, gproc, [{deps, []}]},
  {override, grpcbox, [
    {deps, [chatterbox, ctx, acceptor_pool, gproc]},
    {project_plugins, []}
  ]},
  {override, chatterbox, [{deps, [hpack]}]},
  {override, opentelemetry, [{deps, [opentelemetry_api]}]},
  {override, opentelemetry_exporter, [
    {deps, [grpcbox, tls_certificate_check, opentelemetry, opentelemetry_api]}
  ]},
  {override, tls_certificate_check, [
    {deps, [ssl_verify_fun]},
    {project_plugins, []}
  ]}
]}.
ERL
mkdir -p _checkouts
ln -sfn ../.otel-erlang-sdk/opentelemetry_api _checkouts/opentelemetry_api
ln -sfn ../.otel-erlang-sdk/opentelemetry _checkouts/opentelemetry
ln -sfn ../.otel-erlang-sdk/opentelemetry_exporter _checkouts/opentelemetry_exporter
ln -sfn ../.otel-erlang-sdk/grpcbox _checkouts/grpcbox
ln -sfn ../.otel-erlang-sdk/ts_chatterbox _checkouts/chatterbox
ln -sfn ../.otel-erlang-sdk/hpack_erl _checkouts/hpack
ln -sfn ../.otel-erlang-sdk/ctx _checkouts/ctx
ln -sfn ../.otel-erlang-sdk/acceptor_pool _checkouts/acceptor_pool
ln -sfn ../.otel-erlang-sdk/gproc _checkouts/gproc
ln -sfn ../.otel-erlang-sdk/tls_certificate_check _checkouts/tls_certificate_check
ln -sfn ../.otel-erlang-sdk/ssl_verify_fun _checkouts/ssl_verify_fun
cat > telemetry/mix.exs.example <<'EX'
defp deps do
  [
    {:opentelemetry_api, path: "../.otel-erlang-sdk/opentelemetry_api", override: true},
    {:opentelemetry, path: "../.otel-erlang-sdk/opentelemetry", override: true},
    {:opentelemetry_exporter, path: "../.otel-erlang-sdk/opentelemetry_exporter", override: true},
    {:grpcbox, path: "../.otel-erlang-sdk/grpcbox", override: true},
    {:chatterbox, path: "../.otel-erlang-sdk/ts_chatterbox", override: true},
    {:hpack, path: "../.otel-erlang-sdk/hpack_erl", override: true},
    {:ctx, path: "../.otel-erlang-sdk/ctx", override: true},
    {:acceptor_pool, path: "../.otel-erlang-sdk/acceptor_pool", override: true},
    {:gproc, path: "../.otel-erlang-sdk/gproc", override: true},
    {:tls_certificate_check, path: "../.otel-erlang-sdk/tls_certificate_check", override: true},
    {:ssl_verify_fun, path: "../.otel-erlang-sdk/ssl_verify_fun", override: true}
  ]
end
EX
cat > telemetry/otel.erl.example <<'ERL'
-module(otel_entry).
-export([start/0]).

start() ->
    Tracer = opentelemetry:get_application_tracer(?MODULE),
    SpanCtx = otel_tracer:start_span(Tracer, <<"GET /">>, #{kind => server}),
    otel_span:end_span(SpanCtx),
    ok.
ERL
cat > telemetry/otel.ex.example <<'EX'
require OpenTelemetry.Tracer

OpenTelemetry.Tracer.with_span "GET /", kind: :server do
  :ok
end
EX
cat <<'ERL'
审阅 telemetry 下的示例后接入应用。rebar3 使用上面的 _checkouts，不要从 Hex 或 Git 拉取包。
启动 opentelemetry_exporter 和 opentelemetry 后再调用 otel_entry:start/0，短命进程要等导出完成后再退出。
ERL"""

_SWIFT_SDK_GUIDE = """# Swift 无通用零代码探针；下面生成 Swift Package Manager 示例，不会覆盖应用源码。
# opentelemetry-swift 2.6.0
mkdir -p telemetry
if [ -e telemetry/Package.swift.example ]; then
  printf "%s\\n" "telemetry/Package.swift.example already exists; refusing to overwrite" >&2
  exit 1
fi
cat > telemetry/Package.swift.example <<'SWIFT'
// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "app",
    dependencies: [
        .package(path: "../.otel-swift-sdk/opentelemetry-swift"),
        .package(path: "../.otel-swift-sdk/opentelemetry-swift-core")
    ],
    targets: [
        .executableTarget(
            name: "app",
            dependencies: [
                .product(name: "OpenTelemetrySdk", package: "opentelemetry-swift-core"),
                .product(name: "OpenTelemetryProtocolExporterHTTP", package: "opentelemetry-swift")
            ]
        )
    ]
)
SWIFT
cat <<'SWIFT'
审阅 telemetry/Package.swift.example 后接入应用。依赖只使用本地 path，不要改成远端包地址。
SWIFT"""


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


_DOTNET_SUPPORT_NOTE = "仅支持 Linux x86_64 glibc（Ubuntu / Debian / CentOS 及同类容器镜像）；不支持 Alpine、ARM64、Windows。"
_DOTNET_PROFILER_CLSID = "{918728DD-259F-4A6A-AC2B-B85E1B658318}"
_DOTNET_CONTAINER_HOME = "/otel-dotnet-auto"


FULL_TRACE_SAMPLE_RATE = 100


def _otel_resource_value(value: str) -> str:
    """按 OTEL_RESOURCE_ATTRIBUTES 语法编码值；Shell literal 由调用方另行处理。"""

    return quote(value, safe="-._~")


def _trace_sampler_environment(sample_rate: int) -> dict[str, str]:
    """全量沿用 SDK 默认；降采样只写入本次脚本，不表示平台正在按该比例采集。"""

    if not 1 <= sample_rate <= FULL_TRACE_SAMPLE_RATE:
        raise ValueError("sample_rate 必须在 1 到 100 之间")
    if sample_rate >= FULL_TRACE_SAMPLE_RATE:
        return {}
    ratio = format(Decimal(sample_rate) / Decimal(100), "f").rstrip("0").rstrip(".")
    return {
        "OTEL_TRACES_SAMPLER": "parentbased_traceidratio",
        "OTEL_TRACES_SAMPLER_ARG": ratio,
    }


def _traces_only_environment() -> dict[str, str]:
    return {
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
    }


def _dotnet_clr_environment(home: str) -> dict[str, str]:
    return {
        "OTEL_DOTNET_AUTO_HOME": home,
        "CORECLR_ENABLE_PROFILING": "1",
        "CORECLR_PROFILER": _DOTNET_PROFILER_CLSID,
        "CORECLR_PROFILER_PATH": f"{home}/linux-x64/OpenTelemetry.AutoInstrumentation.Native.so",
        "DOTNET_STARTUP_HOOKS": f"{home}/net/OpenTelemetry.AutoInstrumentation.StartupHook.dll",
        "DOTNET_ADDITIONAL_DEPS": f"{home}/AdditionalDeps",
        "DOTNET_SHARED_STORE": f"{home}/store",
    }


def _dotnet_host_clr_exports() -> tuple[str, ...]:
    lines = ['export OTEL_DOTNET_AUTO_HOME="$HOME/.otel-dotnet-auto"', '. "$OTEL_DOTNET_AUTO_HOME/instrument.sh"']
    for key, value in _dotnet_clr_environment("$OTEL_DOTNET_AUTO_HOME").items():
        if key == "OTEL_DOTNET_AUTO_HOME":
            continue
        if key == "CORECLR_PROFILER":
            lines.append(f"export {key}={shlex.quote(value)}")
        else:
            lines.append(f'export {key}="{value}"')
    return tuple(lines)


def _with_dotnet_support_note(language: str, code: str) -> str:
    if language != "dotnet":
        return code
    return f"# {_DOTNET_SUPPORT_NOTE}\n{code}"


def _kubernetes_snippet(language: str, environment: dict[str, str], probe_download_url: str) -> str:
    """生成可作为 strategic merge patch 使用的容器环境片段。"""

    image_guidance = {
        "python": f"应用镜像需预装 opentelemetry-distro[otlp] 并使用 opentelemetry-instrument 启动。离线包：{probe_download_url}",
        "nodejs": f"应用镜像需预装 @opentelemetry/auto-instrumentations-node。离线包：{probe_download_url}",
        "java": f"应用镜像需包含 /opt/opentelemetry-javaagent.jar。离线包：{probe_download_url}",
        "go": f"Go 无通用自动探针；应用二进制需先完成 OpenTelemetry Go SDK 初始化。离线包：{probe_download_url}",
        "dotnet": f"应用镜像需包含 {_DOTNET_CONTAINER_HOME}，并使用 dotnet App.dll 启动。离线包：{probe_download_url}",
        "php": (
            "应用镜像需预装 PHP 8.1–8.4 NTS 扩展，并从离线包安装 " + " ".join((*PHP_COMPOSER_PACKAGES, *PHP_DATABASE_PACKAGES)) + "。PDO 与 MySQLi 仅用于 PHP 8.2+。"
            f"离线包：{probe_download_url}"
        ),
        "ruby": f"Ruby >= 3.3，无通用自动探针；应用需先加入 Rack 初始化。离线包：{probe_download_url}",
        "cpp": f"C++ 无通用自动探针；应用需先对着 prefix 编译入口 Span。离线包：{probe_download_url}",
        "erlang": f"Erlang/Elixir 无通用自动探针；应用需先加入 path 依赖和入口 Span。离线包：{probe_download_url}",
        "swift": f"Swift 无通用自动探针；应用需先使用本地 Swift Package。离线包：{probe_download_url}",
    }
    runtime_environment = {
        "nodejs": {"NODE_OPTIONS": "--require @opentelemetry/auto-instrumentations-node/register"},
        "java": {"JAVA_TOOL_OPTIONS": "-javaagent:/opt/opentelemetry-javaagent.jar"},
        "dotnet": _dotnet_clr_environment(_DOTNET_CONTAINER_HOME),
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
            "curl --fail --silent --show-error --location --insecure",
            shlex.quote(url),
            f"--output {output}",
        )
    )


def _probe_sha256_check(path: str, digest: str) -> str:
    if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
        raise ProbeArtifactNotFound(path)
    quoted_digest = shlex.quote(digest.lower())
    quoted_path = shlex.quote(path)
    return (
        "if command -v sha256sum >/dev/null 2>&1; then "
        f"printf '%s  %s\\n' {quoted_digest} {quoted_path} | sha256sum -c -; "
        f"else printf '%s  %s\\n' {quoted_digest} {quoted_path} | shasum -a 256 -c -; fi"
    )


GO_OFFLINE_MODULES = (
    "go.opentelemetry.io/otel",
    "go.opentelemetry.io/otel/sdk",
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
    "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp",
    "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc",
    "go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin",
    "go.opentelemetry.io/contrib/instrumentation/github.com/labstack/echo/otelecho",
)

PHP_COMPOSER_PACKAGES = (
    "open-telemetry/sdk:1.15.0",
    "open-telemetry/exporter-otlp:1.4.0",
    "open-telemetry/opentelemetry-auto-laravel:1.10.0",
    "open-telemetry/opentelemetry-auto-symfony:1.7.0",
    "open-telemetry/opentelemetry-auto-slim:1.5.1",
    "open-telemetry/opentelemetry-auto-guzzle:1.5.0",
)
PHP_DATABASE_PACKAGES = (
    "open-telemetry/opentelemetry-auto-pdo:0.6.0",
    "open-telemetry/opentelemetry-auto-mysqli:0.5.0",
)


def _ruby_version_gate() -> str:
    return (
        'ruby -e \'major, minor, = RUBY_VERSION.split(".").map(&:to_i); '
        'abort("Ruby 3.3 or newer is required") if major < 3 || (major == 3 && minor < 3)\''
    )


def _manual_archive_install(artifact_name: str, directory: str, follow_up: str = "") -> tuple[str, ...]:
    steps = (f"mkdir -p {directory}", f"tar -xf {artifact_name} -C {directory}")
    if follow_up:
        return (*steps, follow_up)
    return steps


_MANUAL_SDK_ARCHIVES = {
    "ruby": (
        RUBY_SDK_ARTIFACT_NAME,
        ".otel-ruby-sdk",
        "gem install --local --no-document --ignore-dependencies .otel-ruby-sdk/cache/*.gem",
    ),
    "cpp": (CPP_SDK_ARTIFACT_NAME, ".otel-cpp-sdk", ""),
    "erlang": (ERLANG_SDK_ARTIFACT_NAME, ".otel-erlang-sdk", ""),
    "swift": (SWIFT_SDK_ARTIFACT_NAME, ".otel-swift-sdk", ""),
}


def _go_module_download(prefix: str) -> str:
    return f"{prefix} {' '.join(GO_OFFLINE_MODULES)}"


def _require_probe_sha256(artifact_name: str) -> str:
    digest = get_probe_artifact_sha256(artifact_name)
    if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
        raise ProbeArtifactNotFound(artifact_name)
    return digest.lower()


def _python_offline_install(wheels_dir: str) -> tuple[str, str, str]:
    return (
        f'python -m pip install --no-index --find-links {wheels_dir} "opentelemetry-distro[otlp]"',
        "opentelemetry-bootstrap -a requirements > otel-bootstrap-requirements.txt",
        f"python -m pip install --no-index --find-links {wheels_dir} -r otel-bootstrap-requirements.txt",
    )


def _php_prepare_script(root: str) -> str:
    web_packages = " ".join(PHP_COMPOSER_PACKAGES)
    database_packages = " ".join(PHP_DATABASE_PACKAGES)
    repository = json.dumps({"type": "artifact", "url": f"{root}/dist"}, separators=(",", ":"))
    return "\n".join(
        (
            "# PHP NTS 8.1–8.4。ZTS 和其他版本直接退出。",
            "php -r 'exit(PHP_ZTS !== 0 ? 1 : 0);' || { printf '%s\\n' 'PHP ZTS is not supported' >&2; exit 1; }",
            """php_version=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')""",
            'case "$php_version" in',
            "  8.1|8.2|8.3|8.4) ;;",
            "  *) printf '%s\\n' \"PHP $php_version is not supported\" >&2; exit 1 ;;",
            "esac",
            """extension_dir=$(php -r 'echo ini_get("extension_dir");')""",
            """scan_dir=$(php -r 'echo PHP_CONFIG_FILE_SCAN_DIR;')""",
            'if [ -z "$scan_dir" ] || [ ! -d "$scan_dir" ]; then ' "printf '%s\\n' 'PHP additional ini directory is missing' >&2; exit 1; fi",
            f'cp {root}/php/"$php_version"/nts/opentelemetry.so "$extension_dir/opentelemetry.so"',
            "printf '%s\\n' 'extension=opentelemetry.so' > \"$scan_dir/99-opentelemetry.ini\"",
            f"composer config repositories.otel {shlex.quote(repository)}",
            "export COMPOSER_DISABLE_NETWORK=1",
            f'composer_packages="{web_packages}"',
            'case "$php_version" in',
            f'  8.2|8.3|8.4) composer_packages="$composer_packages {database_packages}" ;;',
            "esac",
            "composer require --no-interaction --prefer-dist --update-with-dependencies $composer_packages",
        )
    )


def _obi_config(endpoint: str, executable: str) -> str:
    return "\n".join(
        (
            'file_format: "1.0"',
            "tracer_provider:",
            "  processors:",
            "    - batch:",
            "        exporter:",
            "          otlp_http:",
            f"            endpoint: {json.dumps(endpoint)}",
            "extensions:",
            "  obi:",
            '    version: "2.0"',
            "    capture:",
            "      policy:",
            "        default_action: exclude",
            "      rules:",
            "        - action: include",
            "          match:",
            "            process:",
            f"              exe_path_glob: [{json.dumps(executable)}]",
            "      instrumentation:",
            "        http:",
            "          enabled:",
            "            traces: true",
            "            metrics: false",
        )
    )


def _obi_preflight() -> str:
    return "\n".join(
        (
            "if [ \"$(uname -s)\" != Linux ]; then printf '%s\\n' 'OBI requires Linux' >&2; exit 1; fi",
            "kernel_release=$(uname -r)",
            "kernel_major=${kernel_release%%.*}",
            "kernel_rest=${kernel_release#*.}",
            "kernel_minor=${kernel_rest%%.*}",
            'case "$kernel_major$kernel_minor" in',
            "  *[!0-9]*) printf '%s\\n' 'OBI requires a numeric Linux kernel version' >&2; exit 1 ;;",
            "esac",
            'if [ "$kernel_major" -lt 4 ] || { [ "$kernel_major" -eq 4 ] && [ "$kernel_minor" -lt 18 ]; }; then',
            "  printf '%s\\n' \"Linux kernel $kernel_release is older than 4.18\" >&2",
            "  exit 1",
            "fi",
            'if [ "$kernel_major" -lt 5 ] || { [ "$kernel_major" -eq 5 ] && [ "$kernel_minor" -lt 8 ]; }; then',
            "  if [ ! -r /sys/kernel/btf/vmlinux ]; then",
            "    printf '%s\\n' \"Linux kernel $kernel_release needs an eBPF backport and BTF\" >&2",
            "    exit 1",
            "  fi",
            "fi",
            "if [ ! -r /sys/kernel/btf/vmlinux ]; then",
            "  printf '%s\\n' 'OBI requires a readable /sys/kernel/btf/vmlinux' >&2",
            "  exit 1",
            "fi",
            'if [ "$(id -u)" -ne 0 ]; then',
            "  cap_eff=$(awk '/^CapEff:/ { print $2 }' /proc/self/status)",
            '  case "$cap_eff" in',
            "    ''|0000000000000000)",
            "      printf '%s\\n' 'OBI needs root or the capabilities required by OBI v1.0.0' >&2",
            "      exit 1",
            "      ;;",
            "  esac",
            "fi",
        )
    )


def _obi_host_snippet(
    probe_download_url: str,
    probe_sha256: str,
    endpoint: str,
    executable: str,
    environment: dict[str, str],
    resource_assignment: str,
    identity_setup: tuple[str, ...],
) -> str:
    exports = list(identity_setup)
    for key, value in environment.items():
        if key == "OTEL_RESOURCE_ATTRIBUTES":
            exports.append(f"export {key}={resource_assignment}")
        else:
            exports.append(f"export {key}={shlex.quote(value)}")
    return "\n".join(
        (
            "# OBI v1.0.0 Linux amd64。未安装语言探针时，只采集指定 Go 可执行文件，不替换 Go SDK。",
            "# 同一进程不要再装 Java、Python、Node.js、.NET、PHP 或 Go SDK。",
            "# 内核需要 Linux 5.8+，或带 eBPF backport 且有 BTF 的 RHEL 系 4.18+。",
            "# 需要 root 或上游要求的 capabilities。内核、BTF 或权限不够时退出，不修改应用二进制。",
            "# 已知限制：子 Span 时间戳可能早于父 Span。",
            _obi_preflight(),
            _curl_download(probe_download_url, OBI_ARTIFACT_NAME),
            _probe_sha256_check(OBI_ARTIFACT_NAME, probe_sha256),
            'mkdir -p "$HOME/.otel-obi"',
            f'tar -xf {OBI_ARTIFACT_NAME} -C "$HOME/.otel-obi"',
            "cat > \"$HOME/.otel-obi/obi.yaml\" <<'OBI_CONFIG'",
            _obi_config(endpoint, executable),
            "OBI_CONFIG",
            *exports,
            'obi_bin=$(find "$HOME/.otel-obi" -type f -name obi | head -n 1)',
            "if [ -z \"$obi_bin\" ]; then printf '%s\\n' 'OBI binary was not found' >&2; exit 1; fi",
            'exec "$obi_bin" --config "$HOME/.otel-obi/obi.yaml"',
        )
    )


def _windows_dotnet_snippet(probe_download_url: str, probe_sha256: str, environment: dict[str, str]) -> str:
    lines = [
        "# .NET Windows auto-instrumentation 1.16.0. ASP.NET Framework is available on this artifact.",
        "# This script sets the current process only. Restart the application yourself.",
        f"$artifact = '{DOTNET_WINDOWS_ARTIFACT_NAME}'",
        f"$url = '{probe_download_url}'",
        "curl.exe --fail --silent --show-error --location --insecure $url --output $artifact",
        f"$expected = '{probe_sha256}'",
        "$actual = (Get-FileHash -Algorithm SHA256 $artifact).Hash.ToLower()",
        "if ($actual -ne $expected) { Write-Error 'probe SHA256 mismatch'; exit 1 }",
        "$installDir = Join-Path $env:USERPROFILE '.otel-dotnet-auto'",
        "Expand-Archive -Force -Path $artifact -DestinationPath $installDir",
        "$env:OTEL_DOTNET_AUTO_HOME = $installDir",
        "$env:CORECLR_ENABLE_PROFILING = '1'",
        "$env:CORECLR_PROFILER = '{918728DD-259F-4A6A-AC2B-B85E1B658318}'",
        "$env:CORECLR_PROFILER_PATH_64 = Join-Path $installDir 'win-x64\\OpenTelemetry.AutoInstrumentation.Native.dll'",
        "$env:COR_ENABLE_PROFILING = '1'",
        "$env:COR_PROFILER = '{918728DD-259F-4A6A-AC2B-B85E1B658318}'",
        "$env:COR_PROFILER_PATH_64 = Join-Path $installDir 'win-x64\\OpenTelemetry.AutoInstrumentation.Native.dll'",
        "$env:ASPNETCORE_HOSTINGSTARTUPASSEMBLIES = 'OpenTelemetry.AutoInstrumentation.AspNetCoreBootstrapper'",
        "$env:DOTNET_STARTUP_HOOKS = Join-Path $installDir 'net\\OpenTelemetry.AutoInstrumentation.StartupHook.dll'",
    ]
    for key, value in environment.items():
        if key == "OTEL_RESOURCE_ATTRIBUTES":
            prefix = value.replace("${OTEL_SERVICE_INSTANCE_ID}", "").replace("'", "''")
            lines.append("$instanceId = [guid]::NewGuid().ToString()")
            lines.append(f"$env:OTEL_RESOURCE_ATTRIBUTES = '{prefix}' + $instanceId")
            continue
        lines.append(f"$env:{key} = '{value.replace(chr(39), chr(39) * 2)}'")
    lines.append("Write-Output 'Start the application in this PowerShell session so it inherits these variables.'")
    return "\n".join(lines)


def _host_install_commands(language: str, probe_download_url: str, probe_sha256: str) -> str:
    if language == "python":
        pip_install, bootstrap_requirements, bootstrap_install = _python_offline_install("otel-python-wheels")
        return "\n".join(
            (
                _curl_download(probe_download_url, PYTHON_WHEELS_ARTIFACT_NAME),
                _probe_sha256_check(PYTHON_WHEELS_ARTIFACT_NAME, probe_sha256),
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
                _probe_sha256_check(NODEJS_AUTO_ARTIFACT_NAME, probe_sha256),
                f"npm install --offline --save ./{NODEJS_AUTO_ARTIFACT_NAME}",
            )
        )
    if language == "java":
        return "\n".join(
            (
                _curl_download(probe_download_url, JAVA_AGENT_ARTIFACT_NAME),
                _probe_sha256_check(JAVA_AGENT_ARTIFACT_NAME, probe_sha256),
            )
        )
    if language == "go":
        return "\n".join(
            (
                _curl_download(probe_download_url, GO_SDK_ARTIFACT_NAME),
                _probe_sha256_check(GO_SDK_ARTIFACT_NAME, probe_sha256),
                "mkdir -p .otel-go-sdk",
                f"unzip -o -q {GO_SDK_ARTIFACT_NAME} -d .otel-go-sdk",
                'export GOPROXY="file://$(pwd)/.otel-go-sdk"',
                "export GOSUMDB=off",
                _go_module_download("go mod download"),
            )
        )
    if language == "dotnet":
        return "\n".join(
            (
                _curl_download(probe_download_url, DOTNET_AUTO_ARTIFACT_NAME),
                _probe_sha256_check(DOTNET_AUTO_ARTIFACT_NAME, probe_sha256),
                'mkdir -p "$HOME/.otel-dotnet-auto"',
                f'unzip -o -q {DOTNET_AUTO_ARTIFACT_NAME} -d "$HOME/.otel-dotnet-auto"',
                *_dotnet_host_clr_exports(),
            )
        )
    if language == "php":
        return "\n".join(
            (
                _curl_download(probe_download_url, PHP_AUTO_ARTIFACT_NAME),
                _probe_sha256_check(PHP_AUTO_ARTIFACT_NAME, probe_sha256),
                "mkdir -p otel-php",
                f"tar -xf {PHP_AUTO_ARTIFACT_NAME} -C otel-php",
                _php_prepare_script("otel-php"),
            )
        )
    if language in _MANUAL_SDK_ARCHIVES:
        artifact, directory, follow_up = _MANUAL_SDK_ARCHIVES[language]
        steps = [
            _curl_download(probe_download_url, artifact),
            _probe_sha256_check(artifact, probe_sha256),
            *_manual_archive_install(artifact, directory, follow_up),
        ]
        if language == "ruby":
            steps.insert(0, _ruby_version_gate())
        return "\n".join(steps)
    return "# Install the selected OpenTelemetry SDK."


def _docker_install_commands(language: str, probe_download_url: str, probe_sha256: str) -> str:
    quoted_url = shlex.quote(probe_download_url)
    if language == "python":
        output = f"/tmp/{PYTHON_WHEELS_ARTIFACT_NAME}"
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
                _probe_sha256_check(output, probe_sha256),
                "mkdir -p /opt/otel-python-wheels",
                f"tar -xf {output} -C /opt/otel-python-wheels",
                'python -m pip install --no-index --find-links /opt/otel-python-wheels "opentelemetry-distro[otlp]"',
                "opentelemetry-bootstrap -a requirements > /tmp/otel-bootstrap-requirements.txt",
                "python -m pip install --no-index --find-links /opt/otel-python-wheels -r /tmp/otel-bootstrap-requirements.txt",
            )
        )
    if language == "nodejs":
        output = f"/tmp/{NODEJS_AUTO_ARTIFACT_NAME}"
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
                _probe_sha256_check(output, probe_sha256),
                f"npm install --offline --save {output}",
            )
        )
    if language == "java":
        output = f"/opt/{JAVA_AGENT_ARTIFACT_NAME}"
        curl = " \\\n  ".join(
            (
                "RUN curl --fail --silent --show-error --location --insecure",
                quoted_url,
                f"--output {output}",
            )
        )
        return f"{curl} && {_probe_sha256_check(output, probe_sha256)}"
    if language == "go":
        output = f"/tmp/{GO_SDK_ARTIFACT_NAME}"
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
                _probe_sha256_check(output, probe_sha256),
                "mkdir -p /opt/otel-go-sdk",
                f"unzip -o -q {output} -d /opt/otel-go-sdk",
                _go_module_download("GOPROXY=file:///opt/otel-go-sdk GOSUMDB=off go mod download"),
            )
        )
    if language == "dotnet":
        output = f"/tmp/{DOTNET_AUTO_ARTIFACT_NAME}"
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
                _probe_sha256_check(output, probe_sha256),
                f"mkdir -p {_DOTNET_CONTAINER_HOME}",
                f"unzip -o -q {output} -d {_DOTNET_CONTAINER_HOME}",
            )
        )
    if language == "php":
        output = f"/tmp/{PHP_AUTO_ARTIFACT_NAME}"
        return " && ".join(
            (
                f"RUN curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
                _probe_sha256_check(output, probe_sha256),
                "mkdir -p /opt/otel-php",
                f"tar -xf {output} -C /opt/otel-php",
                "sh -c " + shlex.quote(_php_prepare_script("/opt/otel-php")),
            )
        )
    manual_archives = {
        "ruby": (
            RUBY_SDK_ARTIFACT_NAME,
            "/opt/otel-ruby-sdk",
            "gem install --local --no-document --ignore-dependencies /opt/otel-ruby-sdk/cache/*.gem",
        ),
        "cpp": (CPP_SDK_ARTIFACT_NAME, "/opt/otel-cpp-sdk", ""),
        "erlang": (ERLANG_SDK_ARTIFACT_NAME, "/opt/otel-erlang-sdk", ""),
        "swift": (SWIFT_SDK_ARTIFACT_NAME, "/opt/otel-swift-sdk", ""),
    }
    if language in manual_archives:
        artifact_name, directory, follow_up = manual_archives[language]
        output = f"/tmp/{artifact_name}"
        commands = [
            f"curl --fail --silent --show-error --location --insecure {quoted_url} --output {output}",
            _probe_sha256_check(output, probe_sha256),
            *_manual_archive_install(output, directory, follow_up),
        ]
        if language == "ruby":
            commands.insert(0, _ruby_version_gate())
        return "RUN " + " && ".join(commands)
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
                    apm_text(None, "error.invalid_cloud_region"),
                    message_key="error.invalid_cloud_region",
                ) from exc
            if region_id < 1 or not region_name:
                raise CloudRegionConfigurationError(
                    "invalid_cloud_region",
                    apm_text(None, "error.invalid_cloud_region"),
                    message_key="error.invalid_cloud_region",
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
                apm_text(None, "error.cloud_region_receiver_unavailable"),
                message_key="error.cloud_region_receiver_unavailable",
            )
        regions = self.list_regions(node_mgmt)
        region = next((item for item in regions if item["id"] == cloud_region_id), None)
        if region is None:
            raise CloudRegionConfigurationError(
                "cloud_region_not_found",
                apm_text(None, "error.cloud_region_not_found"),
                message_key="error.cloud_region_not_found",
            )

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
                    apm_text(None, "error.cloud_region_address_missing"),
                    message_key="error.cloud_region_address_missing",
                )
            try:
                proxy_address = _receiver_host_from_node_server_url(node_server_url)
            except ValueError as exc:
                raise CloudRegionConfigurationError(
                    "invalid_cloud_region_proxy_address",
                    apm_text(None, "error.cloud_region_address_invalid"),
                    message_key="error.cloud_region_address_invalid",
                ) from exc
        try:
            proxy_address = _normalize_proxy_address(proxy_address)
        except ValueError as exc:
            raise CloudRegionConfigurationError(
                "invalid_cloud_region_proxy_address",
                apm_text(None, "error.cloud_region_address_invalid"),
                message_key="error.cloud_region_address_invalid",
            ) from exc

        probe_download_url = ""
        if include_probe_download:
            node_server_url = _node_server_url()
            if not str(node_server_url or "").strip():
                raise CloudRegionConfigurationError(
                    "probe_download_unavailable",
                    apm_text(None, "error.probe_download_url_missing"),
                    message_key="error.probe_download_url_missing",
                )
            try:
                download_base = _download_base_from_node_server_url(node_server_url)
                probe_download_url = build_probe_artifact_download_url(download_base, probe_artifact_name)
            except (ValueError, ProbeArtifactNotFound) as exc:
                raise CloudRegionConfigurationError(
                    "probe_download_unavailable",
                    apm_text(None, "error.probe_download_url_invalid"),
                    message_key="error.probe_download_url_invalid",
                ) from exc

        return CloudRegionEndpoints(
            region_id=region["id"],
            region_name=region["name"],
            http_endpoint=f"http://{proxy_address}:{OTLP_HTTP_PORT}",
            probe_download_url=probe_download_url,
        )

    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet:
        artifact_name = validate_probe_selection(
            language=request.language,
            runtime=request.runtime,
            probe_platform=request.probe_platform,
            process_executable=request.process_executable,
        )
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
            **_trace_sampler_environment(request.sample_rate),
        }
        if request.language in {"dotnet", "php", "obi", "ruby", "cpp", "erlang", "swift"}:
            environment.update(_traces_only_environment())
        if request.language == "php":
            environment["OTEL_PHP_AUTOLOAD_ENABLED"] = "true"
        if request.language in {"php", "ruby", "cpp", "erlang", "swift"}:
            environment["OTEL_TRACES_EXPORTER"] = "otlp"
        if request.language == "erlang":
            environment["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http_protobuf"

        if request.language == "dotnet" and request.probe_platform == "windows":
            code = _windows_dotnet_snippet(
                request.probe_download_url,
                _require_probe_sha256(artifact_name),
                environment,
            )
            return IngestSnippet(environment=environment, code=code)
        if request.language == "obi":
            code = _obi_host_snippet(
                request.probe_download_url,
                _require_probe_sha256(artifact_name),
                environment["OTEL_EXPORTER_OTLP_ENDPOINT"],
                request.process_executable,
                environment,
                resource_assignment,
                runtime_profile.identity_setup,
            )
            return IngestSnippet(environment=environment, code=code)

        if request.runtime == "kubernetes":
            code = _kubernetes_snippet(request.language, environment, request.probe_download_url)
        elif request.runtime == "docker":
            probe_sha256 = _require_probe_sha256(artifact_name)
            image_install_commands = _docker_install_commands(request.language, request.probe_download_url, probe_sha256)
            docker_start_commands = {
                "python": "opentelemetry-instrument python app.py",
                "nodejs": "node app.js",
                "java": "java -jar app.jar",
                "go": "./app",
                "dotnet": "dotnet App.dll",
                "php": "php app.php",
                "ruby": "rackup config.ru",
                "cpp": "./app",
                "erlang": "./app",
                "swift": "./app",
            }
            runtime_environment = {
                "nodejs": {"NODE_OPTIONS": "--require @opentelemetry/auto-instrumentations-node/register"},
                "java": {"JAVA_TOOL_OPTIONS": "-javaagent:/opt/opentelemetry-javaagent.jar"},
                "dotnet": _dotnet_clr_environment(_DOTNET_CONTAINER_HOME),
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
                    image_install_commands,
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
            probe_sha256 = _require_probe_sha256(artifact_name)
            install_commands = _host_install_commands(request.language, request.probe_download_url, probe_sha256)
            start_commands = {
                "python": "opentelemetry-instrument python app.py",
                "nodejs": "node --require @opentelemetry/auto-instrumentations-node/register app.js",
                "java": "java -javaagent:./opentelemetry-javaagent.jar -jar app.jar",
                "go": _GO_SDK_GUIDE,
                "dotnet": "dotnet App.dll",
                "php": "php app.php",
                "ruby": _RUBY_SDK_GUIDE,
                "cpp": _CPP_SDK_GUIDE,
                "erlang": _ERLANG_SDK_GUIDE,
                "swift": _SWIFT_SDK_GUIDE,
            }
            export_lines = [f"# {runtime_profile.guidance}", *runtime_profile.identity_setup]
            for key, value in environment.items():
                if key == "OTEL_RESOURCE_ATTRIBUTES":
                    export_lines.append(f"export {key}={resource_assignment}")
                else:
                    export_lines.append(f"export {key}={shlex.quote(value)}")
            code = "\n".join(
                (
                    "# 1. 安装探针",
                    install_commands,
                    "",
                    "# 2. 配置上报（端点与资源属性使用标准 OTEL_* 环境变量）",
                    *export_lines,
                    "",
                    "# 3. 启动应用",
                    start_commands.get(request.language, "# Start the instrumented application."),
                )
            )
        return IngestSnippet(environment=environment, code=_with_dotnet_support_note(request.language, code))
