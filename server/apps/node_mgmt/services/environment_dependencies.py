"""Validate the management dependency before issuing an environment package."""
import hashlib
import tempfile
import zipfile

from apps.node_mgmt.models import Collector
from apps.node_mgmt.services.package import PackageService

EXECUTOR_NAME = "NATS-Executor"
EXECUTOR_ARCHIVE_PATH = "fusion-collectors/bin/nats-executor"
MAX_CONTROLLER_ARCHIVE_BYTES = 2 * 1024**3
MAX_INSTALL_SCRIPT_BYTES = 1024 * 1024
MAX_EXECUTOR_BYTES = 256 * 1024**2


def validate_executor_dependency(package, env):
    """Return the required collector ID; never issue a grant on invalid material."""
    if env.get("SIDECAR_INPUT_MODE", "nats") != "nats":
        raise ValueError("NATS Executor requires the nats input mode")
    if not env.get("NATS_ADMIN_USERNAME") or not env.get("NATS_ADMIN_PASSWORD"):
        raise ValueError("NATS Executor runtime credentials are missing from the cloud region")
    if env["NATS_ADMIN_USERNAME"] == env.get("NATS_INSTALLER_USERNAME"):
        raise ValueError("NATS Executor must not use the download-only installer account")
    executor = Collector.objects.filter(
        name=EXECUTOR_NAME,
        node_operating_system="linux",
        cpu_architecture="x86_64",
        controller_default_run=True,
        executable_path="/opt/fusion-collectors/bin/nats-executor",
    ).first()
    if not executor or not isinstance(executor.default_config, dict) or not executor.default_config.get("nats"):
        raise ValueError("NATS Executor definition and default configuration are required")
    # Stream to bounded temporary storage, then inspect the actual signed-by-hash
    # controller material. A separate collector package does not bootstrap RPC.
    stream, _ = PackageService.download_file_streaming(package)
    try:
        with tempfile.TemporaryFile() as material:
            digest = hashlib.sha256()
            size = 0
            for chunk in stream:
                size += len(chunk)
                if size > MAX_CONTROLLER_ARCHIVE_BYTES:
                    raise ValueError("Controller archive exceeds the dependency inspection limit")
                digest.update(chunk)
                material.write(chunk)
            if digest.hexdigest() != package.sha256:
                raise ValueError("Controller archive digest differs from the published package")
            material.seek(0)
            try:
                with zipfile.ZipFile(material) as archive:
                    scripts = [entry for entry in archive.infolist() if entry.filename == "fusion-collectors/install.sh"]
                    if len(scripts) != 1 or not 0 < scripts[0].file_size <= MAX_INSTALL_SCRIPT_BYTES:
                        raise ValueError("Controller package does not support environment installation")
                    with archive.open(scripts[0]) as script:
                        content = script.read(MAX_INSTALL_SCRIPT_BYTES + 1)
                    if len(content) > MAX_INSTALL_SCRIPT_BYTES or b"BK_LITE_CONFIG_PREPARED" not in content:
                        raise ValueError("Controller package does not support environment installation")
                    entries = [entry for entry in archive.infolist() if entry.filename == EXECUTOR_ARCHIVE_PATH]
                    if len(entries) != 1 or not 20 <= entries[0].file_size <= MAX_EXECUTOR_BYTES:
                        raise ValueError("Controller package must contain one NATS Executor binary")
                    with archive.open(entries[0]) as binary:
                        header = binary.read(20)
                    if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
                        raise ValueError("NATS Executor must be a Linux x86_64 executable")
            except (zipfile.BadZipFile, RuntimeError) as error:
                raise ValueError("Unable to inspect the controller package NATS Executor") from error
    finally:
        close = getattr(stream, "close", None)
        if close:
            close()
    return executor.id
