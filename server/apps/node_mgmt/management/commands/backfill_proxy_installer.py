import hashlib
import json
import os
from pathlib import Path

from django.core import signing
from django.core.management import BaseCommand, CommandError
from django.db import transaction

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


INSTALLER_KEYS = (NodeConstants.NATS_INSTALLER_USERNAME_KEY, NodeConstants.NATS_INSTALLER_PASSWORD_KEY)
ROLLBACK_SALT = "node-mgmt.proxy-installer-backfill.v1"


def credential_state(row):
    if row is None:
        return None
    fingerprint = hashlib.sha256(json.dumps([row.value, row.type, row.description]).encode()).hexdigest()
    return [row.pk, fingerprint]


def write_rollback_file(path, region_id, before, after):
    snapshot = signing.dumps({"region": region_id, "before": before, "after": after}, salt=ROLLBACK_SALT)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(snapshot)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        raise CommandError("无法保存回退记录。请使用可写安全目录和一个新的文件名；区域变更未提交。") from None


class Command(BaseCommand):
    help = "为指定的存量 Proxy 云区域补齐安装专用账号，或按记录恢复补齐前的状态。默认只检查。"

    def add_arguments(self, parser):
        parser.add_argument("--region-id", required=True, type=int)
        parser.add_argument("--apply", action="store_true", help="实际写入；省略时不修改数据库")
        parser.add_argument("--rollback-file", type=Path, help="补齐时写入、回退时读取的回退记录")
        parser.add_argument("--restore", action="store_true", help="检查或恢复补齐前的安装账号配置")

    @transaction.atomic
    def handle(self, *args, **options):
        region_id = options["region_id"]
        region = CloudRegion.objects.select_for_update().filter(pk=region_id).first()
        if region is None or region.is_default or not (region.proxy_address or region.pending_proxy_address):
            raise CommandError("请指定已配置 Proxy 地址的自定义云区域")

        current = {
            row.key: row
            for row in SidecarEnv.objects.select_for_update().filter(cloud_region=region, key__in=INSTALLER_KEYS)
        }
        rollback_file = options["rollback_file"]
        if options["restore"]:
            self.restore(region_id, current, rollback_file, options["apply"])
            return

        present = [key for key, row in current.items() if row.value.strip()]
        if len(present) == len(INSTALLER_KEYS):
            self.stdout.write(f"区域 {region_id} 已配置安装专用账号，无需修改")
            return
        if present:
            raise CommandError(f"区域 {region_id} 的安装账号配置不完整，请在云区域设置中核对并补齐原有账号")

        source = {
            row.key: row
            for row in SidecarEnv.objects.filter(cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, key__in=INSTALLER_KEYS)
        }
        if not all(key in source and source[key].value.strip() for key in INSTALLER_KEYS):
            raise CommandError("默认云区域缺少安装专用账号；请先完成中心配置升级")
        password = source[NodeConstants.NATS_INSTALLER_PASSWORD_KEY]
        if password.type != EnvVariableConstants.TYPE_SECRET or not AESCryptor().try_decode(password.value):
            raise CommandError("无法验证默认云区域的安装账号密文；请先修复中心配置")

        if not options["apply"]:
            self.stdout.write(f"区域 {region_id} 可从默认云区域补齐安装专用账号；尚未写入")
            return
        if rollback_file is None:
            raise CommandError("实际补齐时必须使用 --rollback-file 保存回退记录")

        before = {}
        after = {}
        for key in INSTALLER_KEYS:
            template = source[key]
            row = current.get(key)
            before[key] = None if row is None else [credential_state(row), row.value, row.type]
            if row is None:
                # A concurrent create fails the transaction instead of overwriting an administrator's value.
                row = SidecarEnv.objects.create(
                    cloud_region=region, key=key, value=template.value, type=template.type, description=template.description
                )
            else:
                row.value = template.value
                row.type = template.type
                row.save(update_fields=["value", "type"])
            after[key] = credential_state(row)
        write_rollback_file(rollback_file, region_id, before, after)
        self.stdout.write(f"已补齐区域 {region_id} 的安装专用账号并保存回退记录")

    def restore(self, region_id, current, rollback_file, apply):
        if rollback_file is None:
            raise CommandError("--restore 需要指定 --rollback-file")
        try:
            snapshot = signing.loads(rollback_file.read_text(), salt=ROLLBACK_SALT)
        except (OSError, ValueError, signing.BadSignature):
            raise CommandError("无法读取或验证回退记录") from None
        if snapshot["region"] != region_id:
            raise CommandError("回退记录与目标区域不匹配")

        before = snapshot["before"]
        actual = {key: credential_state(current.get(key)) for key in INSTALLER_KEYS}
        if actual == {key: before[key][0] if before[key] is not None else None for key in INSTALLER_KEYS}:
            self.stdout.write(f"区域 {region_id} 的安装账号已处于补齐前状态")
            return
        if actual != snapshot["after"]:
            raise CommandError("安装账号在补齐后已变化；请核对当前配置和回退记录，避免覆盖后续修改")
        if not apply:
            self.stdout.write(f"区域 {region_id} 可以恢复补齐前的安装账号配置；尚未写入")
            return

        for key in INSTALLER_KEYS:
            row = current[key]
            if before[key] is None:
                row.delete()
            else:
                _, row.value, row.type = before[key]
                row.save(update_fields=["value", "type"])
        self.stdout.write(f"已恢复区域 {region_id} 补齐前的安装账号配置")
