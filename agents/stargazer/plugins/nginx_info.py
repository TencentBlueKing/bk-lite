# -*- coding: utf-8 -*-
# @File：nginx_info.py.py
# @Time：2025/6/5 16:13
# @Author：bennie


import json

from core.nast_request import NATSClient
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class NginxInfo:
    """Class for collecting Nginx information."""

    def __init__(self, params: dict):
        self.node_id = params["node_id"]
        self.host = params.get("host", "")
        self.username = params.get("username")
        self.password = params.get("password")
        self.time_out = int(params.get("execute_timeout", 60))
        self.command = params.get("command", self.script)
        self.port = int(params.get("port", 22))
        self.nats_client = NATSClient()

    @property
    def script(self) -> str:
        result = """
#!/bin/bash
bk_host_innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址

# Function to get process port numbers
Get_Port_Join_Str() {
    port_arr_str=$(netstat -ntlp | grep -w "$1" | awk '{print $4}' | awk -F ':' '{print $NF}' | sed 's/[[:space:]]*$//g' | sed 's/^[[:space:]]*//g' | sort | uniq | tr '\n' '&')
    port_str="${port_arr_str%&}"
}

# Function to get process PID
Get_Nginx_Pid(){
    i=0
    nginx_pid=()
    pid_arr=$(ps -ef | grep nginx | grep -v grep | grep 'master process' | awk '{print $2}')
    if [ -z "$pid_arr" ]; then
        pid_arr=$(ps -ef | grep nginx | grep -v grep | awk '{print $2}')
    fi
    for pid in ${pid_arr[@]}
    do
        # 过滤掉端口不存在的进程
        port_str=$(netstat -ntlp | grep -w $pid)
        if [ -z "$port_str" ];then
            continue
        fi
        # 过滤掉不是nginx的进程
        is_nginx=$(echo $(readlink /proc/$pid/exe) | grep -i nginx)
        if [ -z "$is_nginx" ];then
            continue
        fi
        # 筛选后的pid
        nginx_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

# Function to get Nginx version
Get_Nginx_Version(){
    nginx_version=$("$1" -v 2>&1 | grep "nginx version" | awk -F'/' '{print $2}' | awk '{print $1}')
    if [ -z "$nginx_version" ]; then
        nginx_version="unknown"
    fi
    echo "$nginx_version"
}
# Function to get document root
Get_DocumentRoot(){
    if [ -f "$1" ]; then
        document_root=$(grep -i 'root' "$1" | awk '{print $2}' | sed 's/;$//')
        if [ -z "$document_root" ]; then
            document_root="unknown"
        fi
    else
        document_root="unknown"
    fi
    echo "$document_root"
}

# Function to get domain from Nginx configuration
Get_Domain(){
    if [ -f "$1" ]; then
        domain=$(grep -i 'server_name' "$1" | awk '{print $2}' | sed 's/;$//')
        if [ -z "$domain" ]; then
            domain="unknown"
        fi
    else
        domain="unknown"
    fi
    echo "$domain"
}
# Function to get include path from Nginx configuration
Get_Include_Path(){
    if [ -f "$1" ]; then
        include_path=$(grep -i 'include' "$1" | awk '{print $2}' | sed 's/;$//')
        if [ -z "$include_path" ]; then
            include_path="unknown"
        fi
    else
        include_path="unknown"
    fi
    echo "$include_path"
}

# Function to get SSL version
Get_SSL_Version(){
    ssl_version=$(openssl version | awk '{print $2}')
    if [ -z "$ssl_version" ]; then
        ssl_version="unknown"
    fi
    echo "$ssl_version"
}
Cover_Nginx(){
    inst_name_array=()

    Get_Nginx_Pid
    for pid in "${nginx_pid[@]}"
    do
        Get_Port_Join_Str "$pid"
        exe_path=$(readlink /proc/"$pid"/exe)
        if [[ "${inst_name_array[*]}" =~ $bk_host_innerip-nginx-$port_str ]]; then
            continue
        fi
        inst_name_array[${#inst_name_array[@]}]="$bk_host_innerip-nginx-$port_str"
        # Get Nginx version
        nginx_version=$(Get_Nginx_Version "$exe_path")
        # Get Nginx installation path
        install_path=$(dirname $(dirname "$exe_path"))
        # Get document root
        nginx_conf=$(echo "$cmdline" | grep -oP '(?<=-c )($\\S+)')
        if [ -n "$nginx_conf" ]; then
            if [[ "$nginx_conf" != /* ]]; then
                nginx_conf="$install_path/$nginx_conf"
            fi
        elif [ -n "$conf_path" ]; then
            nginx_conf="$conf_path"
        else
            nginx_conf="$install_path/conf/nginx.conf"
        fi
        log_path=$(grep -i 'error_log' "$nginx_conf" | awk '{print $2}' | sed 's/;$//')
        # Get domain
        domain=$(Get_Domain "$nginx_conf")
        # Get include path
        include_path=$(Get_Include_Path "$nginx_conf")
        # Get SSL version
        ssl_version=$(Get_SSL_Version)
        # =============can extend key=================
        json_template='{ \"bk_inst_name\": \"%s-nginx-%s\", \"bk_obj_id\": \"nginx\", \"ip_addr\": \"%s\", \"listen_port\": \"%s\", \"nginx_path\": \"%s\", \"version\": \"%s\", \"log_path\": \"%s\", \"config_path\": \"%s\", \"domain\": \"%s\", \"include_path\": \"%s\", \"ssl_version\": \"%s\"}'
        # Replace newlines with spaces in multi-line fields
        log_path=$(echo "$log_path" | tr '\n' ' ' | sed 's/ *$//')
        domain=$(echo "$domain" | tr '\n' ' ' | sed 's/ *$//')
        include_path=$(echo "$include_path" | tr '\n' ' ' | sed 's/ *$//')
        json_string=$(printf "$json_template" "$bk_host_innerip" "$port_str" "$bk_host_innerip" "$port_str" "$exe_path" "$nginx_version" "$log_path" "$nginx_conf" "$domain" "$include_path" "$ssl_version")
        echo "$json_string"
    done
}

Cover_Nginx

    """
        return result

    async def connect_nats(self):
        """异步连接 NATS"""
        await self.nats_client.connect()

    async def close_nats(self):
        """异步关闭 NATS"""
        await self.nats_client.close()

    @property
    def nast_id(self):
        """
        生成NATS ID
        :return:
        """
        return "ssh.execute" if self.username else "local.execute"

    def format_params(self):
        """
        格式化参数
        :return:
        """
        script_params = {
            "command": self.command,
            "port": self.port,
        }
        if self.username:
            script_params["user"] = self.username
            script_params["username"] = self.username
            script_params["password"] = self.password
            script_params["host"] = self.host
        if self.time_out:
            script_params["execute_timeout"] = self.time_out
        return script_params

    async def exec_script(self):
        """
        调用 NATS 执行脚本
        """
        exec_params = {
            "args": [self.format_params()],
            "kwargs": {}
        }
        subject = f"{self.nast_id}.{self.node_id}"
        response = await self.nats_client.request(subject=subject, params=exec_params)  # 使用 await 调用异步方法
        return json.loads(response["result"])

    async def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            await self.connect_nats()  # 异步连接 NATS
            data = await self.exec_script()  # 使用 await 获取执行结果
            prometheus_data = convert_to_prometheus_format({"nginx": [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(f"nginx_info main error! {traceback.format_exc()}")
        finally:
            await self.close_nats()
