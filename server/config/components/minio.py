# MINIO 配置
# MINIO_EXTERNAL_ENDPOINT = os.getenv("MINIO_EXTERNAL_ENDPOINT")
# MINIO_EXTERNAL_ENDPOINT_USE_HTTPS = os.getenv("MINIO_EXTERNAL_ENDPOINT_USE_HTTPS", "0") == "1"
import os
from datetime import timedelta
from typing import List, Tuple

MINIO_BUCKET_CHECK_ON_SAVE = True
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_USE_HTTPS = os.getenv("MINIO_USE_HTTPS", "0") == "1"
# BL-NEW-006：移除内置的默认对象存储凭据（默认凭据可导致对象存储未授权访问）。
# 仅从环境变量读取，未配置时为空，连接将因凭据无效而失败，而非以众所周知的
# 默认账户访问对象存储。
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_URL_EXPIRY_HOURS = timedelta(days=7)
MINIO_CONSISTENCY_CHECK_ON_START = False

MINIO_PRIVATE_BUCKETS = [
    "rewind-private",
    "munchkin-private",
    "log-alert-raw-data",  # 日志告警原始数据存储
    "monitor-alert-raw-data",  # 监控指标原始数据存储
    "job-mgmt-private",  # 监控指标原始数据存储
    "cmdb-config-file",
    "patch-mgmt-private",  # 补丁管理 SSH 私钥
    "patch-mgmt-packages",  # 补丁管理手工 Windows 补丁包
]
MINIO_PUBLIC_BUCKETS = ["rewind-public", "munchkin-public"]
MINIO_POLICY_HOOKS: List[Tuple[str, dict]] = []
