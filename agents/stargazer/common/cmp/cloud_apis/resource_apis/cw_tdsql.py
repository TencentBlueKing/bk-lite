# -*- coding: utf-8 -*-
import time

import requests

from common.cmp.cloud_apis.base import PrivateCloudManage
from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.resource_format.common.base_format import get_format_method
from core.logger import logger



class CwTDSQL:
    """
    TDSQL组件类,通过该类创建TDSQL的Client实例，调用TDSQL的api接口
    """

    def __init__(self, account, password, region, host="", **kwargs):
        """
        初始化方法
        """
        self.account = account
        self.oss_url = host
        self.password = password
        self.host = host
        self.region = region
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getattr__(self, item):
        return TDSQL(
            account=self.account,
            oss_url=self.host,
            method_name=item,
            password=self.password,
            host=self.host,
            region=self.region,
        )


class TDSQL(PrivateCloudManage):
    """
    TDSQL接口类
    """

    def __init__(self, account, oss_url, method_name, password, host, region):
        """ """
        self.account = account
        self.oss_url = oss_url
        self.password = password
        self.host = host
        self.region = region
        self.method_name = method_name
        self.cloud_type = CloudType.TDSQL.value

    def __call__(self, *args, **kwargs):
        return getattr(self, self.method_name, self._non_function)(*args, **kwargs)

    @classmethod
    def _non_function(cls, *args, **kwargs):
        return {"result": True, "data": []}

    def __handle_requests(self, interfacename, interface_dict: dict):
        """
        统一发送TDSQL接口请求，获取接口数据
        """
        url = "http://{}".format(self.oss_url)
        # url = "http://192.168.165.177:8080/tdsql"
        post_data = {
            "version": "1.0",
            "caller": "DES",
            "password": "DES",
            "callee": "TDSQL",
            "eventId": 101,
            "timestamp": int(time.time()),
            "interface": {"interfaceName": interfacename, "para": interface_dict},
        }
        try:
            res = requests.post(url=url, json=post_data, verify=False).json()
            if res["returnMsg"] == "ok":
                return {"result": True, "data": res}
            else:
                return {"result": False, "message": res["returnMsg"]}
        except Exception as e:
            return {"result": False, "message": str(e)}

    #   ************************公共方法*************************
    def get_connection_result(self):
        """
        测试是否连接成功
        """
        rs = self.list_noshard()
        if rs["result"]:
            return {"result": True}
        else:
            return {"result": False}

    def _format_resource_result(self, resource_type, obj):
        """
        格式化获取到的资源结果
        Args:
            resource_type (str): 资源类型名 如 region
            data (list or object): 待格式化的数据，

        Returns:

        """
        try:
            format_method = get_format_method(self.cloud_type, resource_type, region_id=self.region)

            return format_method(obj)
        except Exception as e:
            logger.exception("get_tdsql_info:" + str(e))
            return None

    #   ************************非分布式*************************
    def list_spec(self):
        """
        获取机器规格信息
        """
        return self.__handle_requests("TDSQL.QuerySpec", {})

    def list_proxygroups(self, proxys_array, proxy=""):
        """
        获得所有的网关组信息
        """
        proxys_array = proxys_array or []
        return self.__handle_requests("TDSQL.GetProxyGroups", {"proxys": proxys_array, "proxy": proxy})

    def list_noshard(self, instance_array=None, instance_id=""):
        """
        查询noshard实例信息
        """
        instance_array = instance_array or []
        try:
            res = self.__handle_requests("TDSQL.QueryGWInstance", {"instance": instance_array, "id": instance_id})
            if not res["result"]:
                return {"result": False, "message": res["message"]}
            result_data = []
            for cur_data in res["data"]["returnData"]["instance"]:
                data = self._format_resource_result("noshard_instance", cur_data)
                if data:
                    result_data.append(data)
            return {"result": True, "data": result_data}
        except Exception as e:
            logger.exception("get noshard instance failed!")
            return {"result": False, "message": str(e)}

    def get_switch_status(self, group_id="", set_id=""):
        """
        查询当前免切信息
        """
        return self.__handle_requests("TDSQL.GetInstanceSwitchStatus", {"groupid": group_id, "id": set_id})

    def set_stop_switch(self, action_type, times=0, group_id="", set_id=""):
        """
        手动设置免切
        """
        return self.__handle_requests(
            "TDSQL.StopInstanceSwitch", {"groupid": group_id, "id": set_id, "type": action_type, "times": times}
        )

    def delete_stop_switch(self, group_id="", set_id=""):
        """
        删除免切的参数设置
        """
        return self.__handle_requests("TDSQL.DeleteStopInstanceSwitch", {"id": set_id, "groupid": group_id})

    def create_noshard_instance(self, **kwargs):
        """
        新增非分布式实例,返回任务ID
        """
        res = self.__handle_requests("TDSQL.AddGWInstance", kwargs)

        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("创建非分布式实例任务：{}".format(task_id))
        # task_id = 46
        process = 0
        current_times = 1
        max_times = 30
        # 设置约半小时的超时时间
        while process != 100 and current_times < max_times:
            time.sleep(60)
            task_rs = self.get_create_noshard_process(task_id)
            if not task_rs["result"]:
                return {"result": False, "message": task_rs["message"]}

            if task_rs["data"]["set"]:
                return {"result": True, "data": task_rs["data"]["set"]}

            process = task_rs["data"]["process"]

            if task_rs["data"]["status"] == 1:
                return {"result": False, "message": task_rs["data"]["description"]}

            if task_rs["data"]["status"] == 0:
                return {"result": True, "data": task_rs["data"]["set"]}

            current_times += 1
        return {"result": False, "message": "创建超时"}

        # return {"result": True, "data": res["data"]["returnData"]["taskid"]}

    def init_noshard(self, set_id, **kwargs):
        """
        初始化实例配置任务,只支持noshard
        """
        config = [
            {"param": "character_set_server", "value": kwargs.get("character_set_server", "utf8")},
            {"param": "lower_case_table_names", "value": kwargs.get("lower_case_table_names", "1")},
            {"param": "innodb_page_size", "value": kwargs.get("innodb_page_size", "")},
            # {"param": "other_para", "value": kwargs.get('other_para', '')},
        ]
        res = self.__handle_requests("TDSQL.InitInstance", {"id": set_id, "config": config})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("初始化非分布式实例任务：{}".format(task_id))
        process = 0
        while process != 100:
            time.sleep(30)
            task_rs = self.get_init_noshard_process(task_id)
            if not task_rs["result"]:
                return {"result": False, "message": task_rs["message"]}

            process = task_rs["data"]["process"]

            if task_rs["data"]["status"] == 0 and task_rs["data"]["process"] == 100:
                return {"result": True, "data": task_rs["data"]["set"]}

    def get_init_noshard_process(self, task_id):
        """
        查询初始化实例任务的进度
        """
        res = self.__handle_requests("TDSQL.QueryInitInstance", {"taskid": task_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result = res["data"]["returnData"]
        return {"result": True, "data": {"status": result["status"], "process": result["process"], "set": result["id"]}}

    def get_create_noshard_process(self, task_id):
        """
        查询新增实例任务的进度
        """
        res = self.__handle_requests("TDSQL.QueryAddGWInsance", {"taskid": task_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result = res["data"]["returnData"]
        return {
            "result": True,
            "data": {
                "status": result["status"],
                "process": result["process"],
                "set": result["set"],
                "description": result.get("description"),
            },
        }

    def delete_noshard(self, instance_id, coldbackup=True, gateway=True):
        """
        删除noshard实例
        """
        res = self.__handle_requests(
            "TDSQL.DeleteGWInstance", {"id": instance_id, "check_coldbackup": coldbackup, "check_gateway": gateway}
        )
        if not res["result"]:
            return {"result": False, "message": res["message"]}

        task_id = res["data"]["returnData"]["taskid"]
        logger.info("删除非分布式实例任务：{}".format(task_id))

        return {"result": True}

    def get_del_noshard_process(self, task_id):
        """
        查询删除实例任务的进度
        """
        return self.__handle_requests("TDSQL.QueryGWDelInstance", {"taskid": task_id})

    def expand_noshard(self, **kwargs):
        """
        对网关分离的版本的set进行扩容
        """
        return self.__handle_requests(**kwargs)

    def get_expand_process(self, set_id):
        """
        查询扩容任务的状态
        """
        return self.__handle_requests("TDSQL.QueryExpandGWInstance", {"id": set_id})

    #   ************************分布式*************************
    def list_groupshard(self, groups_array=None, group_id=""):
        """
        查询分布式实例信息
        """
        groups_array = groups_array or []
        res = self.__handle_requests("TDSQL.GetGWGroup", {"groups": groups_array, "id": group_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result_data = []
        for cur_data in res["data"]["returnData"]["groups"]:
            data = self._format_resource_result("group_instance", cur_data)
            if data:
                result_data.append(data)
        return {"result": True, "data": result_data}

    def create_groupshard_instance(self, **kwargs):
        """
        新增分布式实例
        """
        res = self.__handle_requests("TDSQL.AddGWGroup", kwargs)
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("创建分布式实例任务：{}".format(task_id))
        process = 0
        current_times = 1
        max_times = 30
        while process != 100 and current_times < max_times:
            time.sleep(60)
            task_res = self.get_create_group_process(task_id)
            if not task_res["result"]:
                return {"result": False, "message": task_res["message"]}
            if task_res["data"]["groupid"]:
                return {"result": True, "data": task_res["data"]["groupid"]}
            process = task_res["data"]["process"]
            if task_res["data"]["status"] == 1:
                return {"result": False, "message": task_res["data"]["description"]}
            if task_res["data"]["status"] == 0:
                return {"result": True, "data": task_res["data"]["groupid"]}
            current_times += 1
        return {"result": False, "message": "创建超时"}

    def add_into_group(self, **kwargs):
        """
        添加set实例到group
        """
        res = self.__handle_requests("TDSQL.AddInsToGroup", kwargs)
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("添加set到groupshard任务：{}".format(task_id))
        process = 0
        current_times = 1
        max_times = 30
        while process != 100 and current_times < max_times:
            time.sleep(60)
            task_res = self.get_add_into_group_process(kwargs.get("groupid"), task_id)
            if not task_res["result"]:
                return {"result": False, "message": task_res["message"]}
            if task_res["data"]["group_id"] and task_res["data"]["set_id"]:
                return {
                    "result": True,
                    "data": {"group_id": task_res["data"]["group_id"], "set_id": task_res["data"]["set_id"]},
                }
            process = task_res["data"]["process"]
            if task_res["data"]["status"] == 1:
                return {"result": False, "message": task_res["data"]["msg"]}
            if task_res["data"]["status"] == 0:
                return {
                    "result": True,
                    "data": {"group_id": task_res["data"]["group_id"], "set_id": task_res["data"]["set_id"]},
                }
            current_times += 1
        return {"result": False, "message": "添加set超时"}

    def get_add_into_group_process(self, group_id, task_id):
        """
        查询添加set到group任务的进度
        """
        res = self.__handle_requests("TDSQL.QueryAddInsToGroup", {"taskid": task_id, "groupid": group_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result = res["data"]["returnData"]
        return {
            "result": True,
            "data": {
                "status": result["status"],
                "process": result["process"],
                "group_id": result["groupid"],
                "set_id": result["id"],
                "msg": result["msg"],
            },
        }

    def init_groupshard(self, group_id, set_id, **kwargs):
        """
        初始化group中的实例
        """
        config = [
            {"param": "character_set_server", "value": kwargs.get("character_set_server", "utf8")},
            {"param": "collation_server", "value": kwargs.get("collation_server", "utf8_general_ci")},
            {"param": "lower_case_table_names", "value": kwargs.get("lower_case_table_names", "1")},
            {"param": "innodb_page_size", "value": kwargs.get("innodb_page_size", "")},
        ]
        res = self.__handle_requests("TDSQL.InitGroupIns", {"groupid": group_id, "id": set_id, "config": config})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("初始化groupshard中实例任务：{}".format(task_id))
        process = 0
        while process != 100:
            time.sleep(30)
            task_res = self.get_init_group_process(group_id, task_id)
            if not task_res["result"]:
                return {"result": False, "message": task_res["message"]}
            process = task_res["data"]["process"]
            if task_res["data"]["status"] == 1:
                return {"result": False, "message": task_res["data"]["msg"]}
            if task_res["data"]["status"] == 0:
                return {"result": True, "data": task_res["data"]["msg"]}

    def get_init_group_process(self, group_id, task_id):
        """
        查询group初始化任务的进度
        """
        res = self.__handle_requests("TDSQL.QueryInitGroupIns", {"groupid": group_id, "taskid": task_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result = res["data"]["returnData"]
        return {
            "result": True,
            "data": {"status": result["status"], "process": result["process"], "msg": result["msg"]},
        }

    def deactive_group(self, group_id):
        """
        隔离
        """
        return self.__handle_requests("TDSQL.DeactiveGroup", {"groupid": group_id})

    def active_group(self, group_id):
        """
        解除隔离
        """
        return self.__handle_requests("TDSQL.ActiveGroup", {"groupid": group_id})

    def delete_groupshard(self, group_id, check_coldbackup=True, check_gateway=True):
        """
        删除分布式实例（分布式删除前需要先隔离）
        """
        res = self.__handle_requests(
            "TDSQL.DeleteGWGroup",
            {"groupid": group_id, "check_coldbackup": check_coldbackup, "check_gateway": check_gateway},
        )
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        task_id = res["data"]["returnData"]["taskid"]
        logger.info("删除分布式实例任务：{}".format(task_id))
        return {"result": True}

    def get_del_group_process(self, task_id):
        """
        查询删除分布式实例任务的进度
        """
        return self.__handle_requests("TDSQL.QueryDelGWGroup", {"taskid": task_id})

    def get_create_group_process(self, task_id):
        """
        查询新增分布式实例进度
        """
        res = self.__handle_requests("TDSQL.QueryAddGWGroup", {"taskid": task_id})
        if not res["result"]:
            return {"result": False, "message": res["message"]}
        result = res["data"]["returnData"]
        return {
            "result": True,
            "data": {
                "status": result["status"],
                "process": result["process"],
                "groupid": result["groupid"],
                "description": result.get("description"),
            },
        }

    #   ************************数据库*************************
    def list_user(self, group_id, set_id):
        """
        查询用户列表
        """
        return self.__handle_requests("TDSQL.ListUser", {"groupid": group_id, "id": set_id})

    def create_user(self, **kwargs):
        """
        新增用户
        """
        return self.__handle_requests("TDSQL.AddUser", kwargs)

    def list_database(self, group_id="", set_id=""):
        """
        获取数据库列表
        """
        return self.__handle_requests("TDSQL.ListDatabase", {"groupid": group_id, "id": set_id})

    def list_object(self, db, group_id="", set_id=""):
        """
        获取指定数据库的对象列表
        """
        return self.__handle_requests("TDSQL.ListObject", {"groupid": group_id, "id": set_id, "db": db})

    def list_column(self, db, table, group_id="", set_id=""):
        """
        获取表字段列表
        """
        return self.__handle_requests("TDSQL.ListColumn", {"groupid": group_id, "id": set_id, "db": db, "table": table})

    def get_right(self, **kwargs):
        """
        获取权限列表
        """
        return self.__handle_requests("TDSQL.GetRight", kwargs)

    def change_right(self, **kwargs):
        """
        更新权限
        """
        return self.__handle_requests("TDSQL.ChangeRight", kwargs)

    def delete_user(self, user, host, group_id="", set_id=""):
        """
        删除用户
        """
        return self.__handle_requests("TDSQL.DelUser", {"groupid": group_id, "id": set_id, "user": user, "host": host})

    def reset_password(self, user, host, pwd, group_id="", set_id=""):
        """
        修改密码
        """
        return self.__handle_requests(
            "TDSQL.ResetPwd", {"groupid": group_id, "id": set_id, "user": user, "host": host, "pwd": pwd}
        )

    def list_config(self, group_id="", set_id=""):
        """
        获取数据库配置参数
        """
        return self.__handle_requests("TDSQL.ListConfig", {"groupid": group_id, "id": set_id})

    def modify_config(self, config: list, group_id="", set_id=""):
        """
        修改数据库配置参数
        """
        return self.__handle_requests("TDSQL.ModifyConfig", {"groupid": group_id, "id": set_id, "config": config})
