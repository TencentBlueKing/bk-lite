# -- coding: utf-8 --
# @File: init_migrate.py
# @Time: 2025/3/24 10:42
# @Author: windyzhao
import json
import os


def init_network_oid(**kwargs):
    """
    初始化oid
    """
    oid_model = kwargs["sender"].models["oidmapping"]
    if oid_model.objects.filter(built_in=True).exists():
        # 存在内置的oid 说明已经内置过了 停止内置
        return

    oid_file_path = os.path.join(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "oid"),
        "systemoid.json",
    )
    if not os.path.exists(oid_file_path):
        raise FileNotFoundError(f"OID file not found: {oid_file_path}")

    with open(oid_file_path, encoding="utf-8") as r:
        net_work_oid_mapping = json.loads(r.read())

    bulk_data = []
    for data in net_work_oid_mapping.values():
        device_type = data["FirstTypeId"].lower()
        params = {
            "oid": data["OID"],
            "model": data["model"],
            "brand": data["brand"],
            "device_type": device_type,
        }
        bulk_data.append(oid_model(**params))

    oid_model.objects.bulk_create(bulk_data, batch_size=100)
