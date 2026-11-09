"""Jenkins 候选镜像门禁、Compose 镜像锁定及部署后只读验收。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid


HERE = Path(__file__).resolve().parent
NODE_CHECK = r"""
const v = process.versions.node;
if (!/^\d+\.\d+\.\d+$/.test(v)) process.exit(1);
const [major, minor, patch] = v.split('.').map(Number);
const minimum = {22: [23, 4], 24: [22, 1]}[major];
if (!minimum || minor < minimum[0] ||
    (minor === minimum[0] && patch < minimum[1])) process.exit(1);
console.log('Node.js ' + v + '; Brotli ' + process.versions.brotli);
"""
IMAGE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}")
SERVICE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")


def run(args, *, stdin=None):
    # 不输出 Docker/Compose 的错误正文，避免配置或应用内容进入流水线日志。
    result = subprocess.run(args, input=stdin, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(f"{args[0]} 命令失败，退出码 {result.returncode}")
    return result.stdout.strip()


def load_manifest(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("清单必须为 JSON 对象")
    services = data.get("services", {})
    if not isinstance(services, dict) or not 1 <= len(services) <= 32:
        raise ValueError("清单须包含 1 至 32 个 services")
    for name, item in services.items():
        if not SERVICE.fullmatch(name) or not isinstance(item, dict):
            raise ValueError("无效的服务项")
        if not isinstance(item.get("image"), str) or not IMAGE.fullmatch(item["image"]):
            raise ValueError(f"{name}: 必须使用仓库@sha256 摘要")
        if item.get("profile") not in {"node", "system", "node-system"}:
            raise ValueError(f"{name}: 无效的检查 profile")
    return services


def check(profile, *, image=None, container=None):
    if image:
        prefix = ["docker", "run", "--interactive", "--rm", "--pull=never", "--network=none", "--read-only",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1",
                  "--memory=128m", "--pids-limit=64", "--ulimit", "fsize=1048576"]
        def execute(executable, args, stdin=None):
            name = "bklite-brotli-check-" + uuid.uuid4().hex
            try:
                return run([*prefix, "--name", name, "--entrypoint", executable, image, *args], stdin=stdin)
            finally:
                # Docker 客户端超时不保证 daemon 中的容器退出，只清理本次唯一名称。
                try:
                    run(["docker", "rm", "--force", name])
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    pass
    else:
        def execute(executable, args, stdin=None):
            return run(["docker", "exec", "-i", container, executable, *args], stdin=stdin)
    if profile in {"node", "node-system"}:
        print(execute("node", ["--eval", NODE_CHECK]))
    if profile in {"system", "node-system"}:
        print(execute("sh", ["-s"], HERE.joinpath("check_brotli_system.sh").read_text()))


def prepare(services, output):
    # 失败时不生成半份清单；已有产物不覆盖，避免失败后误用旧清单。
    if Path(output).exists():
        raise ValueError("输出文件已存在，请使用本次构建的独立目录")
    for name, item in services.items():
        print(f"检查候选镜像：{name}")
        check(item["profile"], image=item["image"])
    with Path(output).open("x") as stream:
        json.dump({"services": {name: {"image": item["image"]}
                                for name, item in services.items()}}, stream, indent=2)
        stream.write("\n")


def verify(services, project, files, env_files=(), profiles=()):
    prefix = ["docker", "compose", "--project-name", project]
    for file in files:
        prefix.extend(["-f", file])
    for env_file in env_files:
        prefix.extend(["--env-file", env_file])
    for profile in profiles:
        prefix.extend(["--profile", profile])
    # 验证所有副本；停止、缺失、仍使用旧镜像都失败。仅读取 Image/Running 字段。
    for name, item in services.items():
        expected = run(["docker", "image", "inspect", "--format", "{{.Id}}", item["image"]])
        containers = run([*prefix, "ps", "--all", "--quiet", name]).splitlines()
        if not containers:
            raise ValueError(f"{name}: 未发现运行容器")
        for container in containers:
            state = run(["docker", "inspect", "--format", "{{.Image}} {{.State.Running}}", container])
            if state != f"{expected} true":
                raise ValueError(f"{name}: 未运行或仍使用非目标镜像")
            print(f"检查运行容器：{name}")
            check(item["profile"], container=container)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    image = sub.add_parser("check-image")
    image.add_argument("--image", required=True)
    image.add_argument("--profile", choices=["node", "system", "node-system"], required=True)
    lock = sub.add_parser("prepare")
    lock.add_argument("--manifest", required=True)
    lock.add_argument("--output", required=True)
    deployed = sub.add_parser("verify")
    deployed.add_argument("--manifest", required=True)
    deployed.add_argument("--project", required=True)
    deployed.add_argument("-f", "--file", action="append", required=True)
    deployed.add_argument("--env-file", action="append", default=[])
    deployed.add_argument("--profile", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.action == "check-image":
            check(args.profile, image=args.image)
        elif args.action == "prepare":
            prepare(load_manifest(args.manifest), args.output)
        else:
            verify(load_manifest(args.manifest), args.project, args.file, args.env_file, args.profile)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.exit(1, "Brotli 发行验收失败；请核对镜像、版本、清单及 Docker 状态\n")


if __name__ == "__main__":
    main()
