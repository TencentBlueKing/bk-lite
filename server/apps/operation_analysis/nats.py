# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/9/4 11:36
# @Author: windyzhao
from apps.rpc.base import BaseOperationAnaRpc


class DefaultNastClient(BaseOperationAnaRpc):
    """
    默认的NATS客户端
    """
    DEFAULT_NATS = True

    def __init__(self, func_name, *args, **kwargs):
        super(DefaultNastClient, self).__init__(*args, **kwargs)
        self.func_name = func_name

    def get_customization_nast_data(self, *args, **kwargs):
        """
        调用自定义的NATS函数
        所有自定义的数据接口都走这个方法
        :param args: 函数参数
        :param kwargs: 函数关键字参数
        :return: 函数返回值
        """
        return self.client.run(self.func_name, *args, **kwargs)
