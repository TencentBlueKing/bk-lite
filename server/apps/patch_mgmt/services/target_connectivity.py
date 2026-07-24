"""使用 SSH/WinRM 凭据执行协议级目标机连通性探测。"""

import io
import logging
from dataclasses import dataclass

from apps.core.mixinx import EncryptMixin
from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import PatchTarget

logger = logging.getLogger("app")

PROBE_TIMEOUT = 5  # 秒


@dataclass(frozen=True)
class TargetProbeResult:
    reachable: bool
    port: int
    detail: str


def probe_target(target: PatchTarget) -> TargetProbeResult:
    """使用目标中已保存的凭据执行协议级连通性测试。"""
    return probe_target_data(target_connection_data(target))


def target_connection_data(target: PatchTarget) -> dict:
    """将已保存目标转换为可探测的明文连接参数，仅供进程内即时使用。"""
    data = {
        "ip": target.ip,
        "os_type": target.os_type,
        "ssh_port": target.ssh_port,
        "ssh_user": target.ssh_user,
        "ssh_credential_type": target.ssh_credential_type,
        "ssh_password": target.ssh_password,
        "ssh_key_passphrase": target.ssh_key_passphrase,
        "winrm_port": target.winrm_port,
        "winrm_scheme": target.winrm_scheme,
        "winrm_transport": target.winrm_transport,
        "winrm_user": target.winrm_user,
        "winrm_password": target.winrm_password,
        "winrm_cert_validation": target.winrm_cert_validation,
    }
    for field in ("ssh_password", "ssh_key_passphrase", "winrm_password"):
        EncryptMixin.decrypt_field(field, data)
    if target.ssh_key_file:
        try:
            with target.ssh_key_file.open("rb") as key_file:
                data["ssh_key_file"] = io.BytesIO(key_file.read())
        except Exception as exc:  # noqa: BLE001
            logger.info("读取目标 %s 的 SSH 私钥失败: %s", target.pk, exc)
            data["ssh_key_file"] = None
    return data


def probe_target_data(data: dict) -> TargetProbeResult:
    """使用表单中的真实凭据执行协议级连通性测试。"""
    port = data.get("winrm_port", 5986) if data.get("os_type") == OSType.WINDOWS else data.get("ssh_port", 22)
    if data.get("os_type") == OSType.WINDOWS:
        return _probe_winrm(data, port)
    return _probe_ssh(data, port)


def _probe_ssh(data: dict, port: int) -> TargetProbeResult:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {
        "hostname": data["ip"],
        "port": port,
        "username": data.get("ssh_user") or None,
        "timeout": PROBE_TIMEOUT,
        "banner_timeout": PROBE_TIMEOUT,
        "auth_timeout": PROBE_TIMEOUT,
        "look_for_keys": False,
        "allow_agent": False,
    }
    if data.get("ssh_credential_type") == "key":
        connect_kwargs["pkey"] = _load_private_key(
            data.get("ssh_key_file"), data.get("ssh_key_passphrase") or None
        )
    else:
        connect_kwargs["password"] = data.get("ssh_password") or None
    try:
        client.connect(**connect_kwargs)
        _, stdout, _ = client.exec_command("printf patch-connectivity-ok", timeout=PROBE_TIMEOUT)
        if stdout.channel.recv_exit_status() != 0:
            raise OSError("SSH 测试命令执行失败")
        return TargetProbeResult(True, port, "SSH 认证成功")
    except Exception as exc:  # noqa: BLE001
        logger.info("SSH connectivity probe failed for %s:%s: %s", data["ip"], port, exc)
        return TargetProbeResult(False, port, f"SSH 认证失败: {exc}")
    finally:
        client.close()


def _probe_winrm(data: dict, port: int) -> TargetProbeResult:
    import winrm

    endpoint = f"{data.get('winrm_scheme') or 'https'}://{data['ip']}:{port}/wsman"
    try:
        session = winrm.Session(
            endpoint,
            auth=(data.get("winrm_user") or "", data.get("winrm_password") or ""),
            transport=data.get("winrm_transport") or "ntlm",
            server_cert_validation=(
                "validate" if data.get("winrm_cert_validation", True) else "ignore"
            ),
            operation_timeout_sec=PROBE_TIMEOUT,
            read_timeout_sec=PROBE_TIMEOUT + 5,
        )
        result = session.run_ps("Write-Output patch-connectivity-ok")
        if result.status_code != 0:
            raise OSError(f"测试命令退出码 {result.status_code}")
        return TargetProbeResult(True, port, "WinRM 认证成功")
    except Exception as exc:  # noqa: BLE001
        logger.info("WinRM connectivity probe failed for %s:%s: %s", data["ip"], port, exc)
        return TargetProbeResult(False, port, f"WinRM 认证失败: {exc}")


def _load_private_key(key_file, passphrase):
    import paramiko

    if not key_file:
        raise ValueError("缺少 SSH 私钥")
    key_file.seek(0)
    raw = key_file.read()
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    errors = []
    key_types = [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey]
    dss_key = getattr(paramiko, "DSSKey", None)
    if dss_key:
        key_types.append(dss_key)
    for key_type in key_types:
        try:
            return key_type.from_private_key(io.StringIO(text), password=passphrase)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    raise ValueError("无法解析 SSH 私钥") from errors[-1]
