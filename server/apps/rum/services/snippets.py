from __future__ import annotations

import json
import math

from apps.rum.constants import (
    BKLITE_RUM_SDK_VERSION,
    DEFAULT_REPLAY_SAMPLING_RATE,
    FARO_WEB_SDK_VERSION,
    GRAFANA_RRWEB_VERSION,
    REPLAY_PRIVACY_BLOCK,
    REPLAY_PRIVACY_MASK_TEXT,
)
from apps.rum.services.validation import ValidationError, valid_application, valid_browser_key


def _quoted(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _format_rate(rate: float) -> str:
    return format(rate, "g")


def _coerce_session_sampling_rate(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValidationError("sessionSamplingRate must be between 0 and 1")
    rate = float(raw)
    if not math.isfinite(rate) or rate < 0 or rate > 1:
        raise ValidationError("sessionSamplingRate must be between 0 and 1")
    return rate


def _cdn_endpoint_base(collect_url: str, replay_url: str) -> str:
    collect_base = collect_url.removesuffix("/collect").rstrip("/")
    replay_base = replay_url.removesuffix("/replay").rstrip("/")
    return collect_base if collect_base == replay_base else collect_base


def apply_snippet_defaults(data: dict, sdk_cdn_url: str) -> dict:
    raw_session_rate = data.get("sessionSamplingRate", None)
    if raw_session_rate is None:
        raw_session_rate = 1.0
    out = {
        "application": (data.get("application") or "").strip(),
        "environment": (data.get("environment") or "").strip(),
        "release": (data.get("release") or "").strip(),
        "browserKey": (data.get("browserKey") or "").strip(),
        "collectUrl": (data.get("collectUrl") or "").strip(),
        "replayUrl": (data.get("replayUrl") or "").strip(),
        "sdkCdnUrl": (data.get("sdkCdnUrl") or "").strip() or sdk_cdn_url.strip(),
        "replay": dict(data.get("replay") or {}),
        "sessionSamplingRate": raw_session_rate,
    }
    replay = out["replay"]
    replay["enabled"] = bool(replay.get("enabled"))
    rate = float(replay.get("samplingRate") or 0)
    if replay["enabled"] and rate <= 0:
        rate = DEFAULT_REPLAY_SAMPLING_RATE
    replay["samplingRate"] = rate
    return out


def validate_snippet_input(data: dict) -> None:
    if not valid_application(data["application"]):
        raise ValidationError("application must be a stable identifier (letters, digits, . _ : -)")
    if not valid_browser_key(data["browserKey"]):
        raise ValidationError("browser key is invalid")
    for key in ("collectUrl", "replayUrl"):
        value = data[key]
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValidationError("collectUrl and replayUrl must be absolute http(s) URLs")
    if data["replay"]["enabled"]:
        rate = data["replay"]["samplingRate"]
        if rate <= 0 or rate > 1:
            raise ValidationError("replay samplingRate must be between 0 and 1")
    data["sessionSamplingRate"] = _coerce_session_sampling_rate(data["sessionSamplingRate"])


def build_snippet(data: dict, sdk_cdn_url: str) -> dict:
    prepared = apply_snippet_defaults(data, sdk_cdn_url)
    validate_snippet_input(prepared)
    npm_main, npm_advanced = _module_snippet(prepared, react=False)
    react_main, react_advanced = _module_snippet(prepared, react=True)
    cdn_main, cdn_advanced = _cdn_snippet(prepared)
    return {
        "npm": npm_main,
        "react": react_main,
        "generic": npm_main,
        "cdn": cdn_main,
        "advanced": {
            "npm": npm_advanced,
            "react": react_advanced,
            "generic": npm_advanced,
            "cdn": cdn_advanced,
        },
    }


def _snippet_text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _module_snippet(input_data: dict, *, react: bool) -> tuple[str, str]:
    advanced = _version_pin_lines(input_data, react=react)
    advanced.append("")
    advanced.extend(_view_patch_lines(react=react))
    return _snippet_text(_init_lines(input_data, react=react)), _snippet_text(advanced)


def _version_pin_lines(input_data: dict, *, react: bool) -> list[str]:
    packages = [
        f"bklite-rum-sdk@{BKLITE_RUM_SDK_VERSION}",
        f"@grafana/faro-web-sdk@{FARO_WEB_SDK_VERSION}",
        f"@grafana/faro-web-tracing@{FARO_WEB_SDK_VERSION}",
    ]
    if react:
        packages.append(f"@grafana/faro-react@{FARO_WEB_SDK_VERSION}")
    if input_data["replay"]["enabled"]:
        packages.extend(
            [
                f"@grafana/faro-instrumentation-replay@{FARO_WEB_SDK_VERSION}",
                f"@grafana/rrweb@{GRAFANA_RRWEB_VERSION}",
            ]
        )
    lines: list[str] = [f"bun add --exact {' '.join(packages)}", ""]
    overrides: list[tuple[str, str]] = [
        ("@grafana/faro-core", FARO_WEB_SDK_VERSION),
        ("@grafana/faro-web-sdk", FARO_WEB_SDK_VERSION),
        ("@grafana/faro-web-tracing", FARO_WEB_SDK_VERSION),
    ]
    if react:
        overrides.append(("@grafana/faro-react", FARO_WEB_SDK_VERSION))
    if input_data["replay"]["enabled"]:
        overrides.extend(
            [
                ("@grafana/faro-instrumentation-replay", FARO_WEB_SDK_VERSION),
                ("@grafana/rrweb", GRAFANA_RRWEB_VERSION),
            ]
        )
    lines.append("// package.json overrides (pin the approved runtime line)")
    lines.append("{")
    lines.append('  "overrides": {')
    for index, (key, version) in enumerate(overrides):
        suffix = "," if index < len(overrides) - 1 else ""
        lines.append(f"    {_quoted(key)}: {_quoted(version)}{suffix}")
    lines.append("  }")
    lines.append("}")
    return lines


def _init_lines(input_data: dict, *, react: bool) -> list[str]:
    lines: list[str] = []
    imports = [
        "import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk'",
        "import { TracingInstrumentation } from '@grafana/faro-web-tracing'",
    ]
    if react:
        imports.extend(
            [
                "import { ReactIntegration } from '@grafana/faro-react'",
                "import { useEffect } from 'react'",
                "import { useLocation } from 'react-router-dom'",
            ]
        )
    if input_data["replay"]["enabled"]:
        imports.extend(
            [
                "import { ReplayInstrumentation } from '@grafana/faro-instrumentation-replay'",
                "import { takeFullSnapshot } from '@grafana/rrweb'",
            ]
        )
    imports.append("import { CoreRumTransport, sanitizeReplayEvent } from 'bklite-rum-sdk'")
    lines.extend(imports)
    lines.append("")

    indent = "  " if react else ""
    if react:
        lines.append("let faro: ReturnType<typeof initializeFaro> | undefined")
        lines.append("")
        lines.append("function getFaro() {")
        lines.append("  if (faro) return faro")
        lines.append("  if (typeof window === 'undefined') return undefined")
        lines.append("")
        lines.append("  faro = initializeFaro({")
    else:
        lines.append("const faro = initializeFaro({")

    lines.append(f"{indent}  app: {{")
    lines.append(f"{indent}    name: {_quoted(input_data['application'])},")
    if input_data["environment"]:
        lines.append(f"{indent}    environment: {_quoted(input_data['environment'])},")
    if input_data["release"]:
        lines.append(f"{indent}    release: {_quoted(input_data['release'])},")
    lines.append(f"{indent}  }},")
    session_rate = _format_rate(input_data["sessionSamplingRate"])
    lines.append(f"{indent}  sessionTracking: {{ enabled: true, samplingRate: {session_rate} }},")
    lines.append(f"{indent}  pageTracking: {{ generatePageId: () => crypto.randomUUID() }},")
    lines.append(f"{indent}  transports: [")
    lines.append(f"{indent}    new CoreRumTransport({{")
    lines.append(f"{indent}      collectUrl: {_quoted(input_data['collectUrl'])},")
    lines.append(f"{indent}      replayUrl: {_quoted(input_data['replayUrl'])},")
    lines.append(f"{indent}      apiKey: {_quoted(input_data['browserKey'])},")
    lines.append(f"{indent}      replay: {{ enabled: {json.dumps(input_data['replay']['enabled'])} }},")
    lines.append(f"{indent}    }}),")
    lines.append(f"{indent}  ],")
    lines.append(f"{indent}  instrumentations: [")
    lines.append(f"{indent}    ...getWebInstrumentations(),")
    lines.append(f"{indent}    new TracingInstrumentation(),")
    if react:
        lines.append(f"{indent}    new ReactIntegration(),")
    if input_data["replay"]["enabled"]:
        rate_literal = _format_rate(input_data["replay"]["samplingRate"])
        lines.append(f"{indent}    new ReplayInstrumentation({{")
        lines.append(f"{indent}      samplingRate: {rate_literal},")
        lines.append(f"{indent}      beforeSend: sanitizeReplayEvent,")
        lines.append(f"{indent}      maskAllInputs: true,")
        lines.append(f"{indent}      maskTextSelector: {_quoted(REPLAY_PRIVACY_MASK_TEXT)},")
        lines.append(f"{indent}      blockSelector: {_quoted(REPLAY_PRIVACY_BLOCK)},")
        lines.append(f"{indent}      recordCanvas: false,")
        lines.append(f"{indent}      collectFonts: false,")
        lines.append(f"{indent}      inlineImages: false,")
        lines.append(f"{indent}      recordCrossOriginIframes: false,")
        lines.append(f"{indent}    }}),")
    lines.append(f"{indent}  ],")
    lines.append(f"{indent}}})")

    if react:
        if input_data["replay"]["enabled"]:
            lines.append("  if (faro) {")
            lines.extend(_replay_scope_coordinator("    "))
            lines.append("  }")
        lines.append("  return faro")
        lines.append("}")
    elif input_data["replay"]["enabled"]:
        lines.append("")
        lines.extend(_replay_scope_coordinator(""))
    return lines


def _view_patch_lines(*, react: bool) -> list[str]:
    if react:
        return [
            "if (faro) {",
            "  faro.api.setView({ name: logicalViewNameForPathname(location.pathname) })",
            "}",
            "",
            "export function FaroRouteView() {",
            "  const pathname = useLocation().pathname",
            "",
            "  useEffect(() => {",
            "    getFaro()?.api.setView({ name: logicalViewNameForPathname(pathname) })",
            "  }, [pathname])",
            "",
            "  return null",
            "}",
            "",
            "// Render <FaroRouteView /> once inside your React Router shell.",
            "",
            "function logicalViewNameForPathname(pathname: string): string {",
            "  return pathname || '/'",
            "}",
        ]
    return [
        "if (faro) {",
        "  function syncViewFromLocation() {",
        "    faro?.api.setView({ name: logicalViewNameForPathname(location.pathname) })",
        "  }",
        "  syncViewFromLocation()",
        "  ;['pushState', 'replaceState'].forEach((method) => {",
        "    const original = history[method].bind(history)",
        "    history[method] = (...args) => {",
        "      const result = original(...args)",
        "      syncViewFromLocation()",
        "      return result",
        "    }",
        "  })",
        "  window.addEventListener('popstate', syncViewFromLocation)",
        "}",
        "",
        "function logicalViewNameForPathname(pathname: string): string {",
        "  return pathname || '/'",
        "}",
    ]


def _replay_scope_coordinator(indent: str) -> list[str]:
    return [
        f"{indent}let replayScope = ''",
        f"{indent}faro.metas.addListener((meta) => {{",
        f"{indent}  const nextScope = `${{meta.session?.id ?? ''}}\\u0000${{meta.user?.id ?? ''}}`",
        f"{indent}  if (nextScope === replayScope) return",
        f"{indent}  replayScope = nextScope",
        f"{indent}  try {{",
        f"{indent}    takeFullSnapshot(true)",
        f"{indent}  }} catch {{",
        f"{indent}    // Replay may be paused; its next start supplies a bootstrap snapshot.",
        f"{indent}  }}",
        f"{indent}}})",
    ]


def _cdn_snippet(input_data: dict) -> tuple[str, str]:
    sdk = input_data["sdkCdnUrl"]
    replay_asset = sdk
    for suffix in ("/bklite-rum-sdk.js", "/bklite-rum-sdk.cdn.js", "/core-rum-sdk.js", "/core-rum-sdk.cdn.js"):
        if sdk.endswith(suffix):
            replay_asset = sdk[: -len(suffix)] + "/bklite-rum-replay.js"
            break
    replay_literal = "false"
    if input_data["replay"]["enabled"]:
        replay_literal = f"{{ samplingRate: {_format_rate(input_data['replay']['samplingRate'])} }}"
    session_rate = _format_rate(input_data["sessionSamplingRate"])
    lines = [
        f'<script src="{sdk}" crossorigin="anonymous"></script>',
    ]
    if input_data["replay"]["enabled"]:
        lines.append(f'<script src="{replay_asset}" crossorigin="anonymous"></script>')
    lines.append("<script>")
    lines.append("  initCoreRum({")
    lines.append("    app: {")
    lines.append(f"      name: {_quoted(input_data['application'])},")
    if input_data["environment"]:
        lines.append(f"      environment: {_quoted(input_data['environment'])},")
    if input_data["release"]:
        lines.append(f"      release: {_quoted(input_data['release'])},")
    lines.append("    },")
    lines.append(f"    endpoint: {_quoted(_cdn_endpoint_base(input_data['collectUrl'], input_data['replayUrl']))},")
    lines.append(f"    apiKey: {_quoted(input_data['browserKey'])},")
    lines.append(f"    sessionTracking: {{ enabled: true, samplingRate: {session_rate} }},")
    lines.append(f"    replay: {replay_literal},")
    lines.append("  })")
    lines.append("</script>")
    return _snippet_text(lines), ""


def parse_analytics_range(value: str | None) -> tuple[str, bool]:
    key = (value or "24h").strip() or "24h"
    return key, key in {"1h", "24h", "7d"}
