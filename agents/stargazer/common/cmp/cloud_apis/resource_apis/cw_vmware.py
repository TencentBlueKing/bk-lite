# -*- coding: UTF-8 -*-
import datetime
import logging
import socket
import ssl
import time
from ssl import SSLEOFError

from pyVim import connect
from pyVim.connect import SmartConnect
from pyVmomi import vim

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_object.base import Region, Zone
from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.utils import convert_param_to_list

logger = logging.getLogger("root")


class CwVmware(object):
    def __init__(self, account, password, region, host="", **kwargs):
        self.account = account
        self.password = password
        self.host = host
        self.region = region
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.si = self._connect_vc()
        self.content = self.si.RetrieveContent()

    def __getattr__(self, item):
        return Vmware(si=self.si, content=self.content, name=item, region=self.region)

    def _connect_vc(self):
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
            context.verify_mode = ssl.CERT_NONE
            si = SmartConnect(host=self.host, user=self.account, pwd=self.password, port=443, sslContext=context)
            return si
        except (SSLEOFError, socket.error):
            context = ssl._create_unverified_context()
            context.verify_mode = ssl.CERT_NONE
            si = SmartConnect(host=self.host, user=self.account, pwd=self.password, port=443, sslContext=context)
            return si
        except Exception as e:
            logger.exception("connect_vc error" + str(e))
            return None

    @classmethod
    def deconnect_vc(cls, si):
        connect.Disconnect(si)


class Vmware(PrivateCloudManage):
    """
    This class providing all operations on VMware vSphere platform.
    """

    def __init__(self, si, content, name, region):
        """
        Initialize vmware vSphere object.
        :param si: a service instance object using for connecting to the specified server.
        :param content: retrieve content object
        :param name: calling method name
        """
        self.si = si
        self.content = content
        self.name = name
        self.region = region
        self.cloud_type = CloudType.VMWARE.value

    def _convert_server_time_to_timestamp(self, time_str):
        """
        将服务器时间字符串转换为时间戳
        :param time_str: 服务器时间字符串，格式为 "%Y-%m-%d %H:%M:%S"
        :return: Unix时间戳（秒）
        """
        try:
            # 将时间字符串解析为datetime对象，这里假设时间字符串是服务器本地时间
            dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            # 转换为时间戳，mktime会根据服务器的本地时区进行转换
            timestamp = int(time.mktime(dt.timetuple()))
            return timestamp
        except ValueError as e:
            logger.error(f"Invalid time format {time_str}: {e}")
            raise

    def _convert_server_time_to_datetime(self, time_str):
        """
        将服务器时间字符串转换为带时区的datetime对象
        :param time_str: 服务器时间字符串，格式为 "%Y-%m-%d %H:%M:%S"
        :return: 带时区信息的datetime对象
        """
        try:
            import pytz
            import os
            from datetime import timezone, timedelta

            # 将时间字符串解析为naive datetime对象
            dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

            # 获取服务器时区信息，支持多种方式
            server_tz = self._get_server_timezone()

            # 将naive datetime转换为带时区的datetime
            if isinstance(server_tz, str):
                # 如果是字符串时区名（如'Asia/Shanghai'）
                tz = pytz.timezone(server_tz)
                dt_with_tz = tz.localize(dt)
            else:
                # 如果是timezone对象
                dt_with_tz = dt.replace(tzinfo=server_tz)

            return dt_with_tz
        except ValueError as e:
            logger.error(f"Invalid time format {time_str}: {e}")
            raise
        except Exception as e:
            logger.warning(f"Failed to apply timezone, using naive datetime: {e}")
            # 如果时区处理失败，返回原始datetime对象
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    def _get_server_timezone(self):
        """
        获取服务器时区信息
        :return: 时区对象或时区字符串
        """
        import pytz
        import os
        from datetime import timezone, timedelta

        try:
            # 方法1: 从环境变量获取时区
            tz_env = os.environ.get('TZ')
            if tz_env:
                try:
                    return pytz.timezone(tz_env)
                except:
                    pass

            # 方法2: 从系统获取时区信息
            try:
                import time
                # 获取系统时区偏移量（秒）
                if time.daylight:
                    # 如果有夏令时，使用夏令时偏移
                    offset_seconds = -time.altzone
                else:
                    # 使用标准时区偏移
                    offset_seconds = -time.timezone

                # 转换为小时
                offset_hours = offset_seconds // 3600
                offset_minutes = (offset_seconds % 3600) // 60

                # 创建固定偏移的时区对象
                server_tz = timezone(timedelta(hours=offset_hours, minutes=offset_minutes))
                return server_tz
            except:
                pass

            # 方法3: 尝试从/etc/timezone读取（Linux系统）
            try:
                if os.path.exists('/etc/timezone'):
                    with open('/etc/timezone', 'r') as f:
                        tz_name = f.read().strip()
                        return pytz.timezone(tz_name)
            except:
                pass

            # 方法4: 默认使用UTC
            logger.warning("Could not determine server timezone, using UTC")
            return timezone.utc

        except Exception as e:
            logger.error(f"Error getting server timezone: {e}")
            return timezone.utc

    # find method name and exec it.
    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    # if method name not found, then exec _non_function method.
    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        check if this object works.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        if self.si:
            return {"result": True}

    def __region_format(self, region_obj):
        if region_obj:
            return Region(
                id=region_obj._moId,
                name=region_obj.name,
                text=region_obj.name,
                platform_type=CloudType.VMWARE.value,
                description="",
                created_time="",
                updated_time="",
                extra={},
            ).to_dict()
        else:
            return None

    def list_regions(self):
        """
        get datacenter list
        :rtype: dict
        """
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, [vim.Datacenter], True)
        datacenter_list = container.view
        return {"result": True, "data": [self._format_resource_result("region", i) for i in datacenter_list if i]}
        # return {"result": True, "data": [self.__region_format(i) for i in datacenter_list if i]}

    def __find_region_by_id(self, dc_id):
        region_obj = None
        region_obj_rs = self.list_regions()
        if region_obj_rs["result"]:
            for cur_region in region_obj_rs["data"]:
                if cur_region.get("id") == dc_id:
                    region_obj = cur_region
                    break
        return region_obj

    def __zone_format(self, zone_obj, **kwargs):
        if zone_obj:
            return Zone(
                id=zone_obj._moId,
                name=zone_obj.name,
                platform_type=CloudType.VMWARE.value,
                description="",
                status="",
                created_time="",
                updated_time="",
                extra={"dc_id": kwargs["region_id"], "dc_name": kwargs["region_name"]},
            ).to_dict()
        else:
            return None

    def list_zones(self, **kwargs):
        """
        get zone list on cloud platforms
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * region: the Id of a specific datacenter.(required)
        -----------------
        :rtype: dict
        """
        data = []
        if kwargs.get("region"):
            region = kwargs["region"]
            dc_obj = self._get_obj_bymoId(self.content, [vim.Datacenter], region)
            container = self.content.viewManager.CreateContainerView(dc_obj.hostFolder, [vim.ComputeResource], True)
            data = [
                self._format_resource_result("zone", {"obj": i, "region_id": region, "region_name": dc_obj.name})
                for i in container.view
                if i
            ]
        else:
            region_rs = self.list_regions()
            if region_rs["result"]:
                for cur_region in region_rs["data"]:
                    dc_obj = self._get_obj_bymoId(self.content, [vim.Datacenter], cur_region["resource_id"])
                    container = self.content.viewManager.CreateContainerView(
                        dc_obj.hostFolder, [vim.ComputeResource], True
                    )
                    data.extend(
                        [
                            self._format_resource_result(
                                "zone",
                                {
                                    "obj": i,
                                    "region_id": cur_region["resource_id"],
                                    "region_name": cur_region["resource_name"],
                                },
                            )
                            for i in container.view
                            if i
                        ]
                    )
        return {"result": True, "data": data}

    @classmethod
    def _get_obj_bymoId(cls, content, vim_type, mo_id):
        obj = None
        container = content.viewManager.CreateContainerView(content.rootFolder, vim_type, True)
        for c in container.view:
            if mo_id:
                if c._moId == mo_id:
                    obj = c
                    break
            else:
                obj = None
                break
        return obj

    def get_projects(self):
        """
        get project list on cloud platforms
        :rtype: dict
        """
        return {"result": False, "message": "无项目信息！"}

    def list_vms(self, ids=None):
        """
        Get vm list on vmware vsphere platforms
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        try:
            content = self.content
            vms_list = []
            disk_list = []
            snapshot_list = []
            ids = convert_param_to_list(ids)
            if ids:
                vm_obj = self._get_obj_bymoId(content, [vim.VirtualMachine], ids[0])
                vm_instance, vm_disk_data, vm_snap_data = self.__vm_format(vm_obj)
                if vm_instance:
                    vms_list = [vm_instance]
                if vm_disk_data:
                    disk_list.extend(vm_disk_data)
                if vm_snap_data:
                    snapshot_list.extend(vm_snap_data)
            else:
                vm_list = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True).view
                for vm in vm_list:
                    try:
                        if not vm.config.template:
                            vm_format_data, vm_disk_data, vm_snap_data = self.__vm_format(vm)
                            if vm_format_data:
                                vms_list.append(vm_format_data)
                            if vm_disk_data:
                                disk_list.extend(vm_disk_data)
                            if vm_snap_data:
                                snapshot_list.extend(vm_snap_data)
                    except Exception:
                        logger.error("list_vms——not found attribute template: {}".format(vm.name))
            # return {"result": True, "data": vms_list, "total": total}
            return {
                "result": True,
                "data": {"list_vms": vms_list, "list_disks": disk_list, "list_snapshots": snapshot_list},
            }
        except Exception as e:
            logger.exception("get_vm_info" + str(e))
            return {"result": False, "message": str(e)}

    def __nic_format(self, nic_obj):
        if nic_obj:
            pass
        else:
            return None

    def __vm_format(self, vm_obj):
        try:
            if not str(vm_obj.runtime.connectionState) == "disconnected":
                vm_id = vm_obj._moId
                name = vm_obj.name
                vm_instance = self._format_resource_result("vm", vm_obj)
                disk_list = []
                disk_object_rs = self.get_vm_disks(vm_obj._moId)
                if disk_object_rs["result"]:
                    disk_list = disk_object_rs["data"]

                snapshot_list = []
                snapshot_obj_rs = self.get_vm_snapshots({"vm_id": vm_id, "vm_name": name})
                if snapshot_obj_rs["result"]:
                    snapshot_list = snapshot_obj_rs["data"]

                return vm_instance, disk_list, snapshot_list
            else:
                return None, None, None
        except Exception as e:
            logger.exception("get_vm_info:" + str(e))
            return None, None, None

    def _format_resource_result(self, resource_type, obj):
        """
        格式化获取到的资源结果
        Args:
            resource_type (str): 资源类型名 如 region
            data (list or object): 待格式化的数据，

        Returns:

        """
        try:
            # cloud_type 这些哪里来。。。
            format_method = get_format_method(self.cloud_type, resource_type, region_id=self.region)

            return format_method(obj)
        except Exception as e:
            logger.exception("get_vm_info:" + str(e))
            return None

    # ------------------***** monitor *****-------------------
    def monitor_data_batch(self, counters=None, interval=20, **kwargs):
        """
        批量获取监控数据，支持多个counter同时查询，减少API调用次数
        :param counters: type list.(required) 监控指标列表，例如 ["cpu.usage.average", "mem.usage.average"]
        :param interval: 采样间隔
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * obj: vm object.(required)
        * StartTime: start time.(required)
        * EndTime: end time.(required)
        --------------
        :rtype: dict
        """
        if not counters:
            counters = ["cpu.usage.average", "mem.usage.average"]

        content = self.content
        obj = kwargs["obj"]
        start_time = kwargs["StartTime"]
        end_time = kwargs["EndTime"]
        # 使用新的时间转换方法，确保时区一致性
        start_time = self._convert_server_time_to_datetime(start_time)
        end_time = self._convert_server_time_to_datetime(end_time)

        try:
            counter_info = self._get_vmware_metrics(content)

            # 构建多个MetricId
            metric_ids = []
            valid_counters = []
            for counter in counters:
                if counter in counter_info:
                    counter_key = counter_info[counter]
                    metric_id = vim.PerformanceManager.MetricId(counterId=counter_key, instance="*")
                    metric_ids.append(metric_id)
                    valid_counters.append(counter)
                else:
                    logger.warning(f"Counter {counter} not found in performance metrics")

            if not metric_ids:
                return {"result": False, "message": "No valid counters found"}

            # 为每个对象创建查询规格，包含所有指标
            spec_list = []
            for i in obj:
                spec = vim.PerformanceManager.QuerySpec(
                    startTime=start_time,
                    endTime=end_time,
                    entity=i,
                    metricId=metric_ids,  # 传入所有指标ID
                    maxSample=1,
                    intervalId=interval,
                )
                spec_list.append(spec)

            result = content.perfManager.QueryPerf(querySpec=spec_list)
            return {"result": True, "res": result, "counters": valid_counters}
        except Exception as e:
            logger.exception("monitor_data_batch")
            return {"result": False, "message": str(e)}

    def monitor_data(self, counter="cpu.usage.average", interval=20, **kwargs):
        """
        monitor cpu usage or memory usage.
        :param counter: type str.(required) "cpu.usage.average" | "mem.usage.average"
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * obj: vm object.(requried)
        * StartTime: start time.(required)
        * EndTime: end time.(required)
        --------------
        :rtype: dict
        """
        content = self.content
        obj = kwargs["obj"]
        start_time = kwargs["StartTime"]
        end_time = kwargs["EndTime"]
        # 使用新的时间转换方法，确保时区一致性
        start_time = self._convert_server_time_to_datetime(start_time)
        end_time = self._convert_server_time_to_datetime(end_time)
        try:
            counter_info = self._get_vmware_metrics(content)
            counter_key = counter_info[counter]
            metric_id = vim.PerformanceManager.MetricId(counterId=counter_key, instance="*")

            spec_list = []
            for i in obj:
                spec = vim.PerformanceManager.QuerySpec(
                    startTime=start_time,
                    endTime=end_time,
                    entity=i,
                    metricId=[metric_id],
                    maxSample=1,
                    intervalId=interval,
                )
                spec_list.append(spec)
            result = content.perfManager.QueryPerf(querySpec=spec_list)
            return {"result": True, "res": result}
        except Exception as e:
            logger.exception("monitor_data")
            return {"result": False, "message": str(e)}

    def get_metric_counter(self, metric):
        metric_mapping = {
            "cpu_usage_average": "cpu.usage.average",
            "cpu_usagemhz_average": "cpu.usagemhz.average",
            "mem_usage_average": "mem.usage.average",
            "mem_consumed_average": "mem.consumed.average",
            # "disk_used_average": "disk.used.average", #磁盘使用率,需要单独计算,暂不支持
            "disk_read_average": "disk.read.average",
            "disk_write_average": "disk.write.average",
            "disk_numberRead_summation": "disk.numberRead.summation",
            "disk_numberWrite_summation": "disk.numberWrite.summation",
            "disk_io_usage": "disk.usage.average",
            "net_bytesRx_average": "net.bytesRx.average",
            "net_bytesTx_average": "net.bytesTx.average",
            "disk_used_latest": "disk.used.latest",
            "disk_capacity_latest": "disk.capacity.latest",
            # 添加 VC 指标
            "disk_usage_percent": "disk.usage.average",
            "disk_free_space": "disk.free.average",
            "memory_usage_percent": "mem.usage.average",
            "memory_free_amount": "mem.freesize.average",
            "cpu_usage_percent": "cpu.usage.average",
            # 添加 ESXI Datastore 指标
            "datastore_io_read_latency": "datastore.totalReadLatency.average",
            "datastore_io_write_latency": "datastore.totalWriteLatency.average",
            "datastore_iops_read": "datastore.numberReadAveraged.average",
            "datastore_iops_write": "datastore.numberWriteAveraged.average",
            "datastore_throughput_read": "datastore.read.average",
            "datastore_throughput_write": "datastore.write.average",
            "net_usage_average": "net.usage.average",
            # 添加虚拟机磁盘指标
            "disk_io_read_latency": "virtualDisk.totalReadLatency.average",
            "disk_io_write_latency": "virtualDisk.totalWriteLatency.average",
        }
        return metric_mapping.get(metric)

    def _get_vm_disk_used_average(self, obj_list, obj_type="vm"):
        metric_data = {}
        if obj_type == "vm":
            for obj in obj_list:
                disks = obj.guest.disk
                all_disk_capacity = 0
                all_used_space = 0
                # 遍历磁盘信息列表，计算每个磁盘的使用率
                for disk in disks:
                    disk_capacity = disk.capacity / (1024 * 1024)  # 将磁盘容量转换为 MB
                    disk_free_space = disk.freeSpace / (1024 * 1024)  # 将可用磁盘空间转换为 MB
                    disk_used_space = disk_capacity - disk_free_space
                    all_disk_capacity += disk_capacity
                    all_used_space += disk_used_space
                if all_disk_capacity == 0:
                    disk_usage = 0
                else:
                    disk_usage = round((all_used_space / all_disk_capacity) * 100, 3)
                metric_data[obj._moId] = disk_usage
            return metric_data
        else:
            return metric_data

    def _get_vm_datastore_accessible(self, obj_list):
        metric_data = {}
        for obj in obj_list:
            metric_data[obj._moId] = int(obj.summary.accessible)
        return metric_data

    def _get_esxi_cpu_usage(self, data=None):
        metric_data = {}
        data = data or {}
        cpu_usagemhz = self.monitor_data("cpu.usagemhz.average", **data)
        if not cpu_usagemhz["result"]:
            return {}

        for index, host in enumerate(cpu_usagemhz["res"]):
            hardware = host.entity.hardware
            esxi_name = str(host.entity._moId)
            cpu_info = hardware.cpuInfo

            # 总 CPU 核心数和每核心 MHz
            num_cores = cpu_info.numCpuCores  # 总核心数
            cpu_mhz = cpu_info.hz // 10 ** 6

            # 总 CPU 频率（以 MHz 为单位）
            total_cpu_mhz = num_cores * cpu_mhz

            if not host.value:
                continue  # 继续下一个host而不是返回空字典

            timestamp = None  # 初始化timestamp变量
            for k, i in enumerate(host.sampleInfo):
                time_datetime = i.timestamp
                # 使用新的时区处理方法
                timestamp = self._convert_vmware_datetime_to_timestamp(time_datetime)

            if timestamp is None:
                continue  # 如果没有获取到timestamp，跳过这个host

            if total_cpu_mhz == 0:
                cpu_usage = 0
            else:
                # 计算 CPU 使用率
                cpu_usage = round(host.value[0].value[-1] / total_cpu_mhz * 100, 2)
            metric_data[esxi_name] = (cpu_usage, timestamp)

        return metric_data

    def _get_vm_datastore_disk(self, obj_list, metric, data=None):
        metric_data = {}
        data = data or {}
        used_latest_data = self.monitor_data("disk.used.latest", interval=300, **data)
        capacity_latest_data = self.monitor_data("disk.capacity.latest", interval=300, **data)
        if not all([capacity_latest_data["result"], used_latest_data["result"]]):
            return {}

        for index, used_latest in enumerate(used_latest_data["res"]):
            vm_name = str(used_latest.entity._moId)
            capacity_latest = capacity_latest_data["res"][index]
            if all(
                [
                    capacity_latest.value,
                    capacity_latest.value[0].value,
                    capacity_latest.value,
                    capacity_latest.value[0].value,
                ]
            ):
                lasted_used_value = used_latest.value[0].value[-1]
                lasted_capacity_value = capacity_latest.value[0].value[-1]
                if metric == "disk_used_average":
                    if lasted_used_value == 0:
                        value = 0
                    else:
                        value = float(round(lasted_used_value / lasted_capacity_value * 100, 3))
                elif metric == "disk_free_average":
                    value = float(round(lasted_capacity_value - lasted_used_value / (1024 * 1024), 3))
                else:
                    continue
                metric_data[vm_name] = value

        return metric_data

    def get_weops_monitor_data(self, **kwargs):  # noqa
        """
        Get monitor data from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        ------------------
        * StartTime: start time.(required)
        * EndTime: end time.(required)
        * resourceId: the ID of resource.(required)
        ------------------
        :rtype: dict
        """
        content = self.content
        now_time = datetime.datetime.now() + datetime.timedelta(minutes=-5)
        hour_time = datetime.datetime.now() + datetime.timedelta(hours=-1)
        data = {"StartTime": str(kwargs.get("StartTime", hour_time)), "EndTime": str(kwargs.get("EndTime", now_time))}

        resource_id_list = kwargs["resourceId"]
        if isinstance(resource_id_list, str):
            resource_id_list = resource_id_list.split(",")

        resources = kwargs.get("context", {}).get("resources", [])
        if not resources:
            return {"result": False, "message": "未获取到实例信息"}
        # 确定对象类型和指标
        obj_type, vim_obj_type, metrics = self._determine_object_type_and_metrics(resources, kwargs.get("Metrics"))
        # 分类指标
        batch_counters, special_metrics = self._categorize_metrics(metrics, obj_type)

        try:
            # 收集对象
            if obj_type == "vc":
                res = {resource_id_list[0]: {}}
                obj_list = [resource_id_list[0]]
                filter_obj_list = obj_list
                self._process_special_metrics(special_metrics, obj_type, obj_list, filter_obj_list, data, res)
                return {"result": True, "data": res}
            obj_list, res = self._collect_objects_by_ids(content, vim_obj_type, resource_id_list)
            if not obj_list:
                return {"result": False, "message": "未获取到监控信息"}

            # 过滤有效对象
            filter_obj_list = obj_list
            if obj_type == "vm":
                filter_obj_list = list(filter(lambda x: x.summary.runtime.powerState == "poweredOn", obj_list))

            # 处理特殊指标
            self._process_special_metrics(special_metrics, obj_type, obj_list, filter_obj_list, data, res)

            # 批量处理其他监控数据
            self._process_batch_monitoring_data(batch_counters, filter_obj_list, data, metrics, content, res)

            return {"result": True, "data": res}

        except Exception as e:
            logger.exception("get_weops_monitor_data")
            return {"result": False, "message": str(e)}

    def _determine_object_type_and_metrics(self, resources, metrics):
        """确定对象类型和默认指标"""
        if resources[0]["bk_obj_id"] == "vmware_esxi":
            return (
                "esxi",
                [vim.HostSystem],
                metrics
                or [
                    "cpu_usage_average",
                    "cpu_usagemhz_average",
                    "mem_usage_average",
                    "mem_consumed_average",
                    "disk_read_average",
                    "disk_write_average",
                    "net_bytesRx_average",
                    "net_bytesTx.average",
                    "disk_numberRead_summation",
                    "disk_numberWrite_summation",
                    # 添加新的 ESXI 相关指标
                    "datastore_io_read_latency",
                    "datastore_io_write_latency",
                    "datastore_iops_read",
                    "datastore_iops_write",
                    "datastore_throughput_read",
                    "datastore_throughput_write",
                    "net_usage_average",
                ],
            )
        elif resources[0]["bk_obj_id"] == "vmware_vc":
            # 新增 VC 对象类型
            return (
                "vc",
                ["VirtualCenter"],
                metrics
                or [
                    "disk_usage_percent",
                    "disk_free_space",
                    "memory_usage_percent",
                    "memory_free_amount",
                    "cpu_usage_percent",
                ],
            )
        elif resources[0]["bk_obj_id"] == "vmware_ds":
            return (
                "datastore",
                [vim.Datastore],
                metrics
                or [
                    "disk_used_average",
                    "disk_free_average",
                    "store_accessible",
                ],
            )
        else:
            return (
                "vm",
                [vim.VirtualMachine],
                metrics
                or [
                    "cpu_usage_average",
                    "cpu_usagemhz_average",
                    "mem_usage_average",
                    "mem_consumed_average",
                    "disk_used_average",
                    "disk_read_average",
                    "disk_write_average",
                    "net_bytesRx_average",
                    "net_bytesTx.average",  # 修复了这里的错误
                    "disk_numberRead_summation",
                    "disk_numberWrite_summation",
                    "disk_io_usage",
                    "power_state",
                    # 添加新的虚拟机相关指标
                    "disk_io_read_latency",
                    "disk_io_write_latency",
                ],
            )

    def _collect_objects_by_ids(self, content, obj_type, resource_id_list):
        """根据资源ID收集对象"""
        # 处理 vCenter 特殊情况
        if obj_type == "VirtualCenter":
            # 只返回单实例
            return
        container = content.viewManager.CreateContainerView(content.rootFolder, obj_type, True)
        obj_list = []
        res = {}

        for n in container.view:
            for i in resource_id_list:
                if n._moId == i:
                    obj_list.append(n)
                    res[i] = {}
        return obj_list, res

    def _categorize_metrics(self, metrics, obj_type):
        """将指标分类为批量获取和特殊处理两类"""
        batch_counters = []
        special_metrics = []

        special_metric_conditions = {
            ("vm", "power_state"): True,
            ("vm", "disk_used_average"): True,
            ("datastore", "store_accessible"): True,
            ("datastore", "disk_used_average"): True,
            ("datastore", "disk_free_average"): True,
            ("esxi", "cpu_usage_average"): True,
            # 添加 vCenter 特殊指标
            ("vc", "disk_usage_percent"): True,
            ("vc", "disk_free_space"): True,
            ("vc", "memory_usage_percent"): True,
            ("vc", "memory_free_amount"): True,
            ("vc", "cpu_usage_percent"): True,
        }

        for metric in metrics:
            if special_metric_conditions.get((obj_type, metric), False):
                special_metrics.append(metric)
            else:
                counter = self.get_metric_counter(metric)
                if counter:
                    batch_counters.append(counter)

        return batch_counters, special_metrics

    def _process_special_metrics(self, special_metrics, obj_type, obj_list, filter_obj_list, data, res):
        """处理特殊指标"""
        data["obj"] = filter_obj_list
        for metric in special_metrics:
            if metric == "power_state":
                self._process_power_state(obj_list, data, res)
            elif metric == "disk_used_average":
                if obj_type == "vm":
                    self._process_vm_disk_used_average(filter_obj_list, data, res)
                elif obj_type == "datastore":
                    self._process_datastore_disk(filter_obj_list, metric, data, res)
            elif metric == "disk_free_average" and obj_type == "datastore":
                self._process_datastore_disk(filter_obj_list, metric, data, res)
            elif metric == "store_accessible" and obj_type == "datastore":
                self._process_store_accessible(filter_obj_list, data, res)
            elif metric == "cpu_usage_average" and obj_type == "esxi":
                self._process_esxi_cpu_usage(data, res)
            elif obj_type == "vc":
                if metric in ["disk_usage_percent", "disk_free_space"]:
                    self._process_vc_disk_metrics(filter_obj_list, metric, data, res)
                elif metric in ["memory_usage_percent", "memory_free_amount"]:
                    self._process_vc_memory_metrics(filter_obj_list, metric, data, res)
                elif metric == "cpu_usage_percent":
                    self._process_vc_cpu_metrics(filter_obj_list, data, res)

    def _get_all_objects(self, vimtype):
        """获取指定类型的所有对象"""
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, [vimtype], True)
        objects = container.view
        container.Destroy()
        return objects

    def _process_vc_disk_metrics(self, filter_obj_list, metric, data, res):
        """处理 vCenter 磁盘相关指标"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000
        datastores = self._get_all_objects(vim.Datastore)
        total_capacity = 0
        free_space = 0
        used_space = 0
        for datastore in datastores:
            if datastore.summary.accessible:
                total_capacity += datastore.summary.capacity
                free_space += datastore.summary.freeSpace
                used_space = total_capacity - free_space

        if metric == "disk_usage_percent":
            if total_capacity > 0:
                usage_percent = (used_space / total_capacity) * 100
                res.setdefault(filter_obj_list[0], {}).setdefault(metric, []).append(
                    [timestamp, round(usage_percent, 2)]
                )

        elif metric == "disk_free_space":
            free_space_gb = free_space / (1024 * 1024 * 1024)
            res.setdefault(filter_obj_list[0], {}).setdefault(metric, []).append([timestamp, round(free_space_gb, 2)])

    def _process_vc_memory_metrics(self, filter_obj_list, metric, data, res):
        """处理 vCenter 内存相关指标，通过聚合 ESXi 主机的内存指标计算"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        # 获取所有ESXi主机的内存指标
        hosts = self._get_all_objects(vim.HostSystem)
        filter_hosts = [host for host in hosts if host.runtime.connectionState == "connected"]
        data["obj"] = filter_hosts
        # 使用现有方法获取内存使用率和消耗量
        mem_usage_data = self.monitor_data("mem.usage.average", **data)
        mem_consumed_data = self.monitor_data("mem.consumed.average", **data)

        if not all([mem_usage_data["result"], mem_consumed_data["result"]]):
            return

        total_memory = 0
        total_used_memory = 0

        # 计算总内存和使用量
        for host in filter_hosts:
            total_memory += host.hardware.memorySize

        # 处理监控数据
        if mem_consumed_data["res"]:
            for host_metrics in mem_consumed_data["res"]:
                if host_metrics.value:
                    memory_consumed = host_metrics.value[0].value[-1] * 1024  # 转换为字节
                    total_used_memory += memory_consumed

        # 计算总的剩余内存
        total_free_memory = total_memory - total_used_memory

        if metric == "memory_usage_percent":
            if total_memory > 0:
                usage_percent = (total_used_memory / total_memory) * 100
                res.setdefault(filter_obj_list[0], {}).setdefault(metric, []).append(
                    [timestamp, round(usage_percent, 2)]
                )

        elif metric == "memory_free_amount":
            free_memory_mb = total_free_memory / (1024 * 1024)  # 转换为 MB
            res.setdefault(filter_obj_list[0], {}).setdefault(metric, []).append([timestamp, round(free_memory_mb, 2)])

    def _process_vc_cpu_metrics(self, filter_obj_list, data, res):
        """处理 vCenter CPU 相关指标，通过聚合 ESXi 主机的 CPU 指标计算"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        # 获取所有ESXi主机
        hosts = self._get_all_objects(vim.HostSystem)
        filter_hosts = [host for host in hosts if host.runtime.connectionState == "connected"]
        data["obj"] = filter_hosts
        # 使用现有方法获取CPU使用率和MHz数据
        cpu_mhz_data = self.monitor_data("cpu.usagemhz.average", **data)

        if not cpu_mhz_data["result"]:
            return

        total_cpu_mhz = 0
        used_cpu_mhz = 0

        # 计算总CPU容量
        for host in filter_hosts:
            cpu_cores = host.hardware.cpuInfo.numCpuCores
            cpu_mhz = host.hardware.cpuInfo.hz / 1000000  # 转换为 MHz
            total_cpu_mhz += cpu_cores * cpu_mhz

        # 处理CPU MHz使用数据
        if cpu_mhz_data["res"]:
            for host_metrics in cpu_mhz_data["res"]:
                if host_metrics.value:
                    used_cpu_mhz += host_metrics.value[0].value[-1]

        # 计算总的CPU使用率
        if total_cpu_mhz > 0:
            usage_percent = (used_cpu_mhz / total_cpu_mhz) * 100
            res.setdefault(filter_obj_list[0], {}).setdefault("cpu_usage_percent", []).append(
                [timestamp, round(usage_percent, 2)]
            )

    def _process_vm_disk_used_average(self, filter_obj_list, data, res):
        """处理VM磁盘使用率指标"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        metric_data = self._get_vm_disk_used_average(filter_obj_list, obj_type="vm")
        for _obj, metric_value in metric_data.items():
            res.setdefault(_obj, {}).setdefault("disk_used_average", []).append([timestamp, metric_value])

    def _process_power_state(self, obj_list, data, res, metric=None):
        """处理电源状态指标"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        for obj in obj_list:
            res.setdefault(obj._moId, {}).setdefault("power_state", []).append(
                [timestamp, int(obj.summary.runtime.powerState == "poweredOn")]
            )

    def _process_store_accessible(self, filter_obj_list, data, res, metric=None):
        """处理存储可访问性指标"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        metric_data = self._get_vm_datastore_accessible(filter_obj_list)
        for _obj, metric_value in metric_data.items():
            res.setdefault(_obj, {}).setdefault("store_accessible", []).append([timestamp, metric_value])

    def _process_datastore_disk(self, filter_obj_list, metric, data, res):
        """处理数据存储磁盘指标"""
        # 使用新的时间转换方法
        timestamp = self._convert_server_time_to_timestamp(data["EndTime"]) * 1000

        metric_data = self._get_vm_datastore_disk(filter_obj_list, metric, data=data)
        for _obj, metric_value in metric_data.items():
            res.setdefault(_obj, {}).setdefault(metric, []).append([timestamp, metric_value])

    def _add_metric_value(self, vm_name, metric, value_info, k, timestamp, entity_result, res):
        """添加指标值到结果中"""
        no_dims = len(entity_result.value) == 1
        dims = None
        if not no_dims:
            instance = value_info.id.instance or entity_result.entity.name
            dims = (("instance", instance),)

        rate = value_info.value[k]
        if metric in ["cpu_usage_average", "mem_usage_average", "disk_io_usage"]:
            rate = rate / 100
        elif metric in ["mem_consumed_average"]:
            rate = rate / 1024
        _value = round(float(rate), 3)

        if not dims:
            res.setdefault(vm_name, {}).setdefault(metric, []).append([timestamp * 1000, _value])
        else:
            res.setdefault(vm_name, {}).setdefault(metric, {}).setdefault(dims, []).append([timestamp * 1000, _value])

    def _process_batch_monitoring_data(self, batch_counters, filter_obj_list, data, metrics, content, res):
        """处理批量监控数据"""
        if not (batch_counters and filter_obj_list):
            return True

        data["obj"] = filter_obj_list
        batch_result = self.monitor_data_batch(batch_counters, **data)

        if batch_result["result"]:
            return self._parse_batch_result(batch_result, metrics, content, res)
        else:
            logger.warning("Batch monitor data fetch failed, falling back to individual requests")
            return self._fallback_to_individual_requests(metrics, batch_counters, data, res)

    def _parse_batch_result(self, batch_result, metrics, content, res):
        """解析批量结果"""
        counter_to_metric = self._build_counter_to_metric_mapping(metrics, batch_result["counters"])
        counter_info = self._get_vmware_metrics(content)

        for n in batch_result["res"]:
            vm_name = str(n.entity._moId)
            if n.value:
                self._process_entity_values(n, vm_name, counter_info, counter_to_metric, res)
        return True

    def _build_counter_to_metric_mapping(self, metrics, valid_counters):
        """构建counter到metric的映射"""
        counter_to_metric = {}
        for metric in metrics:
            counter = self.get_metric_counter(metric)
            if counter and counter in valid_counters:
                counter_to_metric[counter] = metric
        return counter_to_metric

    def _process_entity_values(self, entity_result, vm_name, counter_info, counter_to_metric, res):
        """处理实体的监控值"""
        for k, sample_info in enumerate(entity_result.sampleInfo):
            time_datetime = sample_info.timestamp
            # 使用新的时区处理方法
            timestamp = self._convert_vmware_datetime_to_timestamp(time_datetime)

            for value_info in entity_result.value:
                counter_id = value_info.id.counterId
                counter_name = self._find_counter_name(counter_info, counter_id)

                if counter_name and counter_name in counter_to_metric:
                    metric = counter_to_metric[counter_name]
                    if k < len(value_info.value):
                        self._add_metric_value(vm_name, metric, value_info, k, timestamp, entity_result, res)

    def _find_counter_name(self, counter_info, counter_id):
        """根据counter ID查找counter名称"""
        for name, cid in counter_info.items():
            if cid == counter_id:
                return name
        return None

    def _fallback_to_individual_requests(self, metrics, batch_counters, data, res):
        """回退到单独请求"""
        special_metrics = ["power_state", "disk_used_average", "store_accessible"]

        for metric in metrics:
            if metric in special_metrics:
                continue

            counter = self.get_metric_counter(metric)
            if not counter:
                continue

            metric_result = self.monitor_data(counter, **data)
            if metric_result["result"]:
                self._process_individual_metric_result(metric_result, metric, res)
        return False

    def _process_individual_metric_result(self, metric_result, metric, res):
        """处理单个指标结果"""
        for n in metric_result["res"]:
            vm_name = str(n.entity._moId)
            if n.value:
                for k, sample_info in enumerate(n.sampleInfo):
                    time_datetime = sample_info.timestamp
                    # 使用新的时区处理方法
                    timestamp = self._convert_vmware_datetime_to_timestamp(time_datetime)

                    no_dims = len(n.value) == 1
                    for value_info in n.value:
                        dims = None
                        if not no_dims:
                            instance = value_info.id.instance or n.entity.name
                            dims = (("instance", instance),)

                        rate = value_info.value[k]
                        if metric in ["cpu_usage_average", "mem_usage_average", "disk_io_usage"]:
                            rate = rate / 100
                        elif metric in ["mem_consumed_average"]:
                            rate = rate / 1024
                        elif metric in ["esxi_sys_uptime_latest"]:
                            rate = rate / (60 * 60 * 24)  # 转换为天

                        _value = round(float(rate), 3)

                        if not dims:
                            res.setdefault(vm_name, {}).setdefault(metric, []).append([timestamp * 1000, _value])
                        else:
                            res.setdefault(vm_name, {}).setdefault(metric, {}).setdefault(dims, []).append(
                                [timestamp * 1000, _value]
                            )

    @classmethod
    def _get_vmware_metrics(cls, content):
        # create a mapping from performance stats to their counterIDs
        # counter_info: [performance stat => counterId]
        # performance stat example: cpu.usagemhz.LATEST
        perf_manager = content.perfManager
        counters = perf_manager.perfCounter
        counter_info = {}
        for counter in counters:
            counter_full_name = f"{counter.groupInfo.key}.{counter.nameInfo.key}.{counter.rollupType}"
            counter_info[counter_full_name] = counter.key
        return counter_info

    def _process_esxi_cpu_usage(self, data, res, metric=None):
        """处理ESXi CPU使用率指标"""
        metric_data = self._get_esxi_cpu_usage(data=data)
        for _obj, metric_value in metric_data.items():
            value, timestamp = metric_value
            res.setdefault(_obj, {}).setdefault("cpu_usage_average", []).append([timestamp * 1000, value])

    def _process_disk_used_average(self, filter_obj_list, data, res, metric=None):
        """处理磁盘使用率指标 - 保留向后兼容性"""
        # 这个方法保留用于向后兼容，新代码应该使用 _process_vm_disk_used_average
        self._process_vm_disk_used_average(filter_obj_list, data, res)

    def _convert_vmware_datetime_to_timestamp(self, vmware_datetime):
        """
        将VMware返回的带时区信息的datetime对象转换为时间戳
        :param vmware_datetime: VMware返回的datetime对象，可能带有tzinfo
        :return: Unix时间戳（秒）
        """
        if vmware_datetime.tzinfo is not None:
            # 如果datetime对象带有时区信息，先转换为UTC时间戳
            import calendar
            utc_timestamp = calendar.timegm(vmware_datetime.utctimetuple())
            return utc_timestamp
        else:
            # 如果没有时区信息，按本地时间处理
            return int(time.mktime(vmware_datetime.timetuple()))
