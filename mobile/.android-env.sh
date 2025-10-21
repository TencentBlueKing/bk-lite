#!/bin/bash
# 安卓构建环境变量配置

# 设置 Android NDK 路径（自动使用最新版本）
export ANDROID_NDK_HOME=$ANDROID_HOME/ndk/$(ls -1 $ANDROID_HOME/ndk 2>/dev/null | sort -V | tail -n 1)
