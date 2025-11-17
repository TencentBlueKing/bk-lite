# -- coding: utf-8 --
# @File: query_vm.py
# @Time: 2025/11/12 11:27
# @Author: windyzhao
import requests

from apps.cmdb.constants.constants import VICTORIAMETRICS_HOST


"""
VM查询的封装
"""

class Collection:
    def __init__(self):
        self.url = f"{VICTORIAMETRICS_HOST}/prometheus/api/v1/query"

    def query(self, sql, timeout=60):
        """查询数据"""
        resp = requests.post(self.url, data={"query": sql}, timeout=timeout)
        if resp.status_code != 200:
            raise Exception(f"request error！{resp.text}")
        return resp.json()
