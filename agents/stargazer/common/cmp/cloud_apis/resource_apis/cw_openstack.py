# -*- coding: UTF-8 -*-
import datetime
import time

from cinderclient.v3 import client as cdclient
from glanceclient.v2 import client as glclient
from keystoneauth1 import session
from keystoneauth1.identity import v3
from keystoneclient.v3 import client as ksclient
from neutronclient.v2_0 import client as netclient
from novaclient import client as nvclient

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_constant import CloudPlatform, DiskType
from common.cmp.cloud_apis.constant import CloudResourceType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.utils import get_compute_price_module, get_storage_pricemodule
from core.logger import logger



class CwOpenstack(object):
    def __init__(self, username, password, region, host="", **kwargs):
        self.username = username
        self.password = password
        self.kwargs = kwargs
        self.host = host
        self.region_name = region
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not kwargs.get("port"):
            self.port = "35357"
        if not kwargs.get("version"):
            self.version = "v3"
        if not kwargs.get("project_id"):
            self.project_id = ""
        else:
            self.project_id = kwargs.pop("project_id")

        self.url = "http://" + self.host + ":" + str(self.port) + "/" + self.version
        auth = v3.Password(
            username=self.username,
            password=self.password,
            auth_url=self.url,
            project_domain_id="default",
            user_domain_id="default",
            project_id=self.project_id,
        )
        self.sess = session.Session(auth=auth)
        self.ops = Openstack(sess=self.sess, region_name=self.region_name, project_id=self.project_id, **self.kwargs)

    def __getattr__(self, item):
        self.ops.set_fuc_name(item)
        return self.ops


class Openstack(PrivateCloudManage):
    """
    This class providing all operations on openstack cloud platform.
    """

    def __init__(self, sess, region_name, project_id, **kwargs):
        """
        Initialize openstack object.
        :param sess: a session object to maintain client communication state
        :param name: calling method name
        :param region_name: openstack region name
        :param kwargs: accept multiple key value pair arguments.
        """
        self.sess = sess
        self.region_name = region_name
        self.project_id = project_id
        self.call_name = ""

        # cache object
        self.region_dict = None
        self.zone_dict = None
        self.disk_dict = None
        self.project_dict = None
        self.vm_dict = None
        self.snapshot_dict = None
        self.vpc_dict = None
        self.subnet_dict = None
        self.image_dict = None

        for k, v in kwargs.items():
            setattr(self, k, v)
        if "nova_version" not in kwargs:
            self.nova_version = "2"
        if "cinder_version" not in kwargs:
            self.cinder_version = "2"
        if "glance_version" not in kwargs:
            self.glance_version = "2"

        self.keystoneclient = ksclient.Client(session=sess)
        self.novaclient = nvclient.Client(self.nova_version, session=sess, region_name=self.region_name)
        self.cinderclient = cdclient.Client(self.cinder_version, session=sess, region_name=self.region_name)
        self.nuclient = netclient.Client(session=sess, region_name=self.region_name)
        self.glclient = glclient.Client(self.glance_version, session=sess, region_name=self.region_name)

    # find method name and exec it.
    def __call__(self, *args, **kwargs):
        return getattr(self, self.call_name, self._non_function)(*args, **kwargs)

    def set_fuc_name(self, name):
        self.call_name = name

    # if method name not found, then exec _non_function method.
    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        Check if this object works.
        use list_domains method to check.
        :return: A dict with a “key: value” pair of object. The key name is result, and the value is a boolean type.
        :rtype: dict
        """
        domain_rs_dict = self.list_domains()
        if domain_rs_dict["result"]:
            return {"result": True}
        else:
            return {"result": False}

    def __region_format(self, region_obj):
        if region_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.REGION.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(region_obj)
        else:
            return None

    def region_list(self):
        """
        get region list on openstack
        :param kwargs: any other attribute provided will be passed to the
                       server.
        :rtype: dict
        """
        region_list = []
        client = self.keystoneclient
        try:
            region_list = client.regions.list()
        except Exception:
            logger.exception("get region list from openstack sdk failed.")
        if self.region_dict is None:
            self.region_dict = {}
            for cur_region in region_list:
                self.region_dict[cur_region.id] = {"id": cur_region.id, "name": cur_region.id}
        return region_list

    def list_regions(self, resource_id="", **kwargs):
        """
        获取区域列表信息
        :param resource_id: 类型：str，区域id
        :param kwargs: 查询过滤字段
        :rtype: dict
        """
        region_list = self.region_list()
        if resource_id:
            data = [self.__region_format(cur_region) for cur_region in region_list if cur_region.id == resource_id]
        else:
            data = [self.__region_format(cur_region) for cur_region in region_list]
        return {"result": True, "data": data}

    def __zone_format(self, zone_obj):
        if zone_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.ZONE.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(zone_obj)
        else:
            return None

    def zone_list(self):
        """
        get zone list on openstack
        :rtype: dict
        """
        zone_list = []
        client = self.novaclient
        try:
            zone_list = client.availability_zones.list()
        except Exception as e:
            logger.exception("get zone list from openstack sdk failed." + str(e))
        if self.zone_dict is None:
            self.zone_dict = {}
            for cur_zone in zone_list:
                self.zone_dict[cur_zone.zoneName] = {"id": cur_zone.zoneName, "name": cur_zone.zoneName}
        return zone_list

    def list_zones(self, resource_id="", **kwargs):
        """
        get zone list on openstack
        :rtype: dict
        """
        zone_list = self.zone_list()
        if resource_id:
            data = [self.__zone_format(cur_zone) for cur_zone in zone_list if cur_zone.zoneName == resource_id]
        else:
            data = [self.__zone_format(cur_zone) for cur_zone in zone_list]
        return {"result": True, "data": data}

    def __find_domain(self, domain_id):
        domain_obj = None
        if domain_id:
            domain_obj_rs = self.list_domains()
            if domain_obj_rs["result"]:
                for cur_domain in domain_obj_rs["data"]:
                    if cur_domain.get("resource_id") == domain_id:
                        domain_obj = cur_domain
                        break
        return domain_obj

    def __project_format(self, project_obj):
        if project_obj:
            domain_obj = self.__find_domain(project_obj.domain_id)
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.PROJECT.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(project_obj, domain_obj=domain_obj)
        else:
            return None

    def project_list(self):
        """
        get project list on openstack
        :rtype: dict
        """
        project_list = []
        client = self.keystoneclient
        try:
            project_list = client.projects.list()
        except Exception as e:
            logger.exception("get project list from openstack sdk failed." + str(e))
        if self.project_dict is None:
            self.project_dict = {}
            for cur_project in project_list:
                self.project_dict[cur_project.id] = {"id": cur_project.id, "name": cur_project.name}
        return project_list

    def list_projects(self, resource_id="", **kwargs):
        """
        get project list on openstack
        :rtype: dict
        """
        project_list = self.project_list()
        if resource_id:
            data = [self.__project_format(cur_project) for cur_project in project_list if cur_project.id == resource_id]
        else:
            data = [self.__project_format(cur_project) for cur_project in project_list]
        if self.project_dict is None:
            self.project_dict = {}
            for cur_project in data:
                self.project_dict[cur_project["id"]] = {"id": cur_project["id"], "name": cur_project["name"]}
        return {"result": True, "data": data}

    def __domain_format(self, domain_obj):
        if domain_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.DOMAIN.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(domain_obj)
        else:
            return None

    def list_domains(self, resource_id="", **kwargs):
        """
        get domain list on openstack
        :rtype: dict
        """
        client = self.keystoneclient
        try:
            domain_list = client.domains.list()
        except Exception as e:
            logger.exception("get domain list from openstack sdk failed.")
            return {"result": False, "message": e.message}
        if resource_id:
            data = [self.__domain_format(cur_domain) for cur_domain in domain_list if cur_domain.id == resource_id]
        else:
            data = [self.__domain_format(cur_domain) for cur_domain in domain_list]
        return {"result": True, "data": data}

    def __find_project(self, project_id):
        project_obj = None
        if project_id:
            project_obj_rs = self.list_projects()
            if project_obj_rs["result"]:
                for cur_project in project_obj_rs["data"]:
                    if cur_project.resource_id == self.project_id:
                        project_obj = cur_project
                        break
        return project_obj

    def __flavor_detail_format(self, flavor_obj):
        if flavor_obj:
            if self.project_dict is None:
                self.project_list()
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.INSTANCE_TYPE.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(flavor_obj)
        else:
            return None

    def list_instance_types(self, ins_type_id=None, **kwargs):
        """
        get flavor list on cloud platforms
        :params: ins_type_id
        :rtype: dict
        """
        client = self.novaclient
        try:
            flavor_list = client.flavors.list()
        except Exception as e:
            logger.exception("get flavor list from openstack sdk failed.")
            return {"result": False, "message": e.message}
        if ins_type_id:
            return self.get_flavor_detail(ins_type_id)
        data = [self.__flavor_detail_format(cur_flavor) for cur_flavor in flavor_list]
        return {"result": True, "data": data}

    def get_flavor_detail(self, uuid):
        """
        Get a specific flavor.
        :param uuid: flavor universally unique identifier(uuid).
        :rtype: dict
        """
        client = self.novaclient
        try:
            flavor_obj = client.flavors.get(uuid)
        except Exception as e:
            logger.exception("get a specific flavor [uuid=" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": e.message}
        return {"result": True, "data": [self.__flavor_detail_format(flavor_obj)]}

    def get_specfic_flavor(self, **kwargs):
        """
        根据规格条件查询指定规格 详细参数查阅 List Flavors接口 无法精准查找
        Args:
            **kwargs ():
                minRam (int): 最小内存 MB
                minDisk (int): 最小磁盘容量  GB
        Returns:

        """
        client = self.novaclient
        minRam = kwargs.get("mem", "")
        # minDisk = kwargs.get("disk", 0)
        try:
            flavor_list = client.flavors.list(min_ram=minRam, sort_key="memory_mb")
        except Exception as e:
            logger.exception("openstack get_specific_flavors" + str(e))
            return {"result": False}
        # 对得到的结果进一步筛选
        data = [self.__flavor_detail_format(cur_flavor) for cur_flavor in flavor_list]
        res = self._filter_flavor(data, **kwargs)
        if res:
            return {"result": True, "data": res}
        else:
            return {"result": False}

    def _filter_flavor(self, data, **kwargs):
        """
        根据指定条件筛选规格
        Args:
            data (list): 待查询数据 格式参照 __flavor_detail_format()
            kwargs:
                mem ():
                cpu ():

        Returns:

        """
        mem = kwargs.get("mem", "")
        cpu = kwargs.get("cpu", "")
        for flavor in data:
            if flavor["mem"] == mem and flavor["vcpus"] == cpu:
                return flavor["id"]
        return None

    def create_flavor(self, **kwargs):
        """
        创建规格
        Args:
            **kwargs ():
                name:
                ram:
                vcpus:
                disk:
        Returns:

        """
        try:
            name = kwargs.get("name", "未命名")
            mem = kwargs.get("mem", 1)
            cpu = kwargs.get("cpu", 1)
            disk = kwargs.get("disk", 50)
            client = self.novaclient
            flavor_obj = client.flavors.create(name, mem, cpu, disk)
            return {"result": True, "data": flavor_obj.id}
        except Exception as e:
            logger.exception("opensatck create_flavor:" + str(e))
            return {"result": False, "message": str(e)}

    def vm_list(self):
        """
        Get vm list on cloud platforms
        :rtype: dict
        """
        vm_origin_list = []
        nova_client = self.novaclient
        try:
            vm_origin_list = nova_client.servers.list(search_opts={"all_tenants": True})
        except Exception as e:
            logger.exception("get vm list from openstack sdk failed." + str(e))
        if self.vm_dict is None:
            self.vm_dict = {}
            for cur_vm in vm_origin_list:
                self.vm_dict[cur_vm.id] = {"id": cur_vm.id, "name": cur_vm.name}

        return vm_origin_list

    def list_vms(self, ids="", **kwargs):
        """
        Get vm list on cloud platforms
        :rtype: dict
        """
        if ids:
            return self.get_vm_detail(ids[0])
        vm_origin_list = self.vm_list()
        return {
            "result": True,
            "data": [self.__vm_detail_format(cur_obj) for cur_obj in vm_origin_list],
            "total": len(vm_origin_list),
        }

    def __vm_detail_format(self, vm_obj):
        info = vm_obj._info
        flavor_obj = None
        if info["flavor"]:
            flavor_obj_rs = self.get_flavor_detail(info["flavor"]["id"])
            if flavor_obj_rs.get("result"):
                flavor_obj = flavor_obj_rs.get("data")[0]
        # handle image info
        image_id = vm_obj.image

        # handle netowrk info
        nic_list = []
        inner_ip_list = []
        out_ip_list = []
        for k, v in vm_obj.addresses.items():
            nic_obj = {"name": k}
            for n in v:
                nic_obj.update(
                    {
                        "type": n["OS-EXT-IPS:type"],
                        "version": n["version"],
                        "ip": n["addr"],
                        "mac": n["OS-EXT-IPS-MAC:mac_addr"],
                    }
                )
                if n["OS-EXT-IPS:type"] == "fixed":
                    inner_ip_list.append(n["addr"])
                else:
                    out_ip_list.append(n["floating"])
            nic_list.append(nic_obj)

        # handle disk info
        disk_list = []
        system_disk = {}
        snapshot_list = []

        if self.disk_dict is None:
            self.volume_list()

        if self.snapshot_dict is None:
            self.snapshot_list()

        if self.project_dict is None:
            self.project_list()

        disk_snp = {}
        for value_obj in self.snapshot_dict.values():
            if disk_snp.get(value_obj["volume_id"], None):
                disk_snp[value_obj["volume_id"]].append({"id": value_obj["id"], "name": value_obj["name"]})
            else:
                disk_snp[value_obj["volume_id"]] = [{"id": value_obj["id"], "name": value_obj["name"]}]

        for cur_volume in getattr(vm_obj, "os-extended-volumes:volumes_attached"):
            disk_obj = self.disk_dict.get(cur_volume.get("id"), None)
            if disk_obj:
                if disk_obj["disk_type"] == DiskType.SYSTEM_DISK.value:
                    system_disk = {"id": disk_obj["id"], "name": disk_obj["name"], "disk_size": disk_obj["disk_size"]}
                else:
                    disk_list.append(disk_obj["id"])
                cur_snp_list = disk_snp.get(disk_obj["id"], [])
                snapshot_list.extend(cur_snp_list)

        # handle security_groups
        security_group_info = []
        # print vm_obj.__dict__
        for cur_sg in getattr(vm_obj, "security_groups", []):
            sg_filter_list = self.__filter_security_group(vm_obj.tenant_id, name=cur_sg["name"])
            if sg_filter_list:
                security_group_info.append(sg_filter_list[0]["id"])
        return get_format_method(
            CloudPlatform.OpenStack, CloudResourceType.VM.value, project_id=self.project_id, region_id=self.region_name
        )(
            vm_obj,
            flavor_obj=flavor_obj,
            image_id=image_id,
            inner_ip_list=inner_ip_list,
            out_ip_list=out_ip_list,
            system_disk=system_disk,
            disk_list=disk_list,
            security_group_info=security_group_info,
        )

    def get_vm_detail(self, uuid):
        """
        Get a specific vm.
        :param uuid: vm universally unique identifier(uuid).
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            vm_obj = nova_client.servers.get(uuid)
        except Exception as e:
            logger.exception("get a specific vm [uuid" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": e.message}
        return {"result": True, "data": [self.__vm_detail_format(vm_obj)]}

    def create_vm(self, **kwargs):
        """
        Create a vm.
        :param kwargs: accept multiple key value pair arguments.
        -----------
        * name: vm name
        * flavor_id: flavor id
        * volume_boot: boot from volume (True | False)
        * image_id: if volume_boot is False, need to input image id
        * count: Specify to create more vms
        * volume_id: if volume_boot is True, need to input volume_id
        * source_type: if volume_boot is True, need to input source_type
          define volume source.
          (image | volume | volume_snapshot | image_snapshot)
        * system_volume_size: system disk. If volume_boot is True, need to input volume_size
        * delete_on_termination: if volume_boot is True, need to input
          delete_on_termination, to determine when delete vm, the vm volume
          is delete or not.

        * security_groups: Network security groups. list type(eg. ['af13a90d-f93f-48df-8d90-55077f94cfcf'].(Optional)
        * availability_zone: Availability zones to create vms. (Optional)
        * key_name: SSH keypairs. (Optional)

        # create vm and create a data volume attach to it.(add these params below.)
        * data_volume_size: data disk.
        * volume_availability_zone: volume availability zone to use.
        * project_id: project id.
        * data_volume_type: data volume type.
        :rtype: dict
        """
        client = self.novaclient
        try:
            flavor = client.flavors.get(kwargs.get("flavor_id", ""))
        except Exception as e:
            logger.exception("get a specific flavor [uuid" + kwargs.get("flavor_id") + "] from openstack sdk failed.")
            return {"result": False, "message": e.message}
        vm_dict = {"name": kwargs.get("name", ""), "flavor": flavor, "min_count": kwargs.get("count", "1")}
        network_list = []
        for i in kwargs.get("network_list", []):
            network_list.append({"v4-fixed-ip": i.get("fixed-ip", ""), "net-id": i.get("net-id", "")})
        vm_dict.update({"nics": network_list})
        if kwargs.get("security_groups"):
            vm_dict.update({"security_groups": kwargs.get("security_groups", [])})
        if kwargs.get("availability_zone"):
            vm_dict.update({"availability_zone": kwargs.get("availability_zone")})
        if kwargs.get("key_name"):
            vm_dict.update({"key_name": kwargs.get("key_name")})

        if kwargs.get("volume_boot") is True:
            block_device_mapping_v2 = [{}]
            block_device_mapping_v2[0].update(
                {
                    "boot_index": 0,
                    "source_type": kwargs.get("source_type"),
                    "volume_size": kwargs.get("system_volume_size"),
                    "delete_on_termination": kwargs.get("delete_on_termination"),
                    "destination_type": "volume",
                }
            )
            if kwargs.get("source_type") == "image" or kwargs.get("source_type") == "image_snapshot":
                block_device_mapping_v2[0].update({"uuid": kwargs.get("image_id"), "source_type": "image"})
            if kwargs.get("source_type") == "volume":
                block_device_mapping_v2[0].update({"uuid": kwargs.get("volume_id")})
            if kwargs.get("source_type") == "volume_snapshot":
                block_device_mapping_v2[0].update({"uuid": kwargs.get("volume_snapshot_id"), "source_type": "snapshot"})

            vm_dict.update({"block_device_mapping_v2": block_device_mapping_v2, "image": None})
        else:
            try:
                image = client.glance.find_image(kwargs.get("image_id" ""))
            except Exception as e:
                logger.exception("get a specific image [uuid" + kwargs.get("image_id") + "] from openstack sdk failed.")
                return {"result": False, "message": e.message}
            vm_dict.update({"image": image})
        vm_res = client.servers.create(**vm_dict)
        ins_id = vm_res.id
        check_time = 15
        while check_time:
            ins_info = client.servers.get(ins_id)
            status = ins_info.status
            if status == "ACTIVE":
                if not (kwargs.get("data_volume_size", "") == 0 or kwargs.get("data_volume_size", "") == ""):
                    try:
                        volume_id = self.create_disk(
                            **{
                                "project_id": kwargs.get("project_id", ""),
                                "availability_zone": kwargs.get("volume_availability_zone", ""),
                                "size": kwargs.get("data_volume_size", ""),
                                "volume_type": kwargs.get("data_volume_type", ""),
                            }
                        )["data"]
                    except Exception as e:
                        logger.error(str(e))
                        time.sleep(30)
                        check_time = check_time - 1
                        if check_time == 0:
                            return {"result": False}
                        continue
                    time.sleep(30)
                    self.attach_disk(**{"instance_uuid": ins_id, "volume": volume_id})
                    break
                else:
                    break
            else:
                check_time = check_time - 1
                if check_time == 0:
                    return {"result": False}
                time.sleep(60)
        return {"result": True, "data": ins_id}

    def start_vm(self, vm_id):
        """
        Start a vm.
        :param vm_id: vm id or the :class:`Server`.
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.servers.start(vm_id)
            return {"result": True}
        except Exception as e:
            logger.exception("start a specific vm [" + vm_id + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def stop_vm(self, vm_id):
        """
        Stop a vm.
        :param vm_id: vm id or the :class:`Server`.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.servers.stop(vm_id)
            return {"result": True}
        except Exception as e:
            logger.exception("stop a specific vm [" + vm_id + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def restart_vm(self, vm_id, **kwargs):
        """
        Reboot a vm.
        :param vm_id: vm id or the :class:`Server`.
        :param kwargs: accept multiple key value pair arguments.
        -----------
        * reboot_type: 'SOFT'|'HARD' (default: 'SOFT', Optional)
        -----------
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.servers.reboot(vm_id, **kwargs)
            return {"result": True}
        except Exception as e:
            logger.exception("reboot a specific vm [" + vm_id + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def modify_vm(self, uuid=None, **kwargs):
        """
        Resize a vm.
        :param uuid: vm id or the :class:`Server`.
        :param kwargs: accept multiple key value pair arguments.
        -------------
        flavor: flavor id.(required)
        disk_config: partitioning mode to use on the rebuilt server.
                            Valid values are 'AUTO' or 'MANUAL'(optional)
        -------------
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            vm_obj = nova_client.servers.get(uuid)
        except Exception as e:
            logger.exception("find a specific vm [" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        try:
            original_flavor = nova_client.flavors.get(vm_obj._info["flavor"]["id"])
        except Exception as e:
            logger.exception("find an old flavor [" + vm_obj._info["flavor"]["id"] + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        try:
            new_flavor = nova_client.flavors.get(kwargs.get("flavor"))
        except Exception as e:
            logger.exception("find a new flavor [" + vm_obj._info["flavor"]["id"] + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        if new_flavor._info["disk"] < original_flavor._info["disk"]:
            return {"result": False, "message": "磁盘不能调整到更小的规格！"}
        try:
            nova_client.servers.resize(uuid, **kwargs)
        except Exception as e:
            logger.exception(
                "resize a specific vm ["
                + uuid
                + "] to a specific flavor["
                + kwargs.get("flavor")
                + "] from openstack sdk failed."
            )
            return {"result": False, "message": str(e)}
        check_time = 15
        while check_time:
            time.sleep(15)
            cur_vm_obj = nova_client.servers.get(uuid)
            if cur_vm_obj._info["status"] == "VERIFY_RESIZE":
                nova_client.servers.confirm_resize(uuid)
                return {"result": True, "data": uuid}
            else:
                check_time = check_time - 1
                if check_time == 0:
                    return {"result": False, "message": "只有虚拟机状态为verify_resize，才能调整大小！"}

    def destroy_vm(self, vm_id=None):
        """
        Destroy a vm.
        :param vm_id: vm id or the :class:`Server`.
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.servers.delete(vm_id)
            return {"result": True}
        except Exception as e:
            logger.exception("delete a specific vm [" + vm_id + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def get_available_specs(self, **kwargs):
        """
        Get available specs.
        :param kwargs: accept multiple key value pair arguments.
        -------------
        * config: list value(two values. the first value is cpu number, the second value is memory size.)(required)
                    eg.
                        config = [4, 2048]
        -------------
        :rtype: dict
        """
        nova_client = self.novaclient
        kwargs["CPU"] = int(kwargs["config"][0])
        kwargs["Memory"] = float(kwargs["config"][1])
        try:
            flavor_list = nova_client.flavors.list()
        except Exception as e:
            logger.exception("get flavor list from openstack sdk failed.")
            return {"result": False, "message": e.message}
        for cur_flavor in flavor_list:
            if cur_flavor.vcpus == kwargs["CPU"] and float(cur_flavor.ram) / 1024 == kwargs["Memory"]:
                return {"result": True, "data": cur_flavor.id}
        return {"result": False, "message": "openstack没有匹配的规格。"}

    def add_vm_disk(self, **kwargs):
        """
        Create a disk and attach to a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * size: create volume size.(required)
        * server_id: The ID of the server.(required)
        * volume_type: volume type.(Optional)
        * device: The device name (optional)
        --------------
        :rtype: dict
        """
        cinder_client = self.cinderclient
        disk_args = {"size": kwargs.get("size", 1)}
        if kwargs.get("volume_type"):
            disk_args.update({"volume_type": kwargs.get("volume_type")})
        create_disk_rs = self.create_disk(**disk_args)
        if create_disk_rs["result"]:
            volume_id = create_disk_rs["data"]
            check_time = 30
            while check_time:
                time.sleep(5)
                cur_volume_status = cinder_client.volumes.get(volume_id).status
                if cur_volume_status == "available":
                    attach_disk_args = {"server_id": kwargs.get("server_id"), "volume_id": volume_id}
                    if kwargs.get("device"):
                        attach_disk_args.update({"device": kwargs.get("device")})
                    return self.attach_disk(**attach_disk_args)
                elif cur_volume_status == "error":
                    return {"result": False, "message": "创建磁盘失败！"}
                else:
                    check_time = check_time - 1
                    if check_time == 0:
                        return {"result": False, "message": "创建磁盘超时！"}
        else:
            return {"result": False, "message": "创建磁盘失败！"}

    def remote_connect_vm(self, **kwargs):
        """
        Connect to a remote vm desktop.
        :param kwargs: accept multiple key value pair arguments.
        ------------
        * uuid: vm id or the :class:`Server`.(required)
        * console_type: Type of vnc console to get ('novnc' or 'xvpvnc').
                        Defult: 'novnc'.
        ------------
        :rtype: dict
        """
        nova_client = self.novaclient
        if not kwargs.get("uuid"):
            return {"result": False, "message": "非法请求，请传入待查找VM的uuid！"}
        vnc_args = {"server": kwargs.get("uuid"), "console_type": kwargs.get("console_type", "novnc")}
        try:
            vnc_obj = nova_client.servers.get_vnc_console(**vnc_args)
            return {"result": True, "data": {"url": vnc_obj["console"]["url"], "uuid": kwargs.get("uuid")}}
        except Exception as e:
            logger.exception("get vnc url failed.[" + kwargs.get("uuid") + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    # 仅列出共享磁盘
    def get_vm_disks(self, uuid):
        """
        Get all volumes from a specific VM instance.
        :param uuid: the ID of a specific vm.
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            vm_obj = nova_client.servers.get(uuid)
        except Exception as e:
            logger.exception("get a specific vm[" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        volume_obj_list = getattr(vm_obj, "os-extended-volumes:volumes_attached")
        disk_detail_list = []
        for cur_volume_obj in volume_obj_list:
            disk_detail_rs = self.get_disk_detail(cur_volume_obj.get("id"))
            if disk_detail_rs["result"]:
                disk_detail_list.append(disk_detail_rs["data"])
        return {"result": True, "data": disk_detail_list}

    def associate_security_groups(self, **kwargs):
        """
        给实例绑定安全组
        :param kwargs:
            server_id: 弹性云服务器id
            security_group_id: string 安全组id
        :type kwargs:
        :return:
        :rtype:
        """
        client = self.novaclient
        server_id = kwargs.get("server_id", "")
        security_group_id = kwargs.get("security_group_id", "")
        try:
            client.servers.add_security_group(server_id, security_group_id)
            return {"result": True}
        except Exception as e:
            logger.exception("vm_add_security_group")
            logger.exception(e)
            message = str(e)
            if str(e).startswith("Invalid input for security_groups. Reason: Duplicate items in the list"):
                message = "该实例已绑定当前安全组，请同步本地数据"
            return {"result": False, "message": message}

    def disassociate_security_groups(self, **kwargs):
        """
        给实例绑解绑安全组
        :param kwargs:
            server_id: vm id
            security_group_id: string 安全组id
        :type kwargs:
        :return:
        :rtype:
        """
        client = self.novaclient
        server_id = kwargs.get("server_id", "")
        security_group_id = kwargs.get("security_group_id", "")
        try:
            client.servers.remove_security_group(server_id, security_group_id)
            return {"result": True}
        except Exception as e:
            logger.exception("vm_remove_security_group")
            message = str(e)
            if str(e).startswith("Invalid input for security_groups. Reason: Duplicate items in the list"):
                message = "该实例已绑定当前安全组，请同步本地数据"
            return {"result": False, "message": message}

    # ------------------***** snapshot *****------------------
    def __snapshot_format(self, snapshot_obj):
        if snapshot_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.SNAPSHOT.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(snapshot_obj, disk_id=snapshot_obj.volume_id)
        else:
            return None

    def create_snapshot(self, **kwargs):
        """
        Create a snapshot of the given volume.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * uuid: The ID of the volume to snapshot.(required)
        * name: Name of the snapshot.(required)
        * description: Description of the snapshot.(optional)
        --------------
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            snapshot_obj = cinder_client.volume_snapshots.create(
                kwargs.get("uuid", ""),
                force=True,
                name=kwargs.get("name", ""),
                description=kwargs.get("description", None),
            )
        except Exception as e:
            return {"result": False, "message": str(e)}
        return {"result": True, "data": snapshot_obj.id}

    def delete_snapshot(self, snapshot_id):
        """
        Delete a specific disk snapshot.
        :param snapshot_id: the ID of a specific snapshot.
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            volume_snapshot_obj = cinder_client.volume_snapshots.get(snapshot_id)
            cinder_client.volume_snapshots.delete(volume_snapshot_obj)
        except Exception as e:
            logger.exception("delete a specific volume snapshot[" + snapshot_id + "]from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True}

    def snapshot_list(self):
        """
        Get all volume snapshot list.
        :rtype: dict
        """
        volume_snapshot_list = []
        cinder_client = self.cinderclient
        try:
            volume_snapshot_list = cinder_client.volume_snapshots.list()
        except Exception as e:
            logger.exception("get volume snapshot list from openstack sdk failed." + str(e))
        if self.snapshot_dict is None:
            self.snapshot_dict = {}
            for cur_snp in volume_snapshot_list:
                self.snapshot_dict[cur_snp.id] = {
                    "id": cur_snp.id,
                    "name": cur_snp.name,
                    "volume_id": cur_snp.volume_id,
                }
        return volume_snapshot_list

    def list_snapshots(self, ids="", **kwargs):
        """
        Get all volume snapshot list.
        :rtype: dict
        """
        volume_snapshot_list = self.snapshot_list()
        if ids:
            data = [self.__snapshot_format(cur_vs) for cur_vs in volume_snapshot_list if ids[0] == cur_vs.id]
        else:
            data = [self.__snapshot_format(cur_vs) for cur_vs in volume_snapshot_list]
        return {"result": True, "data": data}

    def get_disk_snapshot_detail(self, uuid=None, snapshot_id=None):
        """
        Get snapshot list from a specific volume.
        :param uuid: The UUID of the volume.
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            volume_snapshot_list = cinder_client.volume_snapshots.list()
        except Exception as e:
            logger.exception("get volume snapshot list from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        if snapshot_id:
            disk_snapshot_list = [
                self.__snapshot_format(cur_snapshot)
                for cur_snapshot in volume_snapshot_list
                if cur_snapshot.id == snapshot_id
            ]
        else:
            disk_snapshot_list = [
                self.__snapshot_format(cur_snapshot)
                for cur_snapshot in volume_snapshot_list
                if cur_snapshot.volume_id == uuid
            ]
        return {"result": True, "data": disk_snapshot_list}

    def snapshot_recovery(self, **kwargs):
        """
        Revert a volume to a snapshot.
        API version '3.0' is not supported on 'cinderclient.v3.volumes.revert_to_snapshot' method.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * volume_id: the ID of a specific vm.(required)
                     type: str
        * snapshot_id: the ID of a specific snapshot.(required)
                       type: str
        --------------
        :rtype: dict
        """
        volume_id = kwargs.get("volume_id", "")
        snapshot_id = kwargs.get("snapshot_id", "")
        cinder_client = self.cinderclient
        try:
            volume_obj = cinder_client.volumes.get(volume_id)
            snapshot_obj = cinder_client.volume_snapshots.get(snapshot_id)
            res = cinder_client.volumes.revert_to_snapshot(volume_obj, snapshot_obj)
        except Exception as e:
            logger.exception("Revert a volume to a snapshot failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": res}

    def vm_snapshot_recovery(self, uuid, **kwargs):
        """
        recovery vm from a specific snapshot.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * image: the :class:`Image` (or its ID) to re-image with.(required)
                 type: str
        --------------
        :return: dict
        """
        nova_client = self.novaclient
        try:
            vm_obj = nova_client.servers.rebuild(server=uuid, image=kwargs.get("image", ""))
        except Exception as e:
            logger.exception(
                "rebuild a specific vm["
                + uuid
                + "] from a specific snapshot["
                + kwargs.get("image")
                + "] by openstack sdk failed."
            )
            return {"result": False, "message": str(e)}
        return {"result": True, "data": vm_obj._info}

    # ------------------***** tag *****------------------
    def create_tag(self, **kwargs):
        """
        Create a tag.
        :param kwargs: accept multiple key value pair arguments.
        :return:
        """
        return {"result": False, "message": "openstack无标签创建功能！"}

    def delete_tag(self, **kwargs):
        """
        Delete a tag.
        :param kwargs:
        :return: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "openstack无标签删除功能！"}

    def update_tag(self, uuid, **kwargs):
        """
        Update key-value of a tag.
        :param uuid: tag universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "openstack无标签更新功能！"}

    def get_tags(self, **kwargs):
        """
        Get tag list on cloud platforms.
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        return {"result": False, "message": "openstack无获取标签列表功能！"}

    def remove_resource_tag(self, uuid, **kwargs):
        """
        Delete a specific tag from a specific resource.
        :param uuid: the ID of resource
        :param kwargs: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "openstack无删除指定资源的标签创建功能！"}

    def get_resource_tags(self, uuid, **kwargs):
        """
        Get all tags from a specific resource.
        :param uuid: the ID of resource
        :param kwargs: accept multiple key value pair arguments.
        """
        return {"result": False, "message": "openstack无获取指定资源的标签功能！"}

    # ------------------***** storage *****-------------------
    def __disk_format(self, disk_obj):
        if disk_obj:
            if self.project_dict is None:
                self.project_list()
            if self.disk_dict is None:
                self.volume_list()
            cur_disk_dict = self.disk_dict.get(disk_obj.id, {})
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.DISK.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(disk_obj, cur_disk_dict=cur_disk_dict)

        else:
            return None

    def volume_list(self):
        """
        Get volume list on cloud platforms.
        :rtype: dict
        """
        volume_list = []
        client = self.cinderclient
        try:
            volume_list = client.volumes.list()
        except Exception:
            logger.exception("get volume list from openstack sdk failed.")
        if self.disk_dict is None:
            self.disk_dict = {}
            for cur_disk in volume_list:
                is_attached = False
                vm_id = None
                vm_name = None
                if cur_disk.attachments:
                    is_attached = True
                    vm_id = cur_disk.attachments[0].get("server_id")
                    if self.vm_dict is None:
                        self.vm_list()
                    vm_obj = self.vm_dict.get(vm_id, None)
                    if vm_obj:
                        vm_name = vm_obj["name"]

                disk_type = DiskType.DATA_DISK.value
                if cur_disk.bootable == "true":
                    disk_type = DiskType.SYSTEM_DISK.value
                self.disk_dict[cur_disk.id] = {
                    "id": cur_disk.id,
                    "name": cur_disk.name,
                    "disk_type": disk_type,
                    "disk_size": cur_disk.size,
                    "is_attached": is_attached,
                    "vm_id": vm_id,
                    "vm_name": vm_name,
                }
        return volume_list

    def list_disks(self, ids="", **kwargs):
        """
        Get disk list on cloud platforms.
        :rtype: dict
        """
        volume_list = self.volume_list()
        if ids:
            return self.get_disk_detail(ids[0])
        data = [self.__disk_format(cur_volume) for cur_volume in volume_list]
        return {"result": True, "data": data}

    def get_disk_detail(self, uuid):
        """
        Get a specific disk.
        :param uuid: disk universally unique identifier(uuid).
        :rtype: dict
        """
        client = self.cinderclient
        try:
            volume_obj = client.volumes.get(uuid)
        except Exception as e:
            logger.exception("get a specific volume [uuid" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": e.message}
        return {"result": True, "data": [self.__disk_format(volume_obj)]}

    def create_disk(self, **kwargs):
        """
        Create a disk.
        :param kwargs: accept multiple key value pair arguments.
        -----------
        * size: create disk size.
        * project_id: project id.
        * availability_zone: volume availability zone to use.
        * volume_type: volume type.
        * name: Name of the volume.(optional)
        * description: volume description.(optional)
        * scheduler_hints: (optional extension) arbitrary key-value pairs
                            specified by the client to help boot an instance
        ------------
        :rtype: dict
        """
        if not kwargs.get("project_id", None):
            kwargs["project_id"] = self.project_id
        cinder_client = self.cinderclient
        try:
            volume_obj = cinder_client.volumes.create(**kwargs)
        except Exception as e:
            logger.exception("create a volume from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": volume_obj.id}

    def attach_disk(self, **kwargs):
        """
        Attach a specific disk to a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        -----------
        * server_id: The ID of the server.
        * volume_id: The ID of the volume to attach.
        * device: The device name (optional)
        -----------
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.volumes.create_server_volume(**kwargs)
            return {"result": True}
        except Exception as e:
            logger.exception("attach a specific volume to a specific vm from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def detach_disk(self, **kwargs):
        """
        Detach a specific disk from a specific vm.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * server_id: The ID of the server.(required)
        * volume_id: The ID of the volume.(required)
        --------------
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            nova_client.volumes.delete_server_volume(**kwargs)
        except Exception as e:
            logger.exception("detach a specific volume to a specific vm from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True}

    def delete_disk(self, disk_id):
        """
        Delete a specific disk
        :param disk_id: disk id.
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            volume_obj = cinder_client.volumes.get(disk_id)
            if volume_obj.status != "in-use":
                cinder_client.volumes.delete(volume_obj)
                return {"result": True}
            else:
                return {"result": False, "message": "删除失败！不能删除挂载的磁盘！"}
        except Exception as e:
            logger.exception("delete a specific volume to a specific vm from openstack sdk failed.")
            return {"result": False, "message": str(e)}

    def extend_disk(self, uuid, **kwargs):
        """
        extend a specific disk
        :param uuid: The UUID of the volume to extend.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * new_size: The requested size to extend volume to.(required)
        --------------
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            volume_obj = cinder_client.volumes.get(uuid)
            if volume_obj.status != "available":
                return {"result": False, "message": "openstack扩容的磁盘必须是可用状态！"}
            if volume_obj.size >= kwargs.get("new_size", -1):
                return {"result": False, "message": "扩容磁盘新的容量必须比当前磁盘容量大！"}
            cinder_client.volumes.extend(uuid, kwargs.get("new_size", -1))
        except Exception as e:
            logger.exception("extend a specific disk from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True}

    def list_images(self, resource_id="", **kwargs):
        """
        Get image list.
        :rtype: dict
        """
        if resource_id:
            return self.get_image_detail(resource_id)
        nova_client = self.novaclient
        try:
            glance_list = nova_client.glance.list()
        except Exception as e:
            logger.exception("get image list from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        tem_info_list = []
        for i in glance_list:
            tem_info_list.append(self.__image_format(i))
        return {"result": True, "data": tem_info_list}

    def get_image_detail(self, uuid):
        """
        Get a specific image.
        :param uuid: image universally unique identifier(uuid).(name or id)
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            glance_obj = nova_client.glance.find_image(uuid)
            return {"result": True, "data": [self.__image_format(glance_obj)]}
        except Exception as e:
            logger.exception("get a specific image[{}] from openstack sdk failed.".format(uuid))
            return {"result": False, "message": str(e)}

    def __image_format(self, glance_obj):
        if glance_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.IMAGE.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(glance_obj)
        else:
            return None

    def destroy_image(self, uuid):
        """
        Delete a specific image.
        :param uuid: image universally unique identifier(uuid).
        :rtype: dict
        """
        glance_client = self.glclient
        try:
            glance_client.images.delete(uuid)
        except Exception as e:
            logger.exception("delete a specific image[" + uuid + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True}

    # ------------------***** network *****-------------------
    def __get_security_groups_origin(self, **kwargs):
        """
        Get security group list.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        none
        ---------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        security_group_obj = []
        try:
            security_group_obj = neutron_client.list_security_groups(**kwargs)
        except Exception:
            logger.exception("get security group list from openstack sdk failed. ")
        return security_group_obj and security_group_obj["security_groups"]

    def __filter_security_group(self, project_id, **kwargs):
        """
        Search a specific security group.
        :param project_id: the ID of a specific project.
        :param kwargs: accept multiple key value pair arguments.
        ----------------------------
        name: the Name of a security group.(optional)
              type: str
        id: the ID of a security group.(optional)
            type: str
        ----------------------------
        :return:
        """
        security_group_list = self.__get_security_groups_origin()
        sg_filter = []
        for cur_sg in security_group_list:
            if (
                project_id == cur_sg.get("project_id")
                and cur_sg.get("id") == kwargs.get("id", cur_sg.get("id"))
                and cur_sg.get("name") == kwargs.get("name", cur_sg.get("name"))
            ):
                sg_filter.append(cur_sg)
        return sg_filter

    def list_security_groups(self, ids=None, **kwargs):
        if ids:
            return self.get_security_group_detail(ids[0])
        security_group_list = self.__get_security_groups_origin(**kwargs)
        return {"result": True, "data": [self.__security_groups_format(cur_sg) for cur_sg in security_group_list]}

    def __security_groups_format(self, security_group):
        if security_group:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.SECURITY_GROUP.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(security_group)
        else:
            return None

    def get_security_group_detail(self, uuid, **kwargs):
        """
        Get a specific security group.
        :param uuid: uuid: security group universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        none
        --------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            security_group_obj = neutron_client.show_security_group(uuid, **kwargs)
        except Exception as e:
            logger.exception("get a specific security group[{}] from openstack sdk failed.".format(uuid))
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [self.__security_groups_format(security_group_obj["security_group"])]}

    def delete_security_group(self, security_group_id):
        """
        Delete a specific security group.
        :param security_group_id: uuid: security group universally unique identifier(uuid).
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            neutron_client.delete_security_group(security_group_id)
        except Exception as e:
            logger.exception("delete a specific security group[" + security_group_id + "] from openstack sdk failed. ")
            message = str(e)
            if "in use" in str(e):
                message = "安全组已和实例绑定，无法删除。请先解除绑定！"
            return {"result": False, "message": message}
        return {"result": True}

    def create_security_group(self, **kwargs):
        """
        Create a specific security group.
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * name: security group name(required)
        * description: A human-readable description for the resource. Default is an empty string.(Optional)
        --------------
        :rtype: dict
        """
        if not kwargs.get("name"):
            return {"result": False, "message": "参数name的值不能为空！"}
        body_args = {"security_group": {"name": kwargs.get("name"), "description": kwargs.get("description", "")}}
        neutron_client = self.nuclient
        try:
            security_group_obj = neutron_client.create_security_group(body=body_args)
        except Exception as e:
            logger.exception("create a specific security group from openstack sdk failed. ")
            message = str(e)
            if str(e).startswith("Quota exceeded for resources"):
                message = "创建失败，安全组配额已达到最大限制！"
            return {"result": False, "message": message}
        return {"result": True, "data": security_group_obj["security_group"]["id"]}

    def modify_security_group(self, uuid, **kwargs):
        """
        Modify a specific security group.
        :param uuid: uuid: security group universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        * name: new name of security group.
        * description: new description info for security group.
        --------------
        :rtype: dict
        """
        body_args = {"security_group": {"name": kwargs.get("name", ""), "description": kwargs.get("description", "")}}
        neutron_client = self.nuclient
        try:
            security_group_obj = neutron_client.update_security_group(uuid, body=body_args)
        except Exception as e:
            logger.exception("update a specific security group from openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": security_group_obj}

    def list_security_group_rules(self, security_group_id="", **kwargs):
        """
        Get a specific rule info from a specific security group.
        :param security_group_id: uuid: security group universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            security_group_rule_obj = neutron_client.list_security_group_rules(security_group_id=security_group_id)
        except Exception as e:
            logger.exception(e)
            return {"result": False, "message": "获取安全组规则失败"}
        rule_data = []
        for rule in security_group_rule_obj["security_group_rules"]:
            rule_data.append(
                get_format_method(
                    CloudPlatform.OpenStack,
                    CloudResourceType.SECURITY_GROUP_RULE.value,
                    project_id=self.project_id,
                    region_id=self.region_name,
                )(rule)
            )
        return {"result": True, "data": rule_data}

    def create_security_group_rule(self, **kwargs):
        """
        Create a specific rule from a specific security group.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * remote_group_id: The remote group UUID to associate with this security group rule. You can specify either the
                           remote_group_id or remote_ip_prefix attribute in the request body.(Optional)
        * direction: "ingress" | "egress", which is the direction in which the security group rule is applied.(required)
        * protocol: The IP protocol can be represented by a string, an integer, or null. Valid string or integer values
                    are any or 0, ah or 51, dccp or 33, egp or 8, esp or 50, gre or 47, icmp or 1, icmpv6 or 58, igmp or
                    2, ipip or 4, ipv6-encap or 41, ipv6-frag or 44, ipv6-icmp or 58, ipv6-nonxt or 59, ipv6-opts or 60,
                    ipv6-route or 43, ospf or 89, pgm or 113, rsvp or 46, sctp or 132, tcp or 6, udp or 17, udplite or
                    136, vrrp or 112. Additionally, any integer value between [0-255] is also valid. The string any
                    (or integer 0) means all IP protocols. See the constants in neutron_lib.constants for the most
                    up-to-date list of supported strings.(Optional)
        * ethertype: Must be IPv4 or IPv6, and addresses represented in CIDR must match the ingress or egress
                     rules.(Optional)
        * port_range_max: The maximum port number in the range that is matched by the security group rule.
                          If the protocol is TCP, UDP, DCCP, SCTP or UDP-Lite this value must be greater than or equal
                          to the port_range_min attribute value. If the protocol is ICMP, this value must be an ICMP
                          code.(Optional)
        * port_range_min: The minimum port number in the range that is matched by the security group rule.
                          If the protocol is TCP, UDP, DCCP, SCTP or UDP-Lite this value must be less than or equal to
                          the port_range_max attribute value. If the protocol is ICMP, this value must be an ICMP type.
                          (Optional)
        * security_group_id: The security group ID to associate with this security group rule.(required)
        * remote_ip_prefix: The remote IP prefix that is matched by this security group rule.(Optional)
        * description: A human-readable description for the resource. Default is an empty string.(Optional)
            eg.
                **{
                    "direction": "ingress",
                    "port_range_min": "80",
                    "ethertype": "IPv4",
                    "port_range_max": "80",
                    "protocol": "tcp",
                    "remote_group_id": "85cc3048-abc3-43cc-89b3-377341426ac5",
                    "security_group_id": "a7734e61-b545-452d-a3cd-0189cbd9747a"
                }
        ---------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            security_group_rule_obj = neutron_client.create_security_group_rule(body={"security_group_rule": kwargs})
        except Exception as e:
            logger.exception("create a specific security group rule[" "] from openstack sdk failed. ")
            message = str(e)
            if str(e).startswith("Security group rule already exists"):
                message = "规则已存在！"
            failed_ip = kwargs["remote_ip_prefix"]
            return {"result": False, "message": message, "failed_ip": failed_ip}
        return {"result": True, "data": security_group_rule_obj}

    def delete_security_group_rule(self, security_group_rule_id):
        """
        Delete a specific rule info from a specific security group.
        :param security_group_rule_id: security group rule id.
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            neutron_client.delete_security_group_rule(security_group_rule_id)
        except Exception as e:
            logger.exception(
                "get a specific security group rule[" + security_group_rule_id + "] from openstack sdk failed. "
            )
            return {"result": False, "message": str(e)}
        return {"result": True}

    def network_list(self, **kwargs):
        """
        Get network list.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * shared: boolean type. Filter the network list result based on if the network is shared across all
        tenants.(Required)
        ---------------
        :rtype: dict
        """
        net_list = []
        share_network = []
        neutron_client = self.nuclient
        try:
            net_list = neutron_client.list_networks(**kwargs)["networks"]
            if kwargs.get("shared", False):
                share_network = neutron_client.list_networks(**{"shared": True})["networks"]
        except Exception as e:
            logger.exception("get network list from openstack sdk failed. " + str(e))

        if self.vpc_dict is None:
            self.vpc_dict = {}
            for cur_net in net_list:
                self.vpc_dict[cur_net.get("id")] = {"id": cur_net.get("id"), "name": cur_net.get("name")}
            for cur_share in share_network:
                self.vpc_dict[cur_share.get("id")] = {"id": cur_share.get("id"), "name": cur_share.get("name")}
        return net_list, share_network

    def list_vpcs(self, ids=None, **kwargs):
        """
        Get network list.
        :param vpc_id: vpc id.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * shared: boolean type. Filter the network list result based on if the network is shared across all
        tenants.(Required)
        ---------------
        :rtype: dict
        """
        if ids:
            return self.get_vpc_detail(ids[0])
        net_list, shared_network = self.network_list(**kwargs)
        net_info_list = []
        net_id = []
        for i in net_list:
            net_info_list.append(self.__network_format(i))
            net_id.append(i["id"])
        if kwargs.get("shared", False):
            for i in shared_network:
                if i["id"] in net_id:
                    continue
                net_info_list.append(self.__network_format(i))
        return {"result": True, "data": net_info_list}

    def create_vpc(self, **kwargs):
        """
        Create a network.
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * name: Human-readable name of the network.(Optional) type: string
        * admin_state_up: The administrative state of the network, which is up (true) or down (false).(Optional)
        type: boolean
        * shared: Indicates whether this resource is shared across all projects. By default,
                    only administrative users can change this value. (Optional) type: boolean
        * availability_zone_hints: The availability zone candidate for the network.(Optional) type: array
        -----------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            network_obj = neutron_client.create_network(body={"network": kwargs})
        except Exception as e:
            logger.exception("create network list from openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        # return {"result": True, "data":network_obj["network"]["id"]}
        network_data = self.__network_format(network_obj["network"])
        return {"result": True, "data": network_data["resource_id"]}
        # return {"result": True, "data": self.__network_format(network_obj["network"])["data"]["id"]}

    def delete_vpc(self, vpc_id):
        """
        Delete a specific network.
        :param vpc_id: network universally unique identifier(uuid).
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            neutron_client.delete_network(vpc_id)
        except Exception as e:
            logger.exception("create network list from openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True}

    def modify_vpc(self, uuid, **kwargs):
        """
        Modify a specific network.
        :param uuid: network universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        -----------------
        * name: Human-readable name of the network.(Optional) type: string
        * admin_state_up: The administrative state of the network, which is up (true) or down (false).(Optional)
        type: boolean
        * shared: Indicates whether this resource is shared across all projects. By default,
                    only administrative users can change this value. (Optional) type: boolean
        -----------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            network_obj = neutron_client.update_network(uuid, body={"network": kwargs})
        except Exception as e:
            logger.exception("modify network list from openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": self.__network_format(network_obj["network"])}

    def __network_format(self, network_obj):
        if network_obj:
            subnet_list = []
            if self.project_dict is None:
                self.project_list()
            if self.subnet_dict is None:
                self.subnet_list()

            for cur_subnet_id in network_obj.get("subnets"):
                subnet_obj = self.subnet_dict.get(cur_subnet_id)
                if subnet_obj:
                    subnet_list.append({"id": subnet_obj["id"], "name": subnet_obj["name"]})
            zone_id = ""
            if len(network_obj.get("availability_zones")) > 0:
                zone_id = (network_obj.get("availability_zones")[0],)
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.VPC.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(network_obj, zone_id=zone_id)
        else:
            return None

    def get_vpc_detail(self, uuid):
        """
        Get a specific network.
        :param uuid: netwrok universally unique identifier(uuid).
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            network_obj = neutron_client.show_network(uuid)
        except Exception as e:
            logger.exception("get a specific network[" + uuid + "] from openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [self.__network_format(network_obj["network"])]}

    def list_eips(self, resource_id="", **kwargs):
        """
        Get a floating ip address from a specific vm.
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            floating_ip_list = neutron_client.list_floatingips()
        except Exception as e:
            logger.exception("get floating ip from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        floating_ip_info_list = []
        for i in floating_ip_list["floatingips"]:
            floating_ip_info_list.append(self.__pulic_ip_format(i))
            if resource_id and resource_id == i["id"]:
                break
        return {"result": True, "data": floating_ip_info_list}

    def __pulic_ip_format(self, ip_obj):
        if ip_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.EIP.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(ip_obj)
        else:
            return None

    def subnet_list(self, **kwargs):
        """
        Get subnet list.
        :param kwargs: accept multiple key value pair arguments.
        ----------------
        none
        ----------------
        :rtype: dict
        """
        subnet_list = []
        neutron_client = self.nuclient
        try:
            subnet_list = neutron_client.list_subnets(**kwargs)["subnets"]
        except Exception as e:
            logger.exception("get subnet list from openstack sdk failed." + str(e))

        if self.subnet_dict is None:
            self.subnet_dict = {}
            for cur_subnet in subnet_list:
                self.subnet_dict[cur_subnet.get("id")] = {"id": cur_subnet.get("id"), "name": cur_subnet.get("name")}
        return subnet_list

    def list_subnets(self, ids=None, **kwargs):
        """
        Get subnet list.
        :param subnet_id: subnet id
        :param kwargs: accept multiple key value pair arguments.
        ----------------
        none
        ----------------
        :rtype: dict
        """
        if ids:
            return self.get_subnet_detail(ids[0])
        subnet_list = self.subnet_list(**kwargs)
        subnet_info_list = []
        for i in subnet_list:
            subnet_info_list.append(self.__subnet_format(i))
        return {"result": True, "data": subnet_info_list}

    def __subnet_format(self, subnet_obj):
        if subnet_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.SUBNET.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(subnet_obj)
        else:
            return None

    def get_subnet_detail(self, uuid, **kwargs):
        """
        Get a specific subnet.
        :param uuid: subnet universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        --------------
        none
        --------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            subnet_obj = neutron_client.show_subnet(uuid, **kwargs)
        except Exception as e:
            logger.exception("get a specific subnet[" + uuid + " from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [self.__subnet_format(subnet_obj["subnet"])]}

    def create_subnet(self, **kwargs):
        """
        Create a subnet from a specific network.
        :param kwargs: accept multiple key value pair arguments.
        -------------------
        * network_id: The ID of the network to which the subnet belongs.(required) type string
        * ip_version: The IP protocol version. Value is 4 or 6.(required) type string
        * cidr: The CIDR of the subnet.(required) type string
        * name: Human-readable name of the resource. Default is an empty string.(optional) type string
        * enable_dhcp: Indicates whether dhcp is enabled or disabled for the subnet. Default is true.(optional)
        type boolean
        * dns_nameservers: List of dns name servers associated with the subnet. Default is an empty list.(optional)
        type array
        * allocation_pools: Allocation pools with start and end IP addresses for this subnet. If allocation_pools are
                not specified, OpenStack Networking automatically allocates pools for covering all IP addresses in the
                CIDR, excluding the address reserved for the subnet gateway by default.(Optional) type array
        * gateway_ip: Gateway IP of this subnet. If the value is null that implies no gateway is associated with the
                subnet. If the gateway_ip is not specified, OpenStack Networking allocates an address from the CIDR
                for the gateway for the subnet by default.(optional) type string
        -------------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            subnet_obj = neutron_client.create_subnet(body={"subnet": kwargs})
        except Exception as e:
            logger.exception("create subnet from a specific network by openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        subnet_data = self.__subnet_format(subnet_obj["subnet"])
        return {"result": True, "data": subnet_data["resource_id"]}

    def delete_subnet(self, subnet_id):
        """
        Delete a specific subnet from a specific network.
        :param subnet_id: subnet universally unique identifier(uuid).
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            neutron_client.delete_subnet(subnet_id)
        except Exception as e:
            logger.exception("delete subnet from a specific network by openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True}

    def modify_subnet(self, uuid, **kwargs):
        """
        Modify a specific subnet from a specific network.
        :param uuid: subnet universally unique identifier(uuid).
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * name: Human-readable name of the resource. Default is an empty string.(optional) type string
        * enable_dhcp: Indicates whether dhcp is enabled or disabled for the subnet. Default is true.(optional)
        type boolean
        * ..........
        * ..........
        ---------------
        :rtype: dict
        """
        neutron_client = self.nuclient
        try:
            subnet_obj = neutron_client.update_subnet(uuid, body={"subnet": kwargs})
        except Exception as e:
            logger.exception("modify subnet from a specific network by openstack sdk failed. ")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": self.__subnet_format(subnet_obj["subnet"])}

    # ------------------***** charge *****-------------------
    def get_virtual_cost(self, **kwargs):
        """
        Get current cost budget.
        :param kwargs: accept multiple key value pair arguments.
        -------------
        * account_name: account name.(required)
        -------------
        :rtype: dict
        """
        region_rs = self.list_regions()
        if region_rs["result"]:
            region_list = region_rs["data"]
        else:
            return {"result": False, "message": "获取region失败！"}
        availability_zone_rs = self.list_zones()
        if availability_zone_rs["result"]:
            availability_zone_list = availability_zone_rs["data"]
        else:
            return {"result": False, "message": "获取可用区失败！"}
        return_data = []
        try:
            for cur_region in region_list:
                nova_client = nvclient.Client(
                    self.nova_version, session=self.sess, region_name=cur_region["resource_id"]
                )
                cinder_client = cdclient.Client(self.cinder_version, session=self.sess, region_name=self.region_name)
                for cur_availability_zone in availability_zone_list:
                    vm_list = nova_client.servers.list(
                        search_opts={"all_tenants": True, "availability_zone": cur_availability_zone["resource_id"]}
                    )
                    if not vm_list:
                        continue
                    computer_price_module = get_compute_price_module(
                        "OpenStack",
                        kwargs["account_name"],
                        cur_region["resource_id"],
                        cur_availability_zone["resource_id"],
                    )[0]
                    for vm in vm_list:
                        price_disk = 0
                        info = vm._info
                        flavor_obj = info["flavor"]
                        if not flavor_obj:
                            continue
                        flavor_info = nova_client.flavors.get(flavor_obj["id"])
                        cpu = flavor_info.vcpus
                        mem = flavor_info.ram / 1024
                        if computer_price_module:
                            if computer_price_module.computerpricemoduledetail_set.filter(cpu=cpu, mem=mem).exists():
                                price_vm_query_set = computer_price_module.computerpricemoduledetail_set.filter(
                                    cpu=cpu, mem=mem
                                )
                                price_vm = price_vm_query_set.first().price_perday
                            else:
                                price_vm = 0
                        else:
                            price_vm = 0
                        volumes_list = getattr(vm, "os-extended-volumes:volumes_attached")
                        for vol in volumes_list:
                            storage_price_module = get_storage_pricemodule(
                                "OpenStack", kwargs["account_name"], cur_region["id"], cur_availability_zone["id"]
                            )[0]
                            if storage_price_module:
                                vol_info = cinder_client.volumes.get(vol["id"])
                                capacity = vol_info.size
                                price_disk += capacity * storage_price_module.price_perday
                            else:
                                price_disk += 0
                        return_data.append(
                            {
                                "resourceId": info["id"],
                                "name": info["name"],
                                "cpu": cpu,
                                "mem": mem,
                                "cost_all": round(float(price_vm), 2) + round(float(price_disk), 2),
                                "cost_vm": round(float(price_vm), 2),
                                "cost_disk": round(float(price_disk), 2),
                                "cost_net": 0.0,
                                "cost_time": datetime.datetime.now().strftime("%Y-%m-%d"),
                                "source_type": CloudResourceType.VM.value,
                            }
                        )
            return {"result": True, "data": return_data}
        except Exception as e:
            logger.exception("get_virtual_cost")
            return {"result": False, "message": str(e)}

    # ------------------***** monitor *****-------------------
    def get_monitor_data(self, **kwargs):
        """
        Get monitor data from a specific vm.
        :rtype: dict
        """
        return {"result": False, "message": "无监控相关数据。"}

    def get_load_monitor_data(self, **kwargs):
        return {"result": False, "message": "无监控相关数据。"}

    # ------------------***** private cloud compute *****-------------------
    def list_hypervisors(self, resource_id="", **kwargs):
        """
        Get hypervisor list.
        :rtype: dict
        :param resource_id：类型：str，资源ID
        """
        if resource_id:
            return self.get_hypervisor_detail(resource_id)
        nova_client = self.novaclient
        try:
            hypervisor_list = nova_client.hypervisors.list()
        except Exception as e:
            logger.exception("get hypervisor list from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        host_list = []
        for cur_hypervisor in hypervisor_list:
            host_list.append(self.__hypervisor_format(cur_hypervisor))
        return {"result": True, "data": host_list}

    def __hypervisor_format(self, hypervisor_obj):
        if hypervisor_obj:
            return get_format_method(
                CloudPlatform.OpenStack,
                CloudResourceType.HYPERVISOR.value,
                project_id=self.project_id,
                region_id=self.region_name,
            )(hypervisor_obj)
        else:
            return None

    def get_hypervisor_detail(self, resource_id):
        """
        Get a specific hypervisor.
        :param kwargs: accept multiple key value pair arguments.
        ---------------
        * uuid: the ID of a hypervisor.(required)
        ---------------
        :rtype: dict
        """
        nova_client = self.novaclient
        try:
            hypervisor_obj = nova_client.hypervisors.get(resource_id)
        except Exception as e:
            logger.exception("get a specific hypervisor[" + resource_id + "] from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [self.__hypervisor_format(hypervisor_obj)]}

    def get_clusters(self):
        """
        Get cluster list.
        :rtype: dict
        """
        return {"result": False, "message": "无相关所有集群资料。"}

    def get_cluster_detail(self):
        """
        Get a specific cluster.
        :rtype: dict
        """
        return {"result": False, "message": "无相关单个集群资料。"}

    # ------------------***** private cloud storage *****-------------------
    # openstack 拿不到存储列表信息，这里就拿存储的可用区
    def get_local_storage(self, **kwargs):
        """
        Get local storage list.
        :rtype: dict
        """
        return self.get_cinder_availability_zones()

    def get_local_storage_detail(self, region=None):
        """
        Get a specific storage.
        :rtype: dict
        """
        return self.get_cinder_availability_zones()

    def get_cinder_availability_zones(self):
        """
        Get cinder availability zone list.
        :rtype: dict
        """
        cinder_client = self.cinderclient
        try:
            cinder_availability_zone_list = cinder_client.availability_zones.list()
        except Exception as e:
            logger.exception("get all volume availabilities from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [{"id": i.zoneName, "name": i.zoneName} for i in cinder_availability_zone_list]}

    def list_disk_types(self):
        """
        Get volume type list.
        :return: dict
        """
        cinder_client = self.cinderclient
        try:
            volume_type_list = cinder_client.volume_types.list()
        except Exception as e:
            logger.exception("get all volume types from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [{"id": i.id, "name": i.name} for i in volume_type_list]}

    def get_network_zones(self):
        """
        Get network zone list.
        :return:
        """
        neutron_client = self.nuclient
        try:
            neutron_zone_list = neutron_client.list_availability_zones()
        except Exception as e:
            logger.exception("get all network zones from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": neutron_zone_list}

    # ******************************** 规格
    def get_disk_spec(self):
        """
        获取OpenStack磁盘类型
        Returns
        -------

        """
        cinder_client = self.cinderclient
        try:
            volume_type_list = cinder_client.volume_types.list()
        except Exception as e:
            logger.exception("get all volume types from openstack sdk failed.")
            return {"result": False, "message": str(e)}
        return {"result": True, "data": [{"value": i.id, "label": i.name} for i in volume_type_list]}
