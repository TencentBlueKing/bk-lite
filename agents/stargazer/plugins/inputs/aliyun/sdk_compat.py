"""Python 3.12 compatibility aliases for Alibaba Cloud's legacy vendored six."""

from __future__ import annotations

import importlib
import sys

import six


def _install_six_aliases(prefix: str) -> None:
    sys.modules[prefix] = six
    sys.modules[f"{prefix}.moves"] = six.moves
    for suffix in (
        "http_client",
        "queue",
        "urllib",
        "urllib.error",
        "urllib.parse",
        "urllib.request",
        "urllib.response",
        "urllib.robotparser",
    ):
        sys.modules[f"{prefix}.moves.{suffix}"] = importlib.import_module(
            f"six.moves.{suffix}"
        )


if sys.version_info >= (3, 12):
    # aliyun-python-sdk-core 与其内置 urllib3 均捆绑了只实现 find_module
    # 的旧版 six importer；Python 3.12 移除该导入协议后需指向新版 six。
    _install_six_aliases("aliyunsdkcore.vendored.six")
    _install_six_aliases(
        "aliyunsdkcore.vendored.requests.packages.urllib3.packages.six"
    )
