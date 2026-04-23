import sys
import types
from importlib import import_module


class _DummySSHPlugin:
    def __init__(self, params):
        self.params = params


class _DummyLogger:
    def error(self, *_args, **_kwargs):
        return None


sys.modules.setdefault("sanic", types.ModuleType("sanic"))
sanic_log_stub = types.ModuleType("sanic.log")
sanic_log_stub.logger = _DummyLogger()
script_executor_stub = types.ModuleType("plugins.script_executor")
script_executor_stub.SSHPlugin = _DummySSHPlugin


def test_config_file_path_uses_absolute_file_path_without_appending_name():
    sys.modules.setdefault("sanic.log", sanic_log_stub)
    sys.modules.setdefault("plugins.script_executor", script_executor_stub)
    config_file_module = import_module("plugins.inputs.config_file.config_file_info")
    plugin = config_file_module.ConfigFileInfo(
        {
            "config_file_path": "/etc/nginx/nginx.conf",
            "config_file_name": "nginx.conf",
        }
    )

    assert plugin._get_config_file_path() == "/etc/nginx/nginx.conf"
