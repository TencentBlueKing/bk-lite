# -- coding: utf-8 --
# @File: nats_test.py
# @Time: 2025/12/16 16:12
# @Author: windyzhao
"""
测试 NATS 通用工具方法
如接口 bklite.node_list
"""
import asyncio
import json

from dotenv import load_dotenv

from core.nats_utils import nats_request


async def run_test():
    subject = "bklite.node_list"
    # 使用正确的 exec_params 格式
    exec_params = {
        "args": [{"page_size": -1}],  # 位置参数列表
        "kwargs": {}  # 关键字参数字典
    }
    payload = json.dumps(exec_params).encode()
    response = await nats_request(subject, payload, timeout=10.0)
    print("NATS Response:", response)


if __name__ == '__main__':
    load_dotenv(".env")
    asyncio.run(run_test())