# -- coding: utf-8 --
# @File: stargazer.py
# @Time: 2025/4/27 10:30
# @Author: windyzhao
from apps.rpc.base import RpcClient


class Stargazer(object):
    def __init__(self):
        self.client = RpcClient(namespace='stargazer')

    def list_regions(self, params):
        return_data = self.client.run("list_regions", **params)
        return return_data
