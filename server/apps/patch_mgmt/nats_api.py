"""补丁管理 NATS API

注册数据权限模块列表（get_patch_mgmt_module_list）。
"""

import nats_client


@nats_client.register
def get_patch_mgmt_module_list():
    return [
        {"name": "patch", "display_name": "补丁库"},
        {"name": "patch_target", "display_name": "目标管理"},
        {"name": "patch_source", "display_name": "补丁源"},
        {"name": "patch_baseline", "display_name": "基线管理"},
        {"name": "patch_governance", "display_name": "治理任务"},
        {"name": "patch_risk", "display_name": "风险治理"},
        {"name": "patch_dashboard", "display_name": "补丁看板"},
    ]
