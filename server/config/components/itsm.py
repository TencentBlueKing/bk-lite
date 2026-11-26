import os

# Flowable REST。凭据只从环境读取，不在代码里写默认口令。
FLOWABLE_URL = os.getenv("FLOWABLE_URL", "http://127.0.0.1:8088")
FLOWABLE_USER = os.getenv("FLOWABLE_USER", "admin")
FLOWABLE_PASSWORD = os.getenv("FLOWABLE_PASSWORD", "")
