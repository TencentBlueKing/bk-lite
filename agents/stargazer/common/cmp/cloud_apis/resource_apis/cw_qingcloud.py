import ssl

import qingcloud.iaas

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.cloud_constant import CloudPlatform
from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from common.cmp.cloud_apis.resource_apis.utils import fail, success
from core.logger import logger

VM_ACTION = (
    "describe_instances",  # 获取服务器信息
    "run_instances",  # 创建服务器
)
VOLUME_ACTION = ("describe_volumes",)  # 获取硬盘列表
VPC_ACTION = ("describe_routers",)

SUBNET_ACTION = ("describe_vxnets",)

SECURITY_GROUP_ACTION = ("describe_security_groups",)

SECURITY_GROUP_RULE_ACTION = ("describe_security_group_rules",)
LOAD_BALANCER_ACTION = (
    "describe_loadbalancers",
    "describe_loadbalancer_listeners",
)

LOAD_BALANCER_LISTENER_ACTION = ("describe_loadbalancer_listeners",)
REDIS_ACTION = ("describe_clusters",)
VM_ACTION_TUPLE = [(item, item) for item in VM_ACTION]
VOLUME_ACTION_TUPLE = [(item, item) for item in VOLUME_ACTION]
VPC_ACTION_TUPLE = [(item, item) for item in VPC_ACTION]
SUBNET_ACTION_TUPLE = [(item, item) for item in SUBNET_ACTION]
SECURITY_GROUP_TUPLE = [(item, item) for item in SECURITY_GROUP_ACTION]
SECURITY_GROUP_RULE_TUPLE = [(item, item) for item in SECURITY_GROUP_RULE_ACTION]
LOADBALANCER_TUPLE = [(item, item) for item in LOAD_BALANCER_ACTION]
REDIS_TUPLE = [(item, item) for item in REDIS_ACTION]

VMActionCategory = type("vmActionEnum", (object,), dict(VM_ACTION_TUPLE))
VOLUMEActionCategory = type("volumeActionEnum", (object,), dict(VOLUME_ACTION_TUPLE))
VPCActionCategory = type("vpcActionEnum", (object,), dict(VPC_ACTION_TUPLE))
SUBNETActionCategory = type("subnetActionEnum", (object,), dict(SUBNET_ACTION_TUPLE))
SECURITY_GROUPActionCategory = type("security_groupActionEnum", (object,), dict(SECURITY_GROUP_TUPLE))
SECURITY_GROUP_RULEActionCategory = type("security_group_ruleActionEnum", (object,), dict(SECURITY_GROUP_RULE_TUPLE))
LOADBALANCERActionCategory = type("loadbalancer_listenerActionEnum", (object,), dict(LOADBALANCER_TUPLE))
REDISActionCategory = type("redisActionEnum", (object,), dict(REDIS_TUPLE))


class CwQingCloud(object):
    def __init__(self, accesss_key_id, secret_access_key, region="", host="", **kwargs):
        self.accesss_key_id = accesss_key_id
        self.secret_access_key = secret_access_key
        self.host = host
        self.region = region
        self.version = kwargs.get("version", "")
        self.zone = kwargs.get("zone", "pek3")
        self.image_id = kwargs.get("image_id", "")
        ssl._create_default_https_context = ssl._create_unverified_context
        self.conn = qingcloud.iaas.connect_to_zone(
            self.zone, self.accesss_key_id, self.secret_access_key  # 资源所在的节点ID，可在控制台切换节点的地方查看，如 'pek3', 'ap2a', 'gd2' 等
        )
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getattr__(self, item):
        return QingCloud(
            name=item,
            version=self.version,
            zone=self.zone,
            host=self.host,
            conn=self.conn,
        )


class QingCloud(PrivateCloudManage):
    def __init__(self, name, host, zone, version, conn):
        """
        初始化方法
        """
        self.conn = conn
        self.name = name
        self.host = host
        self.version = version
        self.zone = zone
        self.cloud_type = CloudType.QINGCLOUD.value

    def __call__(self, *args, **kwargs):
        return getattr(self, self.name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def get_connection_result(self):
        """
        检查连接是否成功
        """
        if self.conn:
            return success("连接成功")
        else:
            return fail("连接失败")

    def handle_list(self, conn, method_name, params):
        data = getattr(conn, method_name)(params)
        return data

    def list_vms(self, ids=None, **kwargs):
        """
        获取虚拟机列表
        """
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, VMActionCategory.describe_instances, params)["instance_set"]
        res = []
        for i in data:
            # 青云已中止的数据也会返回，需要进行过滤
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "vm",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def create_vm(self, **kwargs):
        """
        新建虚拟机
        """
        try:
            resp = getattr(self.conn, VMActionCategory.run_instances)(
                instance_type="s1.small.r1", login_mode="passwd", **kwargs
            )
        except Exception as e:
            logger.exception(u"创建失败，参数：{}，错误信息：{}".format(kwargs, str(e)))
            return {"result": False, "message": e}
        return {"result": True, "data": resp}

    def list_disks(self, ids=None, **kwargs):
        """获取硬盘列表"""
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, VOLUMEActionCategory.describe_volumes, params)["volume_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "disk",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_vpcs(self, ids=None, **kwargs):
        """获取VPC"""
        params = []
        data = self.handle_list(self.conn, VPCActionCategory.describe_routers, params)["router_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "vpc",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_subnets(self, ids=None, **kwargs):
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, SUBNETActionCategory.describe_vxnets, params)["vxnet_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "subnet",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_security_groups(self, ids=None, **kwargs):
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, SECURITY_GROUPActionCategory.describe_security_groups, params)[
            "security_group_set"
        ]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "security_group",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_security_group_rules(self, ids=None, **kwargs):
        data = self.handle_list(self.conn, SECURITY_GROUP_RULEActionCategory.describe_security_group_rules, None)[
            "security_group_rule_set"
        ]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "security_group_rule",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_load_balancers(self, ids=None, **kwargs):
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, LOADBALANCERActionCategory.describe_loadbalancers, params)[
            "loadbalancer_set"
        ]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "loadbalancer",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_listeners(self, ids=None, **kwargs):
        params = [{"zone": self.zone}, kwargs]
        data = self.handle_list(self.conn, LOADBALANCERActionCategory.describe_loadbalancer_listeners, params)[
            "loadbalancer_listener_set"
        ]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "listener",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_rediss(self, ids=None, **kwargs):
        params = [kwargs]
        data = self.handle_list(self.conn, REDISActionCategory.describe_clusters, params)["cluster_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            if i["app_info"]["app_name"] == "Redis Cluster":
                res.append(
                    get_format_method(
                        CloudPlatform.QingCloud,
                        "redis",
                        project_id=kwargs.get("project_id", ""),
                        region_id=kwargs.get("region_id", ""),
                    )(i)
                )
        return success(res)

    def list_mariadbs(self, ids=None, **kwargs):
        params = [kwargs]
        data = self.handle_list(self.conn, REDISActionCategory.describe_clusters, params)["cluster_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            if i["app_info"]["app_name"] == "QingCloud MySQL Plus":
                res.append(
                    get_format_method(
                        CloudPlatform.QingCloud,
                        "mysql",
                        project_id=kwargs.get("project_id", ""),
                        region_id=kwargs.get("region_id", ""),
                    )(i)
                )
        return success(res)

    def list_images(self, id=None, **kwargs):
        """ "查询镜像
        必传字段provider值为system或self表示镜像提供者
        """
        data = self.conn.describe_images(provider="system", **kwargs)["image_set"]
        res = []
        for i in data:
            if i.get("status") == "ceased":
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "image",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_regions(self, ids=None, **kwargs):
        data = self.conn.describe_zones()["zone_set"]
        res = []
        for i in data:
            if not i.get("region_id"):
                continue
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "region",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)

    def list_zones(self, ids=None, **kwargs):
        data = self.conn.describe_zones(**kwargs)["zone_set"]
        res = []
        for i in data:
            res.append(
                get_format_method(
                    CloudPlatform.QingCloud,
                    "zone",
                    project_id=kwargs.get("project_id", ""),
                    region_id=kwargs.get("region_id", ""),
                )(i)
            )
        return success(res)
