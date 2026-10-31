"""构建期替换已核对的 Log4j 依赖；不启动应用或修改业务数据。"""

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile


MANIFEST = Path(__file__).with_name("log4j-artifacts.json")
MAX_JAR = 16 * 1024 * 1024
ALLOWED_OLD = {"2.17.1", "2.25.4", "2.25.5"}


def coordinate(data):
    with zipfile.ZipFile(io.BytesIO(data)) as jar:
        found = []
        for name in jar.namelist():
            if name.startswith("META-INF/maven/org.apache.logging.log4j/") and name.endswith("/pom.properties"):
                info = jar.getinfo(name)
                if info.file_size > 8192:
                    raise ValueError("Log4j metadata too large")
                props = dict(line.split("=", 1) for line in jar.read(name).decode().splitlines() if "=" in line and not line.startswith("#"))
                if props.get("groupId") == "org.apache.logging.log4j":
                    found.append((props["artifactId"], props["version"]))
        if len(found) != 1:
            raise ValueError("Expected one Log4j Maven coordinate")
        return found[0]


def artifacts(directory, manifest):
    result = {}
    for name, expected in manifest["artifacts"].items():
        path = directory / f"{name}-{manifest['version']}.jar"
        if path.stat().st_size > MAX_JAR:
            raise ValueError("Log4j artifact too large")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {name}")
        if coordinate(data) != (name, manifest["version"]):
            raise ValueError(f"Artifact metadata mismatch: {name}")
        result[name] = data
    return result


def fetch(directory, manifest):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest["artifacts"].items():
        filename = f"{name}-{manifest['version']}.jar"
        url = f"https://repo.maven.apache.org/maven2/org/apache/logging/log4j/{name}/{manifest['version']}/{filename}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(MAX_JAR + 1)
        if len(data) > MAX_JAR or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"Artifact checksum/size mismatch: {name}")
        (directory / filename).write_bytes(data)
    artifacts(directory, manifest)


def replacement(data, available):
    name, version = coordinate(data)
    if name not in available or version not in ALLOWED_OLD:
        raise ValueError(f"Unreviewed Log4j dependency: {name}/{version}")
    return name, available[name]


def patch_conductor(source, output, available, version):
    if output.exists() or output.is_symlink():
        raise ValueError("Output must not exist; in-place JAR editing is forbidden")
    if source.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("Conductor JAR too large")
    with zipfile.ZipFile(source) as jar:
        items = jar.infolist()
        names = [item.filename for item in items]
        if len(items) > 100000 or len(set(names)) != len(names) or sum(i.file_size for i in items) > 2 * 1024**3:
            raise ValueError("Invalid/oversized Conductor archive")
        signatures = [i for i in items if i.filename.upper().startswith("META-INF/")
                      and i.filename.upper().endswith((".SF", ".RSA", ".DSA", ".EC"))]
        # Spring Boot 的空 BOOT.SF 是标记文件，没有签名内容；真实签名仍要求上游重建。
        if any(not (i.filename == "META-INF/BOOT.SF" and i.file_size == 0) for i in signatures):
            raise ValueError("Signed outer JAR requires an upstream rebuild")
        updates, seen = {}, set()
        for item in items:
            name = Path(item.filename).name
            if not (name.startswith("log4j-") and name.endswith(".jar")):
                continue
            if item.file_size > MAX_JAR:
                raise ValueError("Nested Log4j JAR too large")
            module, data = replacement(jar.read(item), available)
            if module in seen:
                raise ValueError("Duplicate Log4j module")
            seen.add(module)
            updates[item.filename] = (str(Path(item.filename).with_name(f"{module}-{version}.jar")), data)
        if not {"log4j-api", "log4j-core"} <= seen:
            raise ValueError("Conductor Log4j API/core not found")
        if len(set(names) | {value[0] for value in updates.values()}) != len(names) + sum(old != new for old, (new, _) in updates.items()):
            raise ValueError("Log4j destination collision")
        with zipfile.ZipFile(output, "w") as patched:
            for item in items:
                info = copy.copy(item)
                if item.filename in updates:
                    info.filename, data = updates[item.filename]
                    info.compress_type = zipfile.ZIP_STORED
                    patched.writestr(info, data)
                elif item.filename in {"BOOT-INF/classpath.idx", "BOOT-INF/layers.idx", "META-INF/MANIFEST.MF"}:
                    if item.file_size > 1024 * 1024:
                        raise ValueError("Classpath metadata too large")
                    data = jar.read(item)
                    for old, (new, _) in updates.items():
                        data = data.replace(old.encode(), new.encode())
                    patched.writestr(info, data)
                else:
                    with jar.open(item) as reader, patched.open(info, "w") as writer:
                        shutil.copyfileobj(reader, writer, 64 * 1024)
    output.chmod(0o644)


def patch_elasticsearch(source, output, available, version):
    if output.is_symlink() or (output.exists() and any(output.iterdir())):
        raise ValueError("Elasticsearch output must be an empty directory")
    api = source / "log4j-api-2.17.1.jar"
    core = source / "elasticsearch-log4j-7.17.21.jar"
    if api.stat().st_size > MAX_JAR or core.stat().st_size > MAX_JAR:
        raise ValueError("Elasticsearch Log4j JAR too large")
    if coordinate(api.read_bytes()) != ("log4j-api", "2.17.1") or coordinate(core.read_bytes()) != ("log4j-core", "2.17.1"):
        raise ValueError("Unreviewed Elasticsearch Log4j baseline")
    if {p.name for p in source.glob("*log4j*.jar")} != {api.name, core.name}:
        raise ValueError("Additional Elasticsearch Log4j libraries need review")
    output.mkdir(parents=True, exist_ok=True)
    (output / f"log4j-api-{version}.jar").write_bytes(available["log4j-api"])
    # 保留 Elasticsearch 原有安全措施：其自定义 core 包主动删除 JndiLookup。
    with zipfile.ZipFile(io.BytesIO(available["log4j-core"])) as jar, zipfile.ZipFile(output / core.name, "w") as patched:
        for item in jar.infolist():
            if item.filename != "org/apache/logging/log4j/core/lookup/JndiLookup.class":
                patched.writestr(item, jar.read(item))
    for path in output.iterdir():
        path.chmod(0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["fetch", "conductor", "elasticsearch"])
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    if args.mode == "fetch":
        fetch(args.artifacts, manifest)
    else:
        if args.source is None or args.output is None:
            parser.error("--source and --output are required")
        available = artifacts(args.artifacts, manifest)
        function = patch_conductor if args.mode == "conductor" else patch_elasticsearch
        function(args.source, args.output, available, manifest["version"])


if __name__ == "__main__":
    main()
