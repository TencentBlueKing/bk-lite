"""Jenkins工具模块

这个模块包含了所有Jenkins相关的工具函数
"""

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.jenkins.build import list_jenkins_jobs, trigger_jenkins_build
CONSTRUCTOR_PARAMS = [
    {
        "name": "jenkins_url",
        "type": "string",
        "required": True,
        "description": "Jenkins服务器URL地址"
    },
    {
        "name": "jenkins_username",
        "type": "string",
        "required": True,
        "description": "Jenkins用户名"
    },
    {
        "name": "jenkins_password",
        "type": "string",
        "required": True,
        "description": "Jenkins用户密码或API Token"
    }
]

# 导入所有工具函数，保持向后兼容性

__all__ = [
    # Jenkins构建工具
    "list_jenkins_jobs",
    "trigger_jenkins_build",
]
