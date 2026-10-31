#!/bin/sh
# USN-8344-1 / USN-8221-1：只升级镜像中已经安装的 Ubuntu 24.04 系统包。
set -eu
set -f
. /etc/os-release
[ "$ID:$VERSION_ID" = ubuntu:24.04 ] || exit 0

packages=''
for package in python3-pip python3-pip-whl python-wheel-common python3-wheel python3-wheel-whl; do
    status=$(dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null) || status=''
    case "$status" in
        'ii '*) packages="$packages $package" ;;
    esac
done
[ -n "$packages" ] || exit 0

apt-get update
# 列表仅来自上面的固定包名，不安装镜像原本没有的构建工具。
apt-get install -y --no-install-recommends --only-upgrade $packages
for package in $packages; do
    case "$package" in
        python3-pip|python3-pip-whl) minimum='24.0+dfsg-1ubuntu1.3+esm1' ;;
        *) minimum='0.42.0-2ubuntu0.1~esm1' ;;
    esac
    installed=$(dpkg-query -W -f='${Version}' "$package")
    if ! dpkg --compare-versions "$installed" ge "$minimum"; then
        echo "$package 未取得安全补丁；请为构建配置包含 USN-8344-1 / USN-8221-1 修复的源（可能需要 Ubuntu Pro ESM）。" >&2
        exit 1
    fi
done
rm -rf /var/lib/apt/lists/*
