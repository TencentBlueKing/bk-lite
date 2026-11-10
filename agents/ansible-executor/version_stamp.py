"""PyInstaller 打包时写入的版本常量。

源码树保持 unknown。``ansible-executor.spec`` 在 Analysis 前改写本文件，
生成归档后再恢复，避免把构建机上的值留在工作区。
"""

GIT_SHA = "unknown"
BUILD_TIMESTAMP = "unknown"
ENCODE_ADHOC_MODULE_ARGS = "unknown"
LINUX_SCRIPT_DELIVERY = "unknown"
