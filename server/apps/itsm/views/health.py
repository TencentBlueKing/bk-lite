from apps.core.utils.open_base import login_exempt
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.health import probe_flowable


@login_exempt
def health(_request):
    """返回 Flowable 连通状态。免登录，供部署后探测。"""
    return WebUtils.response_success(probe_flowable())
