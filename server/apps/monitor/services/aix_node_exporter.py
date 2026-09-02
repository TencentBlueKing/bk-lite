import re
import shlex
from urllib.parse import unquote

from django.db import transaction

from apps.core.logger import monitor_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.monitor.constants.aix_node_exporter import (
    BINARY_NAME,
    COLLECT_TYPE,
    CONFIG_TYPE,
    DEFAULT_SCRAPE_PORT,
    DEFAULT_USERNAME,
    EXTRACTED_DIR_NAME,
    INSTALL_DIR,
    LISTEN_ADDRESS,
    PACKAGE_ARCH,
    PACKAGE_NAME,
    PACKAGE_OBJECT,
    PACKAGE_OS,
    PACKAGE_SHA256,
    PACKAGE_VERSION,
    PLUGIN_NAME,
    REMOTE_PACKAGE_DIR,
    SRC_NAME,
    SSH_PORT,
    VENDOR_FILE_PATH,
)
from apps.monitor.models import CollectConfig
from apps.node_mgmt.models import PackageVersion
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils.installer import download_to_remote, exec_command_to_remote
from apps.rpc.node_mgmt import NodeMgmt
from config.components.nats import NATS_NAMESPACE

_PASSWORD_KEY = "password"
_INTERVAL_RE = re.compile(r'interval\s*=\s*"(\d+)s"', re.IGNORECASE)
_URLS_RE = re.compile(r"urls\s*=\s*\[(.*?)\]", re.IGNORECASE | re.DOTALL)


class AixNodeExporterError(Exception):
    def __init__(self, message, *, failed_stage, error_type="AixNodeExporterError"):
        super().__init__(message)
        self.failed_stage = failed_stage
        self.error_type = error_type


class AixNodeExporterService:
    @staticmethod
    def is_host_aix_plugin(plugin):
        return bool(plugin) and plugin.name == PLUGIN_NAME

    @staticmethod
    def is_aix_child_config(collect_type, config_type):
        return collect_type == COLLECT_TYPE and config_type == CONFIG_TYPE

    @staticmethod
    def wrap_ksh(script):
        return f"/usr/bin/ksh -c {shlex.quote(script)}"

    @classmethod
    def resolve_vendor_file_path(cls):
        package = PackageVersion.objects.filter(
            os=PACKAGE_OS,
            cpu_architecture=PACKAGE_ARCH,
            object=PACKAGE_OBJECT,
            version=PACKAGE_VERSION,
        ).first()
        if package is None:
            logger.warning(
                "event=aix_node_exporter_package_row_missing os=%s arch=%s object=%s version=%s fallback_path=%s",
                PACKAGE_OS,
                PACKAGE_ARCH,
                PACKAGE_OBJECT,
                PACKAGE_VERSION,
                VENDOR_FILE_PATH,
            )
            return VENDOR_FILE_PATH
        try:
            return PackageService.resolve_existing_file_path(package)
        except Exception as exc:
            logger.warning(
                "event=aix_node_exporter_package_path_fallback failed_stage=resolve_package error_type=%s fallback_path=%s",
                type(exc).__name__,
                VENDOR_FILE_PATH,
            )
            return VENDOR_FILE_PATH

    @classmethod
    def build_install_script(cls, *, scrape_port=DEFAULT_SCRAPE_PORT, skip_copy=False):
        listen = f"{LISTEN_ADDRESS}:{int(scrape_port or DEFAULT_SCRAPE_PORT)}"
        package_path = f"{REMOTE_PACKAGE_DIR}/{PACKAGE_NAME}"
        binary_path = f"{INSTALL_DIR}/{BINARY_NAME}"
        extracted_binary = f"{REMOTE_PACKAGE_DIR}/{EXTRACTED_DIR_NAME}/{BINARY_NAME}"
        if skip_copy:
            return "\n".join(
                [
                    "set -e",
                    f'if [ ! -x "{binary_path}" ]; then',
                    '  echo "node_exporter binary missing" >&2',
                    "  exit 1",
                    "fi",
                    cls._src_start_block(binary_path, listen),
                ]
            )
        return "\n".join(
            [
                "set -e",
                cls._sha256_verify_block(package_path),
                f'mkdir -p "{INSTALL_DIR}"',
                f'gzip -dc "{package_path}" | (cd "{REMOTE_PACKAGE_DIR}" && tar -xf -)',
                f'if [ ! -f "{extracted_binary}" ]; then',
                '  echo "extracted binary missing" >&2',
                "  exit 1",
                "fi",
                cls._src_replace_block(extracted_binary, binary_path, listen),
            ]
        )

    @staticmethod
    def _sha256_verify_block(package_path):
        return "\n".join(
            [
                f'if [ ! -f "{package_path}" ]; then',
                '  echo "package missing" >&2',
                "  exit 1",
                "fi",
                'actual=""',
                "if command -v openssl >/dev/null 2>&1; then",
                f"  actual=$(openssl dgst -sha256 \"{package_path}\" | awk '{{print $NF}}')",
                "elif command -v csum >/dev/null 2>&1; then",
                f"  actual=$(csum -h SHA256 \"{package_path}\" | awk '{{print $1}}')",
                "else",
                '  echo "sha256 tool missing" >&2',
                "  exit 1",
                "fi",
                f'if [ "$actual" != "{PACKAGE_SHA256}" ]; then',
                '  echo "package checksum mismatch" >&2',
                "  exit 1",
                "fi",
            ]
        )

    @staticmethod
    def _src_replace_block(extracted_binary, binary_path, listen):
        return "\n".join(
            [
                f'if lssrc -s "{SRC_NAME}" >/dev/null 2>&1; then',
                f'  stopsrc -s "{SRC_NAME}" >/dev/null 2>&1 || true',
                f'  cp "{extracted_binary}" "{binary_path}"',
                f'  chmod 755 "{binary_path}"',
                f'  chssys -s "{SRC_NAME}" -a "--web.listen-address={listen}" >/dev/null 2>&1 || true',
                "else",
                f'  cp "{extracted_binary}" "{binary_path}"',
                f'  chmod 755 "{binary_path}"',
                f'  mkssys -s "{SRC_NAME}" -p "{binary_path}" -u 0 -a "--web.listen-address={listen}" -S -n 15 -f 9 -R',
                "fi",
                AixNodeExporterService._src_start_block(binary_path, listen),
            ]
        )

    @staticmethod
    def _src_start_block(binary_path, listen):
        return "\n".join(
            [
                f'if lssrc -s "{SRC_NAME}" >/dev/null 2>&1; then',
                f'  startsrc -s "{SRC_NAME}" >/dev/null 2>&1 || true',
                "else",
                f'  mkssys -s "{SRC_NAME}" -p "{binary_path}" -u 0 -a "--web.listen-address={listen}" -S -n 15 -f 9 -R',
                f'  startsrc -s "{SRC_NAME}"',
                "fi",
                f"state=$(lssrc -s \"{SRC_NAME}\" | awk 'NR>1 {{print $NF}}')",
                'if [ "$state" != "active" ]; then',
                '  echo "src not active" >&2',
                "  exit 1",
                "fi",
            ]
        )

    @classmethod
    def copy_package(cls, *, node_id, host, username, password, private_key, passphrase):
        file_key = cls.resolve_vendor_file_path()
        result = download_to_remote(
            node_id,
            NATS_NAMESPACE,
            file_key,
            PACKAGE_NAME,
            REMOTE_PACKAGE_DIR,
            host,
            username,
            password,
            port=SSH_PORT,
            private_key=private_key,
            passphrase=passphrase,
        )
        if not _executor_ok(result):
            raise AixNodeExporterError(
                "copy node_exporter package failed",
                failed_stage="copy",
                error_type="CopyFailed",
            )
        return result

    @classmethod
    def start_exporter(cls, *, node_id, host, username, password, private_key, passphrase, scrape_port, skip_copy=False):
        command = cls.wrap_ksh(cls.build_install_script(scrape_port=scrape_port, skip_copy=skip_copy))
        result = exec_command_to_remote(
            node_id,
            host,
            username,
            password,
            command,
            port=SSH_PORT,
            private_key=private_key,
            passphrase=passphrase,
        )
        if not _executor_ok(result):
            raise AixNodeExporterError(
                "start node_exporter failed",
                failed_stage="start",
                error_type="StartFailed",
            )
        return result

    @classmethod
    def install(cls, *, node_id, host, username, password, private_key, passphrase, scrape_port, skip_copy=False):
        if not skip_copy:
            logger.info("event=aix_node_exporter_copy_started node_id=%s instance_host=%s", node_id, host)
            cls.copy_package(
                node_id=node_id,
                host=host,
                username=username,
                password=password,
                private_key=private_key,
                passphrase=passphrase,
            )
        logger.info(
            "event=aix_node_exporter_start_started node_id=%s instance_host=%s skip_copy=%s",
            node_id,
            host,
            skip_copy,
        )
        return cls.start_exporter(
            node_id=node_id,
            host=host,
            username=username,
            password=password,
            private_key=private_key,
            passphrase=passphrase,
            scrape_port=scrape_port,
            skip_copy=skip_copy,
        )

    @classmethod
    def persist_install_env(cls, child_config_id, instance):
        if not child_config_id:
            return
        updates = {}
        username = instance.get("username") or DEFAULT_USERNAME
        updates[f"USERNAME__{str(child_config_id).upper()}"] = username
        node_ids = instance.get("node_ids") or []
        if node_ids:
            updates[f"NODE_ID__{str(child_config_id).upper()}"] = node_ids[0]
        if instance.get("node_id"):
            updates[f"NODE_ID__{str(child_config_id).upper()}"] = instance["node_id"]
        auth_type = instance.get("auth_type")
        if auth_type:
            updates[f"AUTH_TYPE__{str(child_config_id).upper()}"] = auth_type
        private_key = instance.get("private_key_content")
        if private_key:
            updates[f"PRIVATE_KEY_CONTENT__{str(child_config_id).upper()}"] = private_key
        passphrase = instance.get("private_key_passphrase")
        if passphrase:
            updates[f"PRIVATE_KEY_PASSPHRASE__{str(child_config_id).upper()}"] = passphrase
        rows = NodeMgmt().get_child_configs_by_ids([child_config_id])
        if not rows:
            logger.warning(
                "event=aix_node_exporter_env_persist_skipped child_config_id=%s failed_stage=persist_env error_type=ChildConfigMissing",
                child_config_id,
            )
            return
        current = dict(rows[0].get("env_config") or {})
        current.update(updates)
        NodeMgmt().update_child_config_content(child_config_id, None, current)

    @classmethod
    def load_credentials(cls, env_config, config_id, instance=None):
        instance = instance or {}
        username = instance.get("username") or DEFAULT_USERNAME
        password = _first_present(instance.get("ENV_PASSWORD"), instance.get("password"))
        private_key = instance.get("private_key_content")
        passphrase = instance.get("private_key_passphrase")
        suffix = f"__{str(config_id).upper()}"
        aes = AESCryptor()
        for key, value in (env_config or {}).items():
            if value in (None, ""):
                continue
            key_upper = str(key).upper()
            if not key_upper.endswith(suffix):
                continue
            base = key_upper[: -len(suffix)]
            if base == "USERNAME":
                username = value
            elif base == "PASSWORD":
                decoded = _try_decode_password(aes, value)
                if decoded is not None:
                    password = decoded
                elif password:
                    continue
                else:
                    raise AixNodeExporterError(
                        "decode password failed",
                        failed_stage="load_credentials",
                        error_type="PasswordDecodeFailed",
                    )
            elif base == "PRIVATE_KEY_CONTENT":
                private_key = _unquote_plain(value)
            elif base == "PRIVATE_KEY_PASSPHRASE":
                passphrase = _unquote_plain(value)
        if password:
            password = _unquote_plain(password)
        if private_key:
            private_key = _unquote_plain(private_key)
        if passphrase:
            passphrase = _unquote_plain(passphrase)
        return {
            "username": username or DEFAULT_USERNAME,
            "password": password,
            "private_key": private_key,
            "passphrase": passphrase,
        }

    @classmethod
    def maybe_schedule_after_create(cls, plugin, data):
        if not cls.is_host_aix_plugin(plugin):
            return
        cls.schedule_after_create(data)

    @classmethod
    def capture_previous_child_content(cls, config_obj, child_info):
        if not cls.is_aix_child_config(config_obj.collect_type, config_obj.config_type):
            return ""
        existing_child = NodeMgmt().get_child_configs_by_ids([child_info["id"]])
        return (existing_child[0].get("content") if existing_child else "") or ""

    @classmethod
    def maybe_schedule_after_update(cls, config_obj, child_info, previous_content):
        if not cls.is_aix_child_config(config_obj.collect_type, config_obj.config_type):
            return
        cls.schedule_after_update(config_obj, child_info, previous_content)

    @classmethod
    def schedule_after_create(cls, data):
        instances = data.get("instances") or []
        form_defaults = (data.get("configs") or [{}])[0]
        instance_ids = [str(item.get("instance_id")) for item in instances if item.get("instance_id")]
        if not instance_ids:
            return
        rows = list(
            CollectConfig.objects.filter(
                monitor_instance_id__in=instance_ids,
                collect_type=COLLECT_TYPE,
                config_type=CONFIG_TYPE,
                is_child=True,
            ).values("id", "monitor_instance_id")
        )
        config_by_instance = {row["monitor_instance_id"]: row["id"] for row in rows}
        for instance in instances:
            merged = {**form_defaults, **instance}
            instance_id = str(merged.get("instance_id") or "")
            child_config_id = config_by_instance.get(instance_id)
            if not child_config_id:
                logger.warning(
                    "event=aix_node_exporter_schedule_skipped instance_id=%s failed_stage=schedule error_type=ChildConfigMissing",
                    instance_id,
                )
                continue
            cls.persist_install_env(child_config_id, merged)
            node_ids = merged.get("node_ids") or []
            node_id = node_ids[0] if node_ids else ""
            cls._on_commit_install(
                child_config_id=child_config_id,
                instance_id=instance_id,
                node_id=node_id,
                host=merged.get("host"),
                scrape_port=merged.get("port") or DEFAULT_SCRAPE_PORT,
                username=merged.get("username") or DEFAULT_USERNAME,
                skip_copy=False,
            )

    @classmethod
    def schedule_after_update(cls, config_obj, child_info, previous_content):
        instance = {
            "username": _env_value(child_info.get("env_config"), "USERNAME", config_obj.id),
            "auth_type": _env_value(child_info.get("env_config"), "AUTH_TYPE", config_obj.id),
            "private_key_content": _env_value(child_info.get("env_config"), "PRIVATE_KEY_CONTENT", config_obj.id),
            "private_key_passphrase": _env_value(child_info.get("env_config"), "PRIVATE_KEY_PASSPHRASE", config_obj.id),
        }
        new_content = child_info.get("content") if isinstance(child_info.get("content"), str) else ""
        host, scrape_port = _host_port_from_child({}, new_content or previous_content)
        skip_copy = _is_interval_only_change(previous_content or "", new_content, {})
        cls.persist_install_env(config_obj.id, instance)
        rows = NodeMgmt().get_child_configs_by_ids([config_obj.id])
        persisted_env = (rows[0].get("env_config") if rows else {}) or {}
        node_id = _env_value(persisted_env, "NODE_ID", config_obj.id) or ""
        cls._on_commit_install(
            child_config_id=config_obj.id,
            instance_id=config_obj.monitor_instance_id,
            node_id=node_id,
            host=host,
            scrape_port=scrape_port,
            username=instance.get("username") or DEFAULT_USERNAME,
            skip_copy=skip_copy,
        )

    @staticmethod
    def _on_commit_install(*, child_config_id, instance_id, node_id, host, scrape_port, username, skip_copy):
        from apps.monitor.tasks.aix_node_exporter import install_aix_node_exporter

        def _enqueue():
            install_aix_node_exporter.delay(
                child_config_id=child_config_id,
                instance_id=instance_id,
                node_id=node_id,
                host=host,
                scrape_port=scrape_port,
                username=username,
                skip_copy=skip_copy,
            )

        transaction.on_commit(_enqueue)
        logger.info(
            "event=aix_node_exporter_install_scheduled child_config_id=%s instance_id=%s node_id=%s skip_copy=%s",
            child_config_id,
            instance_id,
            node_id,
            skip_copy,
        )


def _executor_ok(result):
    if not isinstance(result, dict):
        return False
    if result.get("success") is True:
        return True
    exit_code = result.get("exit_code")
    try:
        return int(exit_code) == 0
    except (TypeError, ValueError):
        return False


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _unquote_plain(value):
    text = str(value)
    try:
        return unquote(text)
    except Exception:
        return text


def _try_decode_password(aes, value):
    try:
        return aes.decode(str(value))
    except Exception:
        return None


def _env_value(env_config, prefix, config_id):
    if not env_config:
        return None
    key = f"{prefix}__{str(config_id).upper()}"
    return env_config.get(key)


def _host_port_from_child(config, previous_content):
    urls = config.get("urls") if isinstance(config, dict) else None
    url = ""
    if isinstance(urls, list) and urls:
        url = str(urls[0])
    elif previous_content:
        match = _URLS_RE.search(previous_content)
        if match:
            url = match.group(1).strip().strip('"').strip("'")
    host = ""
    port = DEFAULT_SCRAPE_PORT
    parsed = re.match(r"^https?://([^:/]+):?(\d+)?", url)
    if parsed:
        host = parsed.group(1)
        if parsed.group(2):
            port = int(parsed.group(2))
    if isinstance(config, dict) and config.get("host"):
        host = config.get("host")
    return host, port


def _is_interval_only_change(previous_content, new_content, config):
    old_urls = _URLS_RE.search(previous_content or "")
    new_urls = _URLS_RE.search(new_content or "")
    old_interval = _INTERVAL_RE.search(previous_content or "")
    new_interval = _INTERVAL_RE.search(new_content or "")
    if isinstance(config, dict) and config.get("interval"):
        new_interval_value = str(config.get("interval")).rstrip("s")
    else:
        new_interval_value = new_interval.group(1) if new_interval else ""
    old_url = old_urls.group(1).strip() if old_urls else ""
    new_url = new_urls.group(1).strip() if new_urls else old_url
    old_interval_value = old_interval.group(1) if old_interval else ""
    return bool(old_url and new_url == old_url and old_interval_value and new_interval_value != old_interval_value)
