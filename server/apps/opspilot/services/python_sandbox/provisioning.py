"""Stream a skill package to Docker in one bounded archive, including binary assets."""
import io
import posixpath
import tarfile
import tempfile
import uuid

from deepagents.backends.protocol import FileUploadResponse, WriteResult

from apps.opspilot.services.skill_package.materializer import materialize_skill_package

from .runtime import SandboxUnavailable


class _ArchiveWriter:
    def __init__(self, archive, prefix):
        self.archive = archive
        self.prefix = prefix
        self.size = 0
        self.count = 0
        self.failed = False
        self.directories = set()

    def write(self, path, content):
        self.upload_files([(path, content.encode("utf-8"))])
        return WriteResult(path=path)

    def upload_files(self, files):
        results = []
        for path, data in files:
            if not path.startswith("/workspace/skills/") or posixpath.normpath(path) != path:
                self.failed = True
                raise ValueError("Invalid skill path")
            self.size += len(data)
            self.count += 1
            if len(data) > 16 * 1024 * 1024 or self.size > 128 * 1024 * 1024 or self.count > 20000:
                self.failed = True
                raise ValueError("Skill package exceeds transfer limits")
            archive_path = self.prefix + "/" + path.removeprefix("/workspace/")
            parts = archive_path.split("/")
            for index in range(1, len(parts)):
                directory = "/".join(parts[:index])
                if directory not in self.directories:
                    info = tarfile.TarInfo(directory)
                    info.type = tarfile.DIRTYPE
                    info.uid = info.gid = 65534
                    info.mode = 0o755
                    self.archive.addfile(info)
                    self.directories.add(directory)
            info = tarfile.TarInfo(archive_path)
            info.size = len(data)
            info.uid = info.gid = 65534
            info.mode = 0o755
            self.archive.addfile(info, io.BytesIO(data))
            results.append(FileUploadResponse(path=path))
        return results

    def chmod(self, path, mode):
        # Skill resources are already executable, without any host path exposure.
        return None


def materialize_container_skill(package, sandbox):
    prefix = "opspilot-skill-" + uuid.uuid4().hex
    with tempfile.TemporaryFile() as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            writer = _ArchiveWriter(archive, prefix)
            paths = materialize_skill_package(package, writer, skills_root="/workspace/skills")
            if writer.failed:
                raise SandboxUnavailable("技能包传输失败")
        stream.seek(0)
        with sandbox._lock:
            container = sandbox._ensure_container()
            if not container.put_archive("/var/tmp", stream):
                raise SandboxUnavailable("技能包传输失败")
            # /var/tmp is the container layer; Docker archive extraction into tmpfs
            # is not reliable. Copy into the visible workspace from inside Docker.
            script = "import shutil,sys; p=sys.argv[1]; " "shutil.copytree(p+'/skills','/workspace/skills',dirs_exist_ok=True); shutil.rmtree(p)"
            result = container.exec_run(["python", "-c", script, "/var/tmp/" + prefix])
            if result.exit_code:
                raise SandboxUnavailable("技能包安装失败")
    return paths
