#!/bin/bash
# domestic_linux (麒麟/统信/欧拉) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 采集国产操作系统(host_manage 商业版)
# 真实采集依赖国产 OS(麒麟 Kylin/统信 UOS/欧拉 openEuler)
# 输出:内核版本、OS 版本、包管理器
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# OS 类型检测
os_type="unknown"
if [ -f /etc/kylin-release ]; then
    os_type="kylin"
    os_version=$(cat /etc/kylin-release | head -1)
elif [ -f /etc/uos-release ]; then
    os_type="uos"
    os_version=$(cat /etc/uos-release | head -1)
elif [ -f /etc/openEuler-release ]; then
    os_type="openeuler"
    os_version=$(cat /etc/openEuler-release | head -1)
elif [ -f /etc/os-release ]; then
    os_type="other"
    os_version=$(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')
fi

# 内核
kernel=$(uname -r)

# 包管理器
pkg_mgr="unknown"
if command -v dnf >/dev/null 2>&1; then
    pkg_mgr="dnf"
elif command -v yum >/dev/null 2>&1; then
    pkg_mgr="yum"
elif command -v apt-get >/dev/null 2>&1; then
    pkg_mgr="apt"
fi

# CPU 架构
arch=$(uname -m)

# 监听端口(任意服务,简化只看 22 ssh)
listening=$(ss -tln 2>/dev/null | grep ':22 ' | head -1 | awk '{print $4}')

bk_inst_name="$bk_host_innerip-domestic_linux"
printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"domestic_linux","os_type":"%s","os_version":"%s","kernel":"%s","arch":"%s","pkg_manager":"%s"}\n' \
    "$bk_inst_name" "$bk_host_innerip" "$os_type" "$os_version" "$kernel" "$arch" "$pkg_mgr"