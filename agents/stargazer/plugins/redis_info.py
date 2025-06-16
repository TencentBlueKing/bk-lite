# -*- coding: utf-8 -*-
# @File: redis_info.py
# @Time: 2025/6/4 12:00
# @Author: bennie

import json

from core.nast_request import NATSClient
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class RedisInfo:
    """Class for collecting Redis information."""

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

# Function to run command
run_cmd() {
    cmd=$1
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

# Function to get Redis processes
_procs() {
    local redis_dict=()
    local pids=$(ps -e -o pid,comm | grep redis-server | awk '{print $1}')
    for pid in $pids; do
        local cmdline=$(ps -p $pid -o args=)
        local exe=$(readlink -f /proc/$pid/exe)
        local install_path=$(dirname $exe | sed 's/\bin$//')
        local redis_cli=$(ps -p $pid -o comm= | sed 's/redis-server$/redis-cli/')

        # 修改正则表达式以匹配 IP 和端口
        # local ipport=$(echo $cmdline | grep -oP '([0-9]+.[0-9]+.[0-9]+.[0-9]+|*):[0-9]+')
        local ipport=$(echo "$cmdline" | grep -oP '(?:[0-9]{1,3}.){3}[0-9]{1,3}(?::[0-9]+)?')
        
        if [ -n "$ipport" ]; then
            local redis_ip=$(echo $ipport | cut -d: -f1)
            local redis_port=$(echo $ipport | cut -d: -f2)
            if [ "$redis_ip" = "*" ]; then
                redis_ip="0.0.0.0"
            fi
            redis_dict+=("$pid:$redis_ip:$redis_port:$redis_cli:$install_path")
        fi
    done
    echo "${redis_dict[@]}"
}

# Function to discover Redis
discover_redis() {
    local procs=($(_procs))
    if [ ${#procs[@]} -eq 0 ]; then
        echo "{}"
        exit 0
    fi

    # 获取主机内网 IP 地址
    bk_host_innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址

    for proc in "${procs[@]}"; do
        local pid=$(echo $proc | cut -d: -f1)
        local ip=$(echo $proc | cut -d: -f2)
        local port=$(echo $proc | cut -d: -f3)
        local redis_cli=$(echo $proc | cut -d: -f4)
        local install_path=$(echo $proc | cut -d: -f5)

        local version=$(run_cmd "$redis_cli --version" | awk '{print $2}')

        # 新增逻辑：获取最大连接数
        local max_clients=$(run_cmd "$redis_cli config get maxclients" | grep -A1 "maxclients" | tail -n1)

        # 新增逻辑：获取最大内存
        local max_memory=$(run_cmd "$redis_cli config get maxmemory" | grep -A1 "maxmemory" | tail -n1)

        # 新增逻辑：获取数据库角色
        local role=$(run_cmd "$redis_cli info replication" | grep "role:" | awk -F: '{print $2}' | tr -d '\r')

        bk_inst_name="${bk_host_innerip}-redis-${port}"

        # 修复 JSON 格式化问题，确保变量值正确插入
        redis_info=$(printf '{"bk_inst_name":"%s","bk_obj_id":"redis","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","max_clients":"%s","max_memory":"%s","role":"%s"}' \
            "$bk_inst_name" \
            "$bk_host_innerip" \
            "$port" \
            "$version" \
            "$install_path" \
            "$max_clients" \
            "$max_memory" \
            "$role"
        )

        echo "$redis_info"
    done
}

# Main script execution
discover_redis
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
            prometheus_data = convert_to_prometheus_format({"redis": [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(f"redis_info main error! {traceback.format_exc()}")
        finally:
            await self.close_nats()
