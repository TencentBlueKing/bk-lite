# -- coding: utf-8 --
# @File: encrypt_collect_password.py
# @Time: 2025/12/10 10:53
# @Author: windyzhao

from apps.cmdb.constants.constants import COLLECT_OBJ_TREE


def get_collect_model_passwords(collect_model_id):
    """
    获取采集模型所需的加密密码字典 从COLLECT_OBJ_TREE的encrypted_fields字段中提取
    :param collect_model_id: 采集模型名称
    :return: 加密密码字典
    """
    # 从 COLLECT_OBJ_TREE 中查找对应的采集模型配置
    encrypted_fields = []
    for parent in COLLECT_OBJ_TREE:
        for child in parent.get("children", []):
            if child.get("model_id") == collect_model_id:
                encrypted_fields = child.get("encrypted_fields", [])
                break
        if encrypted_fields:
            break

    return encrypted_fields
