# -*- coding: utf-8 -*-
# @File：kafka_info.py
# @Time：2025/6/9 12:02
# @Author：bennie


import json

from core.nast_request import NATSClient
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class KafkaInfo:
    """Class for collecting kafka information."""

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

# 获取Java版本
get_jdk_version() {
    jpath=$1
    [[ -x "$jpath" ]] || { echo "unknown"; return; }
    version=$($jpath -version 2>&1 | grep 'version' | awk -F '\"' '{print $2}')
    echo ${version:-"unknown"}
}

# 获取Kafka版本
get_kafka_version() {
    installpath=$1
    [[ -z "$installpath" || ! -d "$installpath" ]] && { echo "unknown"; return; }
    [[ "$installpath" != */ ]] && installpath="${installpath}/"
    lib_path="${installpath}libs"
    [[ -d "$lib_path" ]] || { echo "unknown"; return; }
    version=$(find "$lib_path" -name 'kafka_*.jar' 2>/dev/null | head -1 | grep -oE 'kafka_[^-]+-[^-]+' | sed 's/^kafka_//;s/[.]jar$//')
    echo ${version:-"unknown"}
}

# 解析配置文件
parse_config() {
    cfg_path=$1
    declare -A config_dict
    [[ -f "$cfg_path" ]] || { declare -p config_dict; return; }
    
    while IFS= read -r line; do
        line_trimmed=$(echo "$line" | xargs)
        [[ -z "$line_trimmed" || "$line_trimmed" == \#* ]] && continue
        if [[ "$line_trimmed" == *=* ]]; then
            key=$(echo "$line_trimmed" | cut -d'=' -f1 | awk '{$1=$1;print}')
            value=$(echo "$line_trimmed" | cut -d'=' -f2- | awk '{$1=$1;print}')
            config_dict["$key"]="$value"
        fi
    done < "$cfg_path"
    declare -p config_dict
}

# 生成未知实例
generate_unknown_instance() {
    innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址
    inst_name="${innerip}-kafka-unknown"
    
    cat <<EOF
{
    "bk_inst_name": "$inst_name",
    "bk_obj_id": "kafka",
    "ip_addr": "$innerip",
    "port": "unknown",
    "version": "unknown",
    "bin_path": "unknown",
    "conf_path": "unknown",
    "log_path": "unknown",
    "java_path": "unknown",
    "java_version": "unknown",
    "xms": "unknown",
    "xmx": "unknown",
    "broker_id": "unknown",
    "io_threads": "unknown",
    "network_threads": "unknown",
    "socket_receive_buffer_bytes": "unknown",
    "socket_request_max_bytes": "unknown",
    "socket_send_buffer_bytes": "unknown"
}
EOF
}

# 主函数
main() {
    # 获取Kafka进程
    pid_list=$(ps -ef | grep kafka.Kafka | grep -v grep | awk '{print $2}')
    
    # 如果没有Kafka进程，生成未知实例
    [[ -z "$pid_list" ]] && generate_unknown_instance && exit 0

    for pid in $pid_list; do
        # 初始化所有变量
        port="unknown"
        install_path="unknown"
        cfg_path="unknown"
        log_path="unknown"
        exe="unknown"
        xms="unknown"
        xmx="unknown"
        broker_id="unknown"
        io_threads="unknown"
        network_threads="unknown"
        socket_receive="unknown"
        socket_request="unknown"
        socket_send="unknown"
        bin_path="unknown"
        kafka_version="unknown"
        java_version="unknown"

        # 获取进程基本信息
        command=$(ps -p $pid -o args=)
        cwd=$(pwdx $pid 2>/dev/null | awk '{print $2}')
        [[ -z "$cwd" ]] && cwd=$(readlink -f /proc/$pid/cwd)
        user=$(ps -p $pid -o user=)
        exe=$(readlink -f /proc/$pid/exe)
        
        # 解析配置文件路径
        cfg_param=$(echo "$command" | awk '{
            for(i=1; i<=NF; i++) {
                if ($i ~ /\.properties$/) {print $i; exit}
                if ($i == "-config") {print $(i+1); exit}
            }
        }')
        
        # 处理配置文件路径
        if [[ -n "$cfg_param" ]]; then
            if [[ "$cfg_param" != /* ]]; then
                if [[ "$cwd" == "/" ]]; then
                    cfg_path="/${cfg_param}"
                else
                    cfg_path="${cwd}/${cfg_param}"
                fi
            else
                cfg_path="$cfg_param"
            fi
        fi
        
        # 解析配置文件内容
        if [[ -f "$cfg_path" ]]; then
            eval $(parse_config "$cfg_path")
        fi
        
        # 获取端口
        if [[ -n "${config_dict[listeners]}" ]]; then
            IFS=',' read -ra listeners <<< "${config_dict[listeners]}"
            for listener in "${listeners[@]}"; do
                if [[ "$listener" =~ [:/] ]]; then
                    port=$(echo "$listener" | awk -F: '{print $NF}' | tr -d ']' | cut -d'-' -f1)
                    [[ -n "$port" ]] && break
                fi
            done
        fi
        [[ "$port" == "unknown" ]] && port="${config_dict[port]}"
        [[ "$port" == "unknown" ]] && port="${config_dict[listeners]}" | awk -F: '{print $NF}'
        
        # 获取安装路径
        classpath=$(echo "$command" | grep -oP -- '-cp\s+\K\S+')
        [[ -z "$classpath" ]] && classpath=$(echo "$command" | grep -oP -- '-classpath\s+\K\S+')
        
        if [[ -n "$classpath" ]]; then
            path=$(echo "$classpath" | awk -F: '{print $1}')
            install_path=$(dirname "$path" | sed 's/\/libs$//;s/\/bin$//')
        fi
        
        # 获取日志路径
        log_path=$(echo "$command" | grep -oP -- '-Dkafka\.logs\.dir=\K\S+')
        [[ -z "$log_path" && -n "${config_dict[log.dirs]}" ]] && 
            log_path=$(echo "${config_dict[log.dirs]}" | cut -d, -f1)

        # 获取Java内存设置
        xms=$(echo "$command" | grep -oP -- '-Xms\K\S+')
        xmx=$(echo "$command" | grep -oP -- '-Xmx\K\S+')
        
        # 获取其他配置参数
        broker_id="${config_dict[broker_id]:-unknown}"
        io_threads="${config_dict[num_io_threads]:-unknown}"
        network_threads="${config_dict[num_network_threads]:-unknown}"
        socket_receive="${config_dict[socket_receive_buffer_bytes]:-unknown}"
        socket_request="${config_dict[socket_request_max_bytes]:-unknown}"
        socket_send="${config_dict[socket_send_buffer_bytes]:-unknown}"
        
        # 计算bin路径
        if [[ "$install_path" != "unknown" ]]; then
            bin_path="${install_path}/bin"
        fi
        
        # 获取版本信息
        kafka_version=$(get_kafka_version "$install_path")
        java_version=$(get_jdk_version "$exe")
        
        # 生成实例名
        innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址
        inst_name="${innerip}-kafka-${port}"
        
        # 生成JSON输出
        cat <<EOF
{
    "bk_inst_name": "$inst_name",
    "bk_obj_id": "kafka",
    "ip_addr": "$innerip",
    "port": "$port",
    "version": "$kafka_version",
    "install_path": "$bin_path",
    "conf_path": "$cfg_path",
    "log_path": "$log_path",
    "java_path": "$exe",
    "java_version": "$java_version",
    "xms": "$xms",
    "xmx": "$xmx",
    "broker_id": "$broker_id",
    "io_threads": "$io_threads",
    "network_threads": "$network_threads",
    "socket_receive_buffer_bytes": "$socket_receive",
    "socket_request_max_bytes": "$socket_request",
    "socket_send_buffer_bytes": "$socket_send"
}
EOF
    done
}

main
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
            prometheus_data = convert_to_prometheus_format({"kafka": [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(f"kafka_info main error! {traceback.format_exc()}")
        finally:
            await self.close_nats()
