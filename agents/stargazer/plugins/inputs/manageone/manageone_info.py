# -*- coding: utf-8 -*-
"""ManageOne 采集器：调 CMPDriver(cloud_type=ManageOne) 拉取平台与各类资源。

输出结构：
  {"result": {
      "manageone": [...], "manageone_cloud": [...], "manageone_server": [...],
      "manageone_host": [...], "manageone_ds": [...], "manageone_elb": [...],
   }, "success": bool}

字段名严格对齐 CMDB 模型 attr-manageone* （不可改模型）。
本层只输出 attr 业务字段，不生成 inst_name（由 server 端插件负责）。
"""
import traceback

from sanic.log import logger

from common.cmp.driver import CMPDriver


class ManageOneManager:
    def __init__(self, params: dict):
        self.params = params
        self.account = params.get("username") or params.get("accessKey")
        self.password = params.get("password") or params.get("accessSecret")
        self.region = params.get("region", "")
        # host：ManageOne 平台地址，同时作为平台对象的 global_domain_name
        self.host = params.get("host", "")

    def _driver(self):
        return CMPDriver(
            self.account,
            self.password,
            "ManageOne",
            region=self.region,
            host=self.host,
        )

    @staticmethod
    def _unwrap(res, method_name):
        """驱动 list_* 返回 {"result": bool, "data": [...], "total": N}；
        result=False 时抛错，由 list_all_resources 兜底成 success=False。"""
        if not res or not res.get("result"):
            msg = res.get("message") if isinstance(res, dict) else f"{method_name} failed"
            raise RuntimeError(msg or f"{method_name} failed")
        return res.get("data", []) or []

    def get_platform(self):
        """平台对象（manageone）：字段对齐 attr-manageone。"""
        return [{"global_domain_name": self.host, "region": self.region}]

    def get_cloud(self, driver=None):
        """云平台（manageone_cloud）← list_biz_regions。"""
        driver = driver or self._driver()
        data = self._unwrap(driver.list_biz_regions(), "list_biz_regions")
        result = []
        for item in data:
            result.append(
                {
                    "resource_name": item.get("resource_name", ""),
                    "resource_id": item.get("resource_id", ""),
                    "cloud_version": item.get("cloud_version", ""),
                    "brand": item.get("brand", ""),
                    "vcpus": str(item.get("vcpus", "")),
                    "memory_mb": str(item.get("memory_mb", "")),
                    "storage_gb": str(item.get("storage_gb", "")),
                }
            )
        return result

    def get_host(self, driver=None):
        """宿主机（manageone_host）← list_hosts。

        返回 (host_list, host_ip_map)；host_ip_map: resource_id -> ip_addr 供 server 填 self_host_ip。
        """
        driver = driver or self._driver()
        data = self._unwrap(driver.list_hosts(), "list_hosts")
        host_list = []
        host_ip_map = {}
        for item in data:
            resource_id = item.get("resource_id", "")
            ip_addr = item.get("ip_addr", "")
            host_ip_map[resource_id] = ip_addr
            host_list.append(
                {
                    "resource_name": item.get("resource_name", ""),
                    "resource_id": resource_id,
                    "ip_addr": ip_addr,
                    "hypervisor_type": item.get("hypervisor_type", ""),
                    "vcpus": str(item.get("cpu", "")),
                    "memory_mb": str(item.get("memory", "")),
                }
            )
        return host_list, host_ip_map

    def get_server(self, host_ip_map=None, driver=None):
        """云服务器（manageone_server）← list_vms。

        self_host_ip：用 host_id 在 host_ip_map 中查宿主机 ip（查不到留 ""）；
        expired_time：驱动未给，留 ""。
        """
        host_ip_map = host_ip_map or {}
        driver = driver or self._driver()
        data = self._unwrap(driver.list_vms(), "list_vms")
        result = []
        for item in data:
            host_id = item.get("host_id", "")
            result.append(
                {
                    "resource_name": item.get("resource_name", ""),
                    "resource_id": item.get("resource_id", ""),
                    "ip_addr": item.get("inner_ip", ""),
                    "region": item.get("region") or self.region,
                    "status": item.get("status", ""),
                    "os_name": item.get("os_name", ""),
                    "vcpus": str(item.get("vcpus", "")),
                    "create_time": item.get("create_time", ""),
                    "self_host_ip": host_ip_map.get(host_id, ""),
                    "expired_time": "",
                }
            )
        return result

    def get_ds(self, driver=None):
        """数据存储（manageone_ds）← list_ds。"""
        driver = driver or self._driver()
        data = self._unwrap(driver.list_ds(), "list_ds")
        result = []
        for item in data:
            result.append(
                {
                    "resource_name": item.get("resource_name", ""),
                    "resource_id": item.get("resource_id", ""),
                    "ip_addr": item.get("ip_addr", ""),
                    "storage_gb": str(item.get("storage_gb", "")),
                }
            )
        return result

    def get_elb(self, driver=None):
        """负载均衡（manageone_elb）← list_elb。

        驱动返回未格式化的原始 obj，字段名未知 → 多键回退兜底；
        并打印一条原始 obj 样例便于真机核对。
        """
        driver = driver or self._driver()
        data = self._unwrap(driver.list_elb(), "list_elb")
        if data:
            logger.info(f"[manageone] list_elb raw sample: {data[0]}")
        result = []
        for obj in data:
            result.append(
                {
                    "resource_name": obj.get("resource_name") or obj.get("name", ""),
                    "resource_id": obj.get("resource_id") or obj.get("id", ""),
                    "ip_addr": obj.get("ip_addr") or obj.get("eip") or obj.get("vip_address", ""),
                    "instance_type": obj.get("instance_type") or obj.get("spec") or obj.get("type", ""),
                }
            )
        return result

    def exec_script(self):
        driver = self._driver()
        host_list, host_ip_map = self.get_host(driver=driver)
        return {
            "manageone": self.get_platform(),
            "manageone_cloud": self.get_cloud(driver=driver),
            "manageone_server": self.get_server(host_ip_map=host_ip_map, driver=driver),
            "manageone_host": host_list,
            "manageone_ds": self.get_ds(driver=driver),
            "manageone_elb": self.get_elb(driver=driver),
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
