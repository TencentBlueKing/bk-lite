from django.core.management import BaseCommand, CommandError
from django.db import transaction

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


class Command(BaseCommand):
    help = "为指定的存量 Proxy 云区域补齐缺失的安装专用账号；默认只检查。"

    def add_arguments(self, parser):
        parser.add_argument("--region-id", required=True, type=int)
        parser.add_argument("--apply", action="store_true", help="实际写入；省略时不修改数据库")

    @transaction.atomic
    def handle(self, *args, **options):
        region_id = options["region_id"]
        region = CloudRegion.objects.select_for_update().filter(pk=region_id).first()
        if region is None or region.is_default or not (region.proxy_address or region.pending_proxy_address):
            raise CommandError("请指定已配置 Proxy 地址的自定义云区域")

        user_key = NodeConstants.NATS_INSTALLER_USERNAME_KEY
        password_key = NodeConstants.NATS_INSTALLER_PASSWORD_KEY
        keys = (user_key, password_key)
        current = {
            row.key: row
            for row in SidecarEnv.objects.select_for_update().filter(cloud_region=region, key__in=keys)
        }
        present = [key for key, row in current.items() if row.value.strip()]
        if len(present) == len(keys):
            self.stdout.write(f"区域 {region_id} 已配置安装专用账号，无需修改")
            return
        if present:
            raise CommandError(f"区域 {region_id} 的安装账号配置不完整，请在云区域设置中核对并补齐原有账号")

        source = {
            row.key: row
            for row in SidecarEnv.objects.filter(cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, key__in=keys)
        }
        if not all(key in source and source[key].value.strip() for key in keys):
            raise CommandError("默认云区域缺少安装专用账号；请先完成中心配置升级")
        password = source[password_key]
        if password.type != EnvVariableConstants.TYPE_SECRET or not AESCryptor().try_decode(password.value):
            raise CommandError("无法验证默认云区域的安装账号密文；请先修复中心配置")

        if not options["apply"]:
            self.stdout.write(f"区域 {region_id} 可从默认云区域补齐安装专用账号；尚未写入")
            return

        for key in keys:
            template = source[key]
            row = current.get(key)
            if row is None:
                # On a concurrent create, fail the transaction instead of
                # overwriting values entered by a cloud-region administrator.
                SidecarEnv.objects.create(cloud_region=region, key=key, value=template.value, type=template.type, description=template.description)
            else:
                row.value = template.value
                row.type = template.type
                row.save(update_fields=["value", "type"])
        self.stdout.write(f"已补齐区域 {region_id} 的安装专用账号")
