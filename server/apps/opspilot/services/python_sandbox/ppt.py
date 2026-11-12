"""Copy bounded PPT artifacts for trusted validation/publishing; execute in the local task workspace."""
import json
import shlex
from pathlib import Path

from .runtime import SandboxUnavailable


def sync_ppt_workspace(sandbox, workspace):
    ppt_root = sandbox.workspace + "/ppt-workspace"
    script = (
        "import json, pathlib\nroot = pathlib.Path("
        + repr(ppt_root)
        + ")\n"
        + """
files = []
total = 0
for path in root.rglob('*'):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        continue
    size = path.stat().st_size
    total += size
    if size > 16777216 or total > 67108864 or len(files) >= 1000:
        raise ValueError('PPT workspace exceeds transfer limit')
    files.append(path.relative_to(root).as_posix())
print(json.dumps(files))
"""
    )
    result = sandbox.execute_command("python -c " + shlex.quote(script))
    if result.exit_code or result.truncated:
        raise SandboxUnavailable("PPT 产物同步失败")
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for relative in json.loads(result.output):
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or target == root:
            raise SandboxUnavailable("PPT 产物路径无效")
        content = sandbox.read_workspace_file(ppt_root + "/" + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def export_ppt(sandbox, workspace, project):
    # Transfer the platform's repaired SVG and matching validation fingerprint.
    workspace = Path(workspace)
    ppt_root = sandbox.workspace + "/ppt-workspace/"
    for broken in workspace.rglob("*.svg.broken"):
        original = ppt_root + broken.relative_to(workspace).with_suffix("").as_posix()
        result = sandbox.execute_command("rm -f -- " + shlex.quote(original))
        if result.exit_code:
            return False
    paths = list(workspace.rglob("*.svg")) + list(workspace.glob("**/validation/svg_quality_report.json"))
    for path in paths:
        if path.is_file() and not path.is_symlink():
            sandbox.write_workspace_file(ppt_root + path.relative_to(workspace).as_posix(), path.read_bytes())
    relative = project.relative_to(workspace).as_posix()
    command = (
        "cd "
        + shlex.quote(ppt_root)
        + " && python "
        + shlex.quote(sandbox.workspace + "/skills/ppt-master/scripts/svg_to_pptx.py")
        + " "
        + shlex.quote(relative)
        + " --quick-generate"
    )
    result = sandbox.execute_command(command, timeout=180)
    if result.exit_code:
        return False
    sync_ppt_workspace(sandbox, workspace)
    return True
