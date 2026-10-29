"""Diagnostic-only hook: no broker, configuration or service startup required."""

import sys

if sys.argv[1:] in (["--build-info"], ["--verify-release"]):
    import json
    from pathlib import Path

    from release_policy import runtime_info, verify_manifest

    info = verify_manifest(Path(sys._MEIPASS).parent) if sys.argv[1] == "--verify-release" else runtime_info()
    print(json.dumps(info))
    raise SystemExit(0)
