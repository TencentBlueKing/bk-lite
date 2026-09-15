"""Parameter and UI field guards for collector release packs."""

from __future__ import annotations

import re

from apps.node_mgmt.services.collector_release.allowlist import LISTEN_RE, builtin_allowlist, extract_env_vars, extract_flags
from apps.node_mgmt.services.collector_release.errors import (
    LEVEL_INFO,
    PARAM_EXECUTABLE_PATH,
    PARAM_KEEP_LOCAL,
    PARAM_LISTEN,
    PARAM_SHELL,
    PARAM_TOO_LONG,
    PARAM_UNKNOWN_FLAG,
    UI_UNKNOWN_FIELD,
    PackIssue,
    issue,
)
from apps.node_mgmt.services.collector_release.pack import ParsedPack

SHELL_RE = re.compile(r"[;|&`\\\n]|\$\(|>>|>|<")
SAFE_LISTEN_PREFIXES = ("127.0.0.1", "localhost")


def _listen_host(value: str) -> str:
    host = value.split(":")[0].strip().strip('"').strip("'")
    return host


def guard_pack(pack: ParsedPack) -> tuple[list[PackIssue], dict]:
    allowlist = builtin_allowlist(pack.collector)
    issues: list[PackIssue] = []
    keep_local_slots = []

    params = pack.execute_parameters or ""
    if len(params) > 200:
        issues.append(issue(PARAM_TOO_LONG, f"启动参数长度为 {len(params)}，超过 200。", details={"length": len(params)}))

    if SHELL_RE.search(params):
        match = SHELL_RE.search(params)
        fragment = params[max(0, match.start() - 8) : match.end() + 8]
        issues.append(issue(PARAM_SHELL, "启动参数含有不允许的 shell 元字符。", details={"fragment": fragment}))

    listen_match = LISTEN_RE.search(params)
    if listen_match:
        host = _listen_host(listen_match.group(1))
        if not any(host == prefix or host.startswith(f"{prefix}:") for prefix in SAFE_LISTEN_PREFIXES):
            issues.append(
                issue(
                    PARAM_LISTEN,
                    f"监听地址必须是 127.0.0.1 或 localhost，实际为 {host}。",
                    details={"value": listen_match.group(1)},
                )
            )

    unknown_flags = sorted(extract_flags(params) - allowlist["flags"])
    if unknown_flags:
        issues.append(
            issue(
                PARAM_UNKNOWN_FLAG,
                f"存在白名单外的启动参数: {', '.join(unknown_flags)}。",
                details={"flags": unknown_flags},
            )
        )

    unknown_env = sorted(extract_env_vars(params) - allowlist["env_vars"] - {"LISTEN_PORT"})
    if unknown_env:
        issues.append(
            issue(
                PARAM_UNKNOWN_FLAG,
                f"存在白名单外的环境变量: {', '.join(unknown_env)}。",
                details={"env_vars": unknown_env},
            )
        )

    form_fields = (pack.ui or {}).get("form_fields") or []
    unknown_fields = sorted({str(field.get("name") or "") for field in form_fields if field.get("name")} - allowlist["form_fields"])
    if unknown_fields:
        issues.append(
            issue(
                UI_UNKNOWN_FIELD,
                f"ui.json 含白名单外表单字段: {', '.join(unknown_fields)}。",
                details={"fields": unknown_fields},
            )
        )

    from apps.node_mgmt.models.sidecar import Collector

    for artifact in pack.artifacts:
        collector = Collector.objects.filter(
            name=pack.collector,
            node_operating_system=artifact.os,
            cpu_architecture=artifact.arch,
        ).first()
        if not collector:
            continue
        if pack.executable_path and pack.executable_path != collector.executable_path:
            issues.append(
                issue(
                    PARAM_EXECUTABLE_PATH,
                    "不允许修改采集器可执行路径。",
                    details={
                        "os": artifact.os,
                        "arch": artifact.arch,
                        "value": pack.executable_path,
                        "expected": collector.executable_path,
                    },
                )
            )
        builtin_params = allowlist["params_by_slot"].get((artifact.os, artifact.arch), "")
        if collector.execute_parameters and collector.execute_parameters != builtin_params:
            local_extra = extract_flags(collector.execute_parameters) - allowlist["flags"]
            if local_extra:
                keep_local_slots.append({"os": artifact.os, "arch": artifact.arch, "id": collector.id})

    if keep_local_slots:
        issues.append(
            issue(
                PARAM_KEEP_LOCAL,
                "现场存在白名单外启动参数，将保留现场参数，不采用包内参数。",
                hint="二进制仍可导入。",
                details={"slots": keep_local_slots},
                level=LEVEL_INFO,
            )
        )

    return issues, {"allowlist": allowlist, "keep_local_slots": {item["id"] for item in keep_local_slots}}
