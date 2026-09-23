from __future__ import annotations

import json

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


def _cdn_endpoint_base(collect_url: str, replay_url: str) -> str:
    collect_base = collect_url.removesuffix("/collect").rstrip("/")
    replay_base = replay_url.removesuffix("/replay").rstrip("/")
    return collect_base if collect_base == replay_base else collect_base


def apply_snippet_defaults(data: dict, sdk_cdn_url: str) -> dict:
    out = {
        "application": (data.get("application") or "").strip(),
        "environment": (data.get("environment") or "").strip(),
        "release": (data.get("release") or "").strip(),
        "browserKey": (data.get("browserKey") or "").strip(),
        "collectUrl": (data.get("collectUrl") or "").strip(),
        "replayUrl": (data.get("replayUrl") or "").strip(),
        "sdkCdnUrl": (data.get("sdkCdnUrl") or "").strip() or sdk_cdn_url.strip(),
        "replay": dict(data.get("replay") or {}),
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


def build_snippet(data: dict, sdk_cdn_url: str) -> dict[str, str]:
    prepared = apply_snippet_defaults(data, sdk_cdn_url)
    validate_snippet_input(prepared)
    return {
        "npm": _module_snippet(prepared, react=False),
        "react": _module_snippet(prepared, react=True),
        "generic": _module_snippet(prepared, react=False),
        "cdn": _cdn_snippet(prepared),
    }


def _module_snippet(input_data: dict, *, react: bool) -> str:
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
    lines.append("")

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
    lines.append(f"{indent}  sessionTracking: {{ enabled: true, samplingRate: 1 }},")
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
        rate = input_data["replay"]["samplingRate"]
        rate_literal = f"{rate:g}"
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
        lines.append("  if (faro) {")
        lines.append("    faro.api.setView({ name: logicalViewNameForPathname(location.pathname) })")
        if input_data["replay"]["enabled"]:
            lines.extend(_replay_scope_coordinator("    "))
        lines.append("  }")
        lines.append("  return faro")
        lines.append("}")
        lines.append("")
        lines.append("export function FaroRouteView() {")
        lines.append("  const pathname = useLocation().pathname")
        lines.append("")
        lines.append("  useEffect(() => {")
        lines.append("    getFaro()?.api.setView({ name: logicalViewNameForPathname(pathname) })")
        lines.append("  }, [pathname])")
        lines.append("")
        lines.append("  return null")
        lines.append("}")
        lines.append("")
        lines.append("// Render <FaroRouteView /> once inside your React Router shell.")
    else:
        if input_data["replay"]["enabled"]:
            lines.append("")
            lines.extend(_replay_scope_coordinator(""))
        lines.append("")
        lines.append("if (faro) {")
        lines.append("  function syncViewFromLocation() {")
        lines.append("    faro?.api.setView({ name: logicalViewNameForPathname(location.pathname) })")
        lines.append("  }")
        lines.append("  syncViewFromLocation()")
        lines.append("  ;['pushState', 'replaceState'].forEach((method) => {")
        lines.append("    const original = history[method].bind(history)")
        lines.append("    history[method] = (...args) => {")
        lines.append("      const result = original(...args)")
        lines.append("      syncViewFromLocation()")
        lines.append("      return result")
        lines.append("    }")
        lines.append("  })")
        lines.append("  window.addEventListener('popstate', syncViewFromLocation)")
        lines.append("}")
    lines.append("")
    lines.append("function logicalViewNameForPathname(pathname: string): string {")
    lines.append("  return pathname || '/'")
    lines.append("}")
    return "\n".join(lines) + "\n"


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


def _cdn_snippet(input_data: dict) -> str:
    sdk = input_data["sdkCdnUrl"]
    replay_asset = sdk
    for suffix in ("/bklite-rum-sdk.js", "/bklite-rum-sdk.cdn.js", "/core-rum-sdk.js", "/core-rum-sdk.cdn.js"):
        if sdk.endswith(suffix):
            replay_asset = sdk[: -len(suffix)] + "/bklite-rum-replay.js"
            break
    replay_literal = "false"
    if input_data["replay"]["enabled"]:
        replay_literal = f"{{ samplingRate: {input_data['replay']['samplingRate']:g} }}"
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
    lines.append(f"    replay: {replay_literal},")
    lines.append("  })")
    lines.append("</script>")
    return "\n".join(lines) + "\n"


def parse_analytics_range(value: str | None) -> tuple[str, bool]:
    key = (value or "24h").strip() or "24h"
    return key, key in {"1h", "24h", "7d"}
