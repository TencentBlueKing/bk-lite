# -- coding: utf-8 --
# @File: operation_analysis.py
# @Time: 2025/11/5 15:30
# @Author: windyzhao
from apps.rpc.base import RpcClient


class OperationAnalysisRPC:
    """
    RPC related operations for Operation Analysis app.
    """

    def __init__(self):
        self.client = RpcClient()

    def get_module_data(self, **kwargs):
        return_data = self.client.run("get_operation_analysis_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        return_data = self.client.run("get_operation_analysis_module_list", **kwargs)
        return return_data
