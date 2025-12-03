from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models import SidecarEnv


class RegionService:

    @staticmethod
    def get_cloud_region_envconfig(cloud_region_id):
        """获取云区域环境变量"""
        objs = SidecarEnv.objects.filter(cloud_region_id)
        variables = {}
        for obj in objs:
            if obj.type == "secret":
                # 如果是密文，解密后使用
                aes_obj = AESCryptor()
                value = aes_obj.decode(obj.value)
                variables[obj.key] = value
            else:
                # 如果是普通变量，直接使用
                variables[obj.key] = obj.value
        return variables
