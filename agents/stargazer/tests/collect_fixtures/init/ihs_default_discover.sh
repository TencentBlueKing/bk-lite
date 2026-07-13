#!/bin/bash
# IHS (IBM HTTP Server) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 IHS 二进制安装(G5.1 amd64 CI 跑通)
# IBM HTTP Server 是 IBM WebSphere 配套 HTTP 服务器,基于 Apache HTTPD + IBM 模块
# 进程名:httpd / IBMHTTPServer
# 配置路径:/opt/IBM/HTTPServer/conf/httpd.conf
# 默认端口:80
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 IHS 进程(httpd 或 IBMHTTPServer)
ihs_pids=$(ps -ef | grep -E '[h]ttpd|[H]TTPServer' | grep -v 'grep' | awk '{print $2}')
if [ -z "$ihs_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $ihs_pids; do
    # cmdline
    cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    [ -z "$cmdline" ] && cmdline=$(ps -p "$pid" -o args= 2>/dev/null)

    # 监听端口
    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    # 安装路径(从 exe symlink 反推)
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/IBM/HTTPServer"

    # 版本(httpd -v)
    version=$($install_path/bin/httpd -v 2>&1 | head -1 | grep -oE 'Apache/[0-9.]+|IBM_HTTP_Server/[0-9.]+' | head -1)

    # 配置文件
    config="${install_path}/conf/httpd.conf"

    bk_inst_name="$bk_host_innerip-ihs-80"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"ihs","port":"80","version":"%s","install_path":"%s","config":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$config" "$listening" "$pid"
done