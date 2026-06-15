# -*- coding: utf-8 -*-
"""华为云采集器：调 CMPDriver(cloud_type=HuaweiCloud) 拉取平台与 ECS 资源。

输出结构：{"result": {"hwcloud": [...], "hwcloud_ecs": [...]}, "success": bool}
字段名严格对齐 CMDB 模型 attr-hwcloud / attr-hwcloud_ecs（不可改模型）。
"""
import traceback

from sanic.log import logger

from common.cmp.driver import CMPDriver


class HuaweiCloudManager:
    def __init__(self, params: dict):
        self.params = params
        self.account = params.get("username") or params.get("accessKey")
        self.password = params.get("password") or params.get("accessSecret")
        self.region = params.get("region", "")
        # endpoint：私有/专属场景由 host 指定，亦作为平台对象的 endpoint 字段
        self.endpoint = params.get("host", "")

    def _driver(self):
        return CMPDriver(
            self.account,
            self.password,
            "HuaweiCloud",
            region=self.region,
            host=self.endpoint,
        )

    def get_ecs(self):
        """返回标准化后的 ECS 列表（字段对齐 attr-hwcloud_ecs）。

        cw_huaweicloud.list_vms() 返回 {"result": bool, "data": [...]}；
        data 元素字段名以 cw_huaweicloud.format_resource 输出为准。
        """
        res = self._driver().list_vms()
        if not res or not res.get("result"):
            raise RuntimeError(res.get("message") if isinstance(res, dict) else "list_vms failed")
        ecs_list = []
        for item in res.get("data", []) or []:
            ecs_list.append(
                {
                    "resource_name": item.get("resource_name") or item.get("name", ""),
                    "resource_id": item.get("resource_id") or item.get("id", ""),
                    "ip_addr": item.get("ip_addr") or item.get("private_ip", ""),
                    "public_ip": item.get("public_ip", ""),
                    "region": item.get("region") or self.region,
                    "zone": item.get("zone") or item.get("availability_zone", ""),
                    "vpc": item.get("vpc") or item.get("vpc_id", ""),
                    "status": item.get("status", ""),
                    "instance_type": item.get("instance_type") or item.get("flavor", ""),
                    "os_name": item.get("os_name") or item.get("image_name", ""),
                    "vcpus": str(item.get("vcpus", "")),
                    "memory_mb": str(item.get("memory_mb") or item.get("ram", "")),
                    "charge_type": item.get("charge_type", ""),
                    "create_time": item.get("create_time") or item.get("created", ""),
                    "expired_time": item.get("expired_time", ""),
                }
            )
        return ecs_list

    def get_platform(self):
        """平台对象（hwcloud）：字段对齐 attr-hwcloud（endpoint）。"""
        return [{"endpoint": self.endpoint}]

    def exec_script(self):
        return {
            "hwcloud": self.get_platform(),
            "hwcloud_ecs": self.get_ecs(),
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
