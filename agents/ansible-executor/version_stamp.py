"""PyInstaller 打包时写入的 git SHA 与构建时间。

产品版本在 ``version_info.PRODUCT_VERSION``，不在这里生成。
源码树的 SHA 与构建时间保持 unknown。``ansible-executor.spec`` 在 Analysis
前改写本文件，生成归档后再恢复，避免把构建机上的值留在工作区。
"""

GIT_SHA = "unknown"
BUILD_TIMESTAMP = "unknown"
