# flake8: noqa
"""NATS handlers for system_mgmt, split by responsibility domain."""

from importlib import import_module


_MODULES = (
    "common",
    "auth",
    "clients",
    "users",
    "channels",
    "permissions",
    "login",
    "login_auth_bindings",
    "wechat",
    "otp",
    "settings",
    "audit",
)

for _module_name in _MODULES:
    _module = import_module(f"{__name__}.{_module_name}")
    for _name, _value in vars(_module).items():
        if not _name.startswith("__"):
            globals()[_name] = _value

_INTERNAL_EXPORTS = {"import_module", "_MODULES", "_module_name", "_module", "_INTERNAL_EXPORTS"}

__all__ = [name for name in globals() if not name.startswith("__") and name not in _INTERNAL_EXPORTS]
