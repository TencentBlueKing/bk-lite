# -- coding: utf-8 --
# @File: vmware_info.py
# @Time: 2025/2/26 11:08
# @Author: windyzhao
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim
from sanic.log import logger

from core.decorator import timer


class VmwareManage(object):
    def __init__(self, params: dict):
        self.params = params
        self.password = params.get("password")
        self.user = params.get("username")
        self.host = params.get("host") or params.get("hostname")
        self.port = params.get("port", 443)
        """
        启用证书校验
        vCenter 必须：
        证书没过期
        主机名匹配
        CA 可信（或已导入）
        否则直接连接失败
        """
        self.ssl_verify = params.get("ssl", "false") == "true" # 要不要严格检查 vCenter 的 HTTPS 证书是不是合法的
        self.si = None
        self.content = None

        # disk detail enabled by default (issue #1104)
        self.collect_disk_detail = str(params.get("collect_disk_detail", "true")).lower() == "true"
        # NB custom fields (can be overridden by params)
        self.nb_last_backup_field = params.get("nb_last_backup_field", "NB_LAST_BACKUP")
        self.nb_backup_policy_field = params.get("nb_backup_policy_field", "NB_BACKUP_POLICY")

    def test_connection(self):
        """
        Test connection to vcenter
        :return:
        """
        try:
            self.connect_vc()
            return True
        except Exception as err:
            logger.error(f"test_connection error! {err}")
            return False

    def get_all_objs(self, obj_type, folder=None):
        if folder is None:
            container = self.content.viewManager.CreateContainerView(self.content.rootFolder, obj_type, True)
        else:
            container = self.content.viewManager.CreateContainerView(folder, obj_type, True)
        return container.view

    def connect_vc(self):
        try:
            params = dict(host=self.host, port=int(self.port), user=self.user, pwd=self.password,
                          httpConnectionTimeout=10, connectionPoolTimeout=10)
            if not self.ssl_verify:
                params['disableSslCertValidation'] = True
            import time
            a = time.time()
            si = SmartConnect(**params)
            self.si = si
            logger.error(f"SmartConnect time cost: {time.time() - a}")
            if not si:
                raise RuntimeError(
                    "Unable to establish a pyVmomi connection. Could you please double-check the address, username, or password?")
            self.content = si.RetrieveContent()
            logger.error(f"RetrieveContent time cost: {time.time() - a}")
        except Exception as err:
            logger.error(f"connect_vc error! {err}")
            raise RuntimeError("Connect vcenter error!" + str(err))

    def get_hosts(self):
        result = []
        cluster_list = self.get_all_objs(obj_type=[vim.ComputeResource])
        for cluster in cluster_list:
            for host in cluster.host:
                ip_addr = ""
                try:
                    if host.config and host.config.network:
                        if host.config.network.vnic:
                            for nic in host.config.network.vnic:
                                ip_addr = nic.spec.ip.ipAddress
                                break
                    else:
                        if host.summary and host.summary.managementServerIp:
                            ip_addr = host.summary.managementServerIp
                        else:
                            logger.warning("Host config or network is None and no managementServerIp found")
                except Exception as err:
                    logger.error(f"get_hosts host ip_add error! {err}")

                esxi_version = ""
                try:
                    esxi_version = host.config.product.version
                except Exception as err:
                    logger.error(f"get_hosts host.config.product.version host esxi_version error! {err}")

                if not esxi_version:
                    try:
                        esxi_version = host.summary.config.product.version
                    except Exception as err:
                        logger.error(f"get_hosts host.summary.config.product host esxi_version error! {err}")

                memory_total = host.hardware.memorySize // 1024 // 1024

                result.append(
                    {
                        "ip_addr": ip_addr,
                        # "inst_name": host.name,
                        "inst_name": f"{host.name}[{host._moId}]",
                        "resource_id": host._moId,
                        "memory": memory_total,
                        "cpu_model": host.summary.hardware.cpuModel,
                        "cpu_cores": host.summary.hardware.numCpuCores,
                        "vcpus": host.summary.hardware.numCpuThreads,
                        "esxi_version": esxi_version,
                        "vmware_ds": ",".join(i._moId for i in host.datastore),

                    }
                )

        return result

    @staticmethod
    def _get_vm_prop(vm, attributes):
        result = vm
        for attribute in attributes:
            try:
                result = getattr(result, attribute)
            except (AttributeError, IndexError):
                return None
        return result

    @staticmethod
    def _safe_str(value: Any) -> str:
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            return ""

    @staticmethod
    def _dt_to_iso(value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            try:
                return value.isoformat()
            except Exception:
                return ""
        return ""

    @staticmethod
    def _bytes_to_gb(value: Any) -> float:
        try:
            return round(float(value) / (1024 ** 3), 2)
        except Exception:
            return 0.0

    @staticmethod
    def _get_disk_type(backing: Any) -> str:
        try:
            raw_type_1 = getattr(vim.vm.device.VirtualDisk, "RawDiskMappingVer1BackingInfo", None)
            raw_type_2 = getattr(vim.vm.device.VirtualDisk, "RawDiskMappingVer2BackingInfo", None)
            raw_types = tuple(t for t in (raw_type_1, raw_type_2) if t is not None)
            if raw_types and isinstance(backing, raw_types):
                return "raw"

            se_sparse = getattr(vim.vm.device.VirtualDisk, "SeSparseBackingInfo", None)
            if se_sparse and isinstance(backing, se_sparse):
                return "sparse"

            thin = getattr(backing, "thinProvisioned", None)
            if thin is True:
                return "thin"
            if thin is False:
                return "thick"
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_custom_field_values(vm) -> Dict[str, str]:
        try:
            fields = getattr(vm, "availableField", None) or []
            values = getattr(vm, "value", None) or []
        except Exception:
            return {}

        key_to_name: Dict[int, str] = {}
        for f in fields:
            try:
                key_to_name[int(f.key)] = str(f.name)
            except Exception:
                continue

        result: Dict[str, str] = {}
        for v in values:
            try:
                name = key_to_name.get(int(v.key))
                if not name:
                    continue
                result[name] = "" if v.value is None else str(v.value)
            except Exception:
                continue
        return result

    def _get_vm_disks(self, vm) -> List[Dict[str, Any]]:
        if not self.collect_disk_detail:
            return []

        used_bytes_by_disk_key: Dict[int, int] = {}
        try:
            layout = getattr(vm, "layoutEx", None)
            if layout and getattr(layout, "file", None) and getattr(layout, "disk", None):
                file_size_by_key: Dict[int, int] = {}
                for f in layout.file:
                    try:
                        file_size_by_key[int(f.key)] = int(f.size or 0)
                    except Exception:
                        continue

                for d in layout.disk:
                    try:
                        file_keys: List[int] = []
                        for chain in getattr(d, "chain", None) or []:
                            for fk in getattr(chain, "fileKey", None) or []:
                                file_keys.append(int(fk))
                        used_bytes_by_disk_key[int(d.key)] = sum(file_size_by_key.get(k, 0) for k in file_keys)
                    except Exception:
                        continue
        except Exception:
            used_bytes_by_disk_key = {}

        try:
            devices = getattr(getattr(getattr(vm, "config", None), "hardware", None), "device", None) or []
        except Exception:
            devices = []

        disks: List[Dict[str, Any]] = []
        for dev in devices:
            if not isinstance(dev, vim.vm.device.VirtualDisk):
                continue

            backing = getattr(dev, "backing", None)
            provisioned_bytes = 0
            try:
                if getattr(dev, "capacityInBytes", None) is not None:
                    provisioned_bytes = int(dev.capacityInBytes)
                elif getattr(dev, "capacityInKB", None) is not None:
                    provisioned_bytes = int(dev.capacityInKB) * 1024
            except Exception:
                provisioned_bytes = 0

            disk_key = None
            try:
                disk_key = int(getattr(dev, "key", 0))
            except Exception:
                disk_key = None

            used_bytes: Optional[int] = None
            if disk_key is not None and disk_key in used_bytes_by_disk_key:
                used_bytes = used_bytes_by_disk_key[disk_key]
                if provisioned_bytes:
                    try:
                        if used_bytes > provisioned_bytes * 1.1:
                            used_bytes = provisioned_bytes
                    except Exception:
                        pass

            datastore_name = ""
            try:
                datastore = getattr(backing, "datastore", None)
                datastore_name = getattr(datastore, "name", "") or ""
            except Exception:
                datastore_name = ""

            disks.append(
                {
                    "disk_id": disk_key,
                    "provisioned_gb": self._bytes_to_gb(provisioned_bytes),
                    "used_gb": None if used_bytes is None else self._bytes_to_gb(used_bytes),
                    "disk_type": self._get_disk_type(backing),
                    "datastore": datastore_name,
                }
            )

        return disks

    def get_vms(self):
        result = []
        try:
            vm_list = self.get_all_objs(obj_type=[vim.VirtualMachine])
            for vm in vm_list:
                if vm.config and vm.config.template:
                    continue

                vm_dict = {
                    "resource_id": vm._moId,
                    "inst_name": f"{vm.name}[{vm._moId}]",
                    "ip_addr": "",
                    "vmware_esxi": "",
                    "vmware_ds": "",
                    "cluster": "",
                    "os_name": "",
                    "vcpus": "",
                    "memory": "",
                    "annotation": "",
                    "uptime_seconds": "0",
                    "tools_version": "",
                    "tools_status": "",
                    "tools_running_status": "",
                    "last_boot": "",
                    "creation_date": "",
                    "last_backup": "",
                    "backup_policy": "",
                    "data_disks": "[]",
                }

                vmnet = self._get_vm_prop(vm, ("guest", "net"))
                if vmnet:
                    net_dict = {}
                    for device in vmnet:
                        net_dict[device.macAddress] = dict()
                        net_dict[device.macAddress]["ipv4"] = []
                        net_dict[device.macAddress]["ipv6"] = []
                        for ip_addr in device.ipAddress:
                            if "::" in ip_addr:
                                net_dict[device.macAddress]["ipv6"].append(ip_addr)
                            else:
                                net_dict[device.macAddress]["ipv4"].append(ip_addr)

                    for _vmnet in net_dict.values():
                        if _vmnet["ipv4"]:
                            vm_dict["ip_addr"] = _vmnet["ipv4"][0]
                            break

                    if not vm_dict["ip_addr"]:
                        for _vmnet in net_dict.values():
                            if _vmnet["ipv6"]:
                                vm_dict["ip_addr"] = _vmnet["ipv6"][0]
                                break

                if vm.summary.runtime.host:
                    vm_dict["vmware_esxi"] = vm.summary.runtime.host._moId
                    if isinstance(vm.summary.runtime.host.parent, vim.ClusterComputeResource):
                        vm_dict["cluster"] = vm.summary.runtime.host.parent.name

                vm_dict["vmware_ds"] = ",".join(datastore._moId for datastore in vm.datastore)
                vm_dict["vcpus"] = vm.summary.config.numCpu
                vm_dict["os_name"] = vm.summary.config.guestFullName
                vm_dict["memory"] = vm.summary.config.memorySizeMB

                vm_dict["annotation"] = self._safe_str(self._get_vm_prop(vm, ("summary", "config", "annotation")))

                uptime = self._get_vm_prop(vm, ("summary", "quickStats", "uptimeSeconds"))
                try:
                    vm_dict["uptime_seconds"] = "0" if uptime in (None, "") else str(int(uptime))
                except Exception:
                    vm_dict["uptime_seconds"] = "0"

                vm_dict["tools_version"] = self._safe_str(self._get_vm_prop(vm, ("guest", "toolsVersion")))
                vm_dict["tools_status"] = self._safe_str(self._get_vm_prop(vm, ("guest", "toolsStatus")))
                vm_dict["tools_running_status"] = self._safe_str(self._get_vm_prop(vm, ("guest", "toolsRunningStatus")))
                vm_dict["last_boot"] = self._dt_to_iso(self._get_vm_prop(vm, ("runtime", "bootTime")))
                vm_dict["creation_date"] = self._dt_to_iso(self._get_vm_prop(vm, ("config", "createDate")))

                custom_fields = self._get_custom_field_values(vm)
                vm_dict["last_backup"] = self._safe_str(custom_fields.get(self.nb_last_backup_field, ""))
                vm_dict["backup_policy"] = self._safe_str(custom_fields.get(self.nb_backup_policy_field, ""))

                try:
                    disks = self._get_vm_disks(vm)
                    vm_dict["data_disks"] = json.dumps(disks, ensure_ascii=False, separators=(",", ":"))
                except Exception as err:
                    logger.error(f"get_vms build disk detail error! {err}")

                result.append(vm_dict)

        except Exception as err:
            logger.error(f"get_vms error! {err}")

        return result

    def get_datastore(self):
        result = []
        cluster_list = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.ComputeResource], True
        ).view
        for cluster in cluster_list:
            result.append({"name": cluster.name, "moid": cluster._moId})
        return result

    def get_datacenters_and_datastore(self):
        datastore_list = []
        datacenters_list = []
        try:
            container = self.get_all_objs(obj_type=[vim.Datacenter])
            for datacenter in container:
                datacenter_dict = {
                    "moid": datacenter._moId,
                    "name": datacenter.name,
                    "vc": {"name": self.content.about.name, "version": self.content.about.version},
                }
                for datastore in datacenter.datastore:
                    datastore_list.append(
                        {
                            "resource_id": datastore._moId,
                            "ds_url": datastore.summary.url,
                            # "inst_name": datastore.summary.name,
                            "inst_name": f"{datastore.summary.name}[{datastore._moId}]",
                            "system_type": datastore.summary.type,
                            "storage": datastore.summary.capacity // 1024 // 1024 // 1024,
                            "vmware_esxi": ",".join(host.key._moId for host in datastore.summary.datastore.host),
                        }
                    )
                datacenters_list.append(datacenter_dict)
        except Exception as err:
            logger.error(f"get_datacenters_and_datastore error! {err}")

        return datacenters_list, datastore_list

    def service(self):
        vc_name = self.content.about.name
        vc_version = self.content.about.version
        datacenters, datastore = self.get_datacenters_and_datastore()
        vm_list = self.get_vms()
        esxi = self.get_hosts()

        result = {
            "vmware_vc": [{"vc_version": vc_version, "inst_name": vc_name}],
            "vmware_ds": datastore,
            "vmware_vm": vm_list,
            "vmware_esxi": esxi,
        }

        return result

    def disconnect_vc(self):
        try:
            if self.si:
                Disconnect(self.si)
        except Exception:
            logger.error(f"disconnect_vc error! {self.si}")
            pass

    @timer(logger=logger)
    def list_all_resources(self):
        try:
            self.connect_vc()
            result = self.service()
            inst_data = {"result": result, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"vmware_info list_all_resources error! {traceback.format_exc()}")
            error = str(err)
            error = error.replace("=", "-").replace("\n", " ")
            inst_data = {"result": {"cmdb_collect_error": error}, "success": False}
        finally:
            self.disconnect_vc()
        
        return inst_data
