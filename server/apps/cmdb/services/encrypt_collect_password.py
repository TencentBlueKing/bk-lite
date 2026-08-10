# -- coding: utf-8 --
# @File: encrypt_collect_password.py
# @Time: 2025/12/10 10:53
# @Author: windyzhao

from apps.cmdb.services.collect_credential_contract import (
    get_collect_credential_contract,
)
from apps.cmdb.services.collect_object_tree import get_collect_object_meta


def get_collect_model_passwords(collect_model_id, driver_type=None):
    """
    获取采集模型所需的加密字段。

    静态凭据契约是已注册模型的权威来源，不能依赖企业采集对象树是否已装载；
    未注册模型继续从 COLLECT_OBJ_TREE 读取，以兼容现有配置。
    :param collect_model_id: 采集模型名称
    :return: 加密密码字典
    """
    credential_contract = get_collect_credential_contract(collect_model_id)
    if credential_contract is not None:
        return credential_contract.get("encrypted_fields", [])

    collect_object_meta = get_collect_object_meta(collect_model_id, driver_type=driver_type)
    return collect_object_meta.get("encrypted_fields", [])
