from collections import OrderedDict

from core.logger import logger

try:
    from common.cmp.cloud_apis.resource_client import ResourceClient
except Exception:
    logger.exception("cmp error")
    raise ModuleNotFoundError("must build cmp directory or pip install -r cmp/requirements.txt")


register_driver = OrderedDict()


class MetaDriver(type):
    def __new__(cls, name, bases, attrs):
        new_class = super(MetaDriver, cls).__new__(cls, name, bases, attrs)
        _tag = attrs.get("__tag__")
        assert _tag is not None, f"register driver:{name} must set class property `__tag__`  "
        register_driver.update({_tag: new_class})
        return new_class


class Driver(metaclass=MetaDriver):
    __tag__ = "base"

    def run(self, *args, **kwargs):
        pass


class CMPDriver(Driver):
    """cloud manager platform"""

    __tag__ = "cmp"

    def __init__(self, account, password, cloud_type, region=None, host="", **kwargs):
        self.account = account
        self.password = password
        self.region = region
        self.cloud_type = cloud_type
        self.host = host
        self.kwargs = kwargs

    def __getattr__(self, item):
        """云资源操作方法:如list_vm,list_dist"""
        if item in ["shape", "__len__"]:
            return
        client = ResourceClient(
            self.account, self.password, self.region, self.cloud_type, host=self.host, **self.kwargs
        ).cw
        method = getattr(client, item)
        if not method:
            raise AttributeError(f"Cloud:{self.cloud_type} not define method `{item}`")
        return method

    def run(self, mname, **kwargs):
        try:
            _method = getattr(self, mname)
        except Exception as e:
            logger.error(f"CMP Driver Error:{e}")
            return {"result": False}
        result = _method(**kwargs)
        return result
