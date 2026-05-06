"""Jenkins工具模块

这个模块包含了所有Jenkins相关的工具函数
"""

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.jenkins.build import list_jenkins_jobs, trigger_jenkins_build

CONSTRUCTOR_PARAMS = [
    {
        "name": "jenkins_instances",
        "type": "string",
        "required": False,
        "description": "Jenkins多实例JSON配置",
    },
    {
        "name": "jenkins_default_instance_id",
        "type": "string",
        "required": False,
        "description": "默认Jenkins实例ID",
    },
]

# 导入所有工具函数，保持向后兼容性

__all__ = [
    # Jenkins构建工具
    "list_jenkins_jobs",
    "trigger_jenkins_build",
]
