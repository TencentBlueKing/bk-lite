# -*- coding: utf-8 -*-

from common.cmp.cloud_apis.constant import CloudType
from common.cmp.cloud_apis.resource_apis.cw_tce import TCE
from common.cmp.cloud_apis.resource_apis.tcecloud.common import credential
from common.cmp.cloud_apis.resource_apis.tcecloud.common.exception.tce_cloud_sdk_exception import TceCloudSDKException

# 导入可选配置类
from common.cmp.cloud_apis.resource_apis.tcecloud.tsf.v20180326 import models as tsf_models
from common.cmp.cloud_apis.resource_apis.tcecloud.tsf.v20180326 import tsf_client
from core.logger import logger


TSF_COMPONENT = ("TSF",)

TSF_ACTION = (
    "DescribeApplications",
    "DescribeApplicationAttribute",
)

TSF_COMPONENT_TUPLE = [(item, item.lower()) for item in TSF_COMPONENT]
TSF_ACTION_TUPLE = [(item, item) for item in TSF_ACTION]

ComponentCategory = type("TsfComponentEnum", (object,), dict(TSF_COMPONENT_TUPLE))
TSFActionCategory = type("TsfActionEnum", (object,), dict(TSF_ACTION_TUPLE))

resource_mapping = {
    "tsf": (ComponentCategory.TSF, TSFActionCategory.DescribeApplications, "ApplicationSet"),
}

client_mapping = {
    "tsf": (tsf_client.TsfClient, tsf_models),
}


class CwTSF:
    def __init__(self, secret_id, secret_key, region_id, host="", **kwargs):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region_id = region_id
        self.domain = host
        self.tsf_ins = None
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.cred = credential.Credential(self.secret_id, self.secret_key)

    def __getattr__(self, method_name):
        if not self.tsf_ins:
            self.tsf_ins = TSF(
                cred=self.cred,
                method_name=method_name,
                region_id=self.region_id,
                domain=self.domain,
                secret_id=self.secret_id,
                secret_key=self.secret_key,
            )
            return self.tsf_ins
        else:
            self.tsf_ins.method_name = method_name
            return self.tsf_ins


class TSF(TCE):
    def __init__(self, cred, method_name, region_id, domain, secret_id=None, secret_key=None, version="api3"):
        super().__init__(cred, method_name, region_id, domain, secret_id=None, secret_key=None, version="api3")
        self.cred = cred
        self.method_name = method_name
        self.region_id = region_id
        self.domain = domain
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.cloud_type = CloudType.TSF.value

        # cache object
        self.region_cache = None
        self.zone_cache = None

    # *************************** tool *****************************

    def handle_call_request(self, component_name, client_method_name, params, request_method_name=None):
        if component_name != "tsf":
            return super().handle_call_request(component_name, client_method_name, params, request_method_name)
        client_profile = self._get_client_profile(component_name, self.version, self.domain)
        client_ins = tsf_client.TsfClient(self.cred, self.region_id, client_profile)
        request_method_name = request_method_name or "%sRequest" % client_method_name
        request_ins = getattr(tsf_models, request_method_name)()
        for key, value in params.items():
            setattr(request_ins, key, value)
        response_obj = getattr(client_ins, client_method_name)(request_ins)
        return response_obj

    # *************************** application *****************************

    def get_application_attr(self, instance_id):
        try:
            resp = self.handle_call_request(
                self.cloud_type.lower(), TSFActionCategory.DescribeApplicationAttribute, {"ApplicationId": instance_id}
            )
        except TceCloudSDKException as e:
            logger.exception("get flavor families failed: %s" % e)
            return {"result": False, "message": e.message}
        return resp

    def list_applications(self):
        try:
            resp = self.handle_call_request(self.cloud_type.lower(), TSFActionCategory.DescribeApplications, {})
        except TceCloudSDKException as e:
            logger.exception("get flavor families failed: %s" % e)
            return {"result": False, "message": e.message}
        appdata = []
        for app in resp.Result.Content:
            app_attr = self.get_application_attr(app.ApplicationId)
            app.GroupCount = app_attr.Result.GroupCount
            app.InstanceCount = app_attr.Result.InstanceCount
            app.RunInstanceCount = app_attr.Result.RunInstanceCount
            appdata.append(app)
        data = self.format_resource("application", resp.Result.Content, region_id=self.region_id)
        return {"result": True, "data": data}
