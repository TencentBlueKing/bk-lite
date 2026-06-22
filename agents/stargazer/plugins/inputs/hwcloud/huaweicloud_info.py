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
        # project_id：华为云 SDK（CwHuaweicloud）构造必需；缺失时由驱动抛出
        # 明确的「项目id不可为空」错误，不臆造默认值。
        self.project_id = params.get("project_id", "") or ""

    def _driver(self):
        kwargs = {}
        if self.project_id:
            kwargs["project_id"] = self.project_id
        return CMPDriver(
            self.account,
            self.password,
            "HuaweiCloud",
            region=self.region,
            host=self.endpoint,
            **kwargs,
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

    # ---------------- 子对象采集（纯增量，存量 ECS/platform 不动） ----------------

    @staticmethod
    def _s(v):
        """统一转字符串（指标 label 均为字符串）；None → 空串。"""
        return "" if v is None else str(v)

    def _fetch(self, method_name):
        """调驱动 list_* 方法（best-effort）：异常或 result=False 仅记日志并返回 []。

        新增子对象为纯增量，单个资源采集失败不得影响存量 ECS/platform 采集，
        因此这里吞掉异常（不像 get_ecs 那样抛错使整次采集失败）。
        """
        try:
            res = getattr(self._driver(), method_name)()
        except Exception as err:  # noqa: BLE001
            logger.warning(f"huaweicloud {method_name} 采集跳过（异常）：{err}")
            return []
        if not res or not res.get("result"):
            msg = res.get("message") if isinstance(res, dict) else res
            logger.warning(f"huaweicloud {method_name} 采集跳过（返回失败）：{msg}")
            return []
        return res.get("data", []) or []

    def get_evs(self):
        """云硬盘（attr-hwcloud_evs）。驱动 list_disks 已归一化。server_id 为隐藏关联→ECS。"""
        out = []
        for it in self._fetch("list_disks"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "disk_size": self._s(it.get("disk_size")),
                "disk_type": self._s(it.get("disk_type")),
                "category": self._s(it.get("category")),
                "status": self._s(it.get("status")),
                "charge_type": self._s(it.get("charge_type")),
                "zone": self._s(it.get("zone")),
                "region": self._s(it.get("region")) or self.region,
                "create_time": self._s(it.get("create_time")),
                "server_id": self._s(it.get("server_id")),  # 隐藏关联字段
            })
        return out

    def get_obs(self):
        """对象存储桶（attr-hwcloud_obs）。驱动 list_buckets 已归一化。"""
        out = []
        for it in self._fetch("list_buckets"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "bucket_type": self._s(it.get("bucket_type")),
                "region": self._s(it.get("region")) or self.region,
                "create_time": self._s(it.get("create_time")),
            })
        return out

    def get_vpc(self):
        """VPC（attr-hwcloud_vpc）。驱动 list_vpcs 已归一化。"""
        out = []
        for it in self._fetch("list_vpcs"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "status": self._s(it.get("status")),
                "cidr": self._s(it.get("cidr")),
                "is_default": self._s(it.get("is_default")),
                "region": self._s(it.get("region")) or self.region,
            })
        return out

    def get_subnet(self):
        """子网（attr-hwcloud_subnet）。vpc 为隐藏关联→VPC。"""
        out = []
        for it in self._fetch("list_subnets"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "status": self._s(it.get("status")),
                "cidr": self._s(it.get("cidr")),
                "gateway": self._s(it.get("gateway")),
                "zone": self._s(it.get("zone")),
                "region": self._s(it.get("region")) or self.region,
                "vpc": self._s(it.get("vpc")),  # 隐藏关联字段（raw vpc_id）
            })
        return out

    def get_eip(self):
        """弹性公网IP（attr-hwcloud_eip）。"""
        out = []
        for it in self._fetch("list_eips"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "ip_addr": self._s(it.get("ip_addr")),
                "status": self._s(it.get("status")),
                "bandwidth": self._s(it.get("bandwidth")),
                "charge_type": self._s(it.get("charge_type")),
                "region": self._s(it.get("region")) or self.region,
                "create_time": self._s(it.get("create_time")),
            })
        return out

    def get_sg(self):
        """安全组（attr-hwcloud_sg）。vpc 隐藏关联（可能为空）。"""
        out = []
        for it in self._fetch("list_security_groups"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "is_default": self._s(it.get("is_default")),
                "region": self._s(it.get("region")) or self.region,
                "vpc": self._s(it.get("vpc")),  # 隐藏关联字段（可能为空）
            })
        return out

    def get_elb(self):
        """负载均衡（attr-hwcloud_elb）。vpc 隐藏关联。"""
        out = []
        for it in self._fetch("list_load_balancers"):
            out.append({
                "resource_name": self._s(it.get("resource_name")),
                "resource_id": self._s(it.get("resource_id")),
                "status": self._s(it.get("status")),
                "ip_version": self._s(it.get("ip_version")),
                "ipv6_addr": self._s(it.get("ipv6_addr")),
                "charge_type": self._s(it.get("charge_type")),
                "region": self._s(it.get("region")) or self.region,
                "create_time": self._s(it.get("create_time")),
                "vpc": self._s(it.get("vpc")),  # 隐藏关联字段
            })
        return out

    def get_rds(self):
        """云数据库RDS（attr-hwcloud_rds）。字段取自官方 ListInstances 响应，不杜撰。

        嵌套对象：datastore.{type,version}、volume.{type,size}、charge_info.charge_mode；
        private_ips/public_ips 取首个。vpc_id/subnet_id 为隐藏字段。
        """
        out = []
        for it in self._fetch("list_rds"):
            ds = it.get("datastore") or {}
            vol = it.get("volume") or {}
            charge = it.get("charge_info") or {}
            priv = it.get("private_ips") or []
            pub = it.get("public_ips") or []
            out.append({
                "resource_name": self._s(it.get("name")),
                "resource_id": self._s(it.get("id")),
                "ip_addr": self._s(priv[0]) if priv else "",
                "public_ip": self._s(pub[0]) if pub else "",
                "status": self._s(it.get("status")),
                "db_type": self._s(it.get("type")),
                "engine": self._s(ds.get("type")),
                "engine_version": self._s(ds.get("version")),
                "volume_type": self._s(vol.get("type")),
                "volume_size": self._s(vol.get("size")),
                "vcpus": self._s(it.get("cpu")),
                "memory_gb": self._s(it.get("mem")),
                "port": self._s(it.get("port")),
                "region": self._s(it.get("region")) or self.region,
                "charge_type": self._s(charge.get("charge_mode")),
                "create_time": self._s(it.get("created")),
                "vpc_id": self._s(it.get("vpc_id")),      # 隐藏字段
                "subnet_id": self._s(it.get("subnet_id")),  # 隐藏字段
            })
        return out

    def get_dcs(self):
        """分布式缓存Redis（attr-hwcloud_dcs）。字段取自官方 DCS V2 ListInstances 响应。

        注意官方字段：instance_id / charging_mode / created_at（非 id/charge_mode/created）。
        """
        out = []
        for it in self._fetch("list_dcs"):
            out.append({
                "resource_name": self._s(it.get("name")),
                "resource_id": self._s(it.get("instance_id")),
                "ip_addr": self._s(it.get("ip")),
                "port": self._s(it.get("port")),
                "status": self._s(it.get("status")),
                "engine": self._s(it.get("engine")),
                "engine_version": self._s(it.get("engine_version")),
                "capacity_gb": self._s(it.get("capacity")),
                "cache_mode": self._s(it.get("cache_mode")),
                "charge_type": self._s(it.get("charging_mode")),
                "region": self._s(it.get("region")) or self.region,
                "create_time": self._s(it.get("created_at")),
                "vpc_id": self._s(it.get("vpc_id")),      # 隐藏字段
                "subnet_id": self._s(it.get("subnet_id")),  # 隐藏字段
            })
        return out

    def get_platform(self):
        """平台对象（hwcloud）：字段对齐 attr-hwcloud（endpoint）。"""
        return [{"endpoint": self.endpoint}]

    def exec_script(self):
        return {
            "hwcloud": self.get_platform(),
            "hwcloud_ecs": self.get_ecs(),
            "hwcloud_evs": self.get_evs(),
            "hwcloud_obs": self.get_obs(),
            "hwcloud_vpc": self.get_vpc(),
            "hwcloud_subnet": self.get_subnet(),
            "hwcloud_eip": self.get_eip(),
            "hwcloud_sg": self.get_sg(),
            "hwcloud_elb": self.get_elb(),
            "hwcloud_rds": self.get_rds(),
            "hwcloud_dcs": self.get_dcs(),
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
