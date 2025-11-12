# MINIO 配置
# MINIO_EXTERNAL_ENDPOINT = os.getenv("MINIO_EXTERNAL_ENDPOINT")
# MINIO_EXTERNAL_ENDPOINT_USE_HTTPS = os.getenv("MINIO_EXTERNAL_ENDPOINT_USE_HTTPS", "0") == "1"
import os
from datetime import timedelta
from typing import List, Tuple

MINIO_BUCKET_CHECK_ON_SAVE = True
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_USE_HTTPS = os.getenv("MINIO_USE_HTTPS", "0") == "1"
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_URL_EXPIRY_HOURS = timedelta(days=7)
MINIO_CONSISTENCY_CHECK_ON_START = False

MINIO_PRIVATE_BUCKETS = [
    "rewind-private",
    "munchkin-private",
    "log-alert-raw-data",  # 日志告警原始数据存储
    "monitor-alert-raw-data",  # 监控告警原始数据存储
]
MINIO_PUBLIC_BUCKETS = ["rewind-public", "munchkin-public"]
MINIO_POLICY_HOOKS: List[Tuple[str, dict]] = []
