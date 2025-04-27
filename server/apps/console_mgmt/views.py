import json

from django.http import JsonResponse

from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt


def init_user_set(request):
    kwargs = json.loads(request.body)
    client = SystemMgmt()
    res = client.init_user_default_attributes(kwargs["user_id"], kwargs["group_name"], request.user.group_list[0]["id"])
    if not res["result"]:
        return JsonResponse(res)
    opspilot_client = OpsPilot()
    res = opspilot_client.init_user_set(res["data"]["group_id"], kwargs["group_name"])
    return JsonResponse(res)
