import json

from django.http import JsonResponse

from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt


def init_user_set(request):
    kwargs = json.loads(request.body)
    client = SystemMgmt()
    res = client.join_default_role(kwargs["user_id"])
    if not res["result"]:
        return JsonResponse(res)
    res = client.create_default_group(kwargs["group_name"], kwargs["user_id"], request.user.group_list[0]["id"])
    if not res["result"]:
        return JsonResponse(res)
    opspilot_client = OpsPilot()
    res = opspilot_client.init_user_set(res["data"]["group_id"], kwargs["group_name"])
    return JsonResponse(res)
