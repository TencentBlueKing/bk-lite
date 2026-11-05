"""兼容旧导入路径。实现放在 rpc，避免作业服务包把模型带进调用方。"""

from apps.rpc.job_opspilot import AUTH_SALT, DEFAULT_AUTH_MAX_AGE_SECONDS, sign_opspilot_job_request, verify_opspilot_job_request  # noqa: F401
