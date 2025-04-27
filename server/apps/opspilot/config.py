import os

# REMOTE_SERVICE
METIS_SERVER_URL = os.getenv("METIS_SERVER_URL", "http://rag-server-api/")
# BOT 环境变量
KUBE_NAMESPACE = os.getenv("KUBE_NAMESPACE", "lite")
MUNCHKIN_BASE_URL = os.getenv("MUNCHKIN_BASE_URL", "http://munchkin")

CONVERSATION_MQ_HOST = os.getenv("CONVERSATION_MQ_HOST", "rabbitmq.ops-pilot")
CONVERSATION_MQ_PORT = int(os.getenv("CONVERSATION_MQ_PORT", 5672))
CONVERSATION_MQ_USER = os.getenv("CONVERSATION_MQ_USER", "admin")
CONVERSATION_MQ_PASSWORD = os.getenv("CONVERSATION_MQ_PASSWORD", "password")

# MINIO 配置
MINIO_PRIVATE_BUCKETS = ["munchkin-private"]
MINIO_PUBLIC_BUCKETS = ["munchkin-public"]
KUBE_CONFIG_FILE = os.getenv("KUBE_CONFIG_FILE", "")
