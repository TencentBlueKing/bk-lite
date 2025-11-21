# -- coding: utf-8 --
# @File: host_info_ssh.py
# @Time: 2025/4/30 15:54
# @Author: windyzhao


import json
import time
from typing import Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

from core.ssh_client import SSHClient


@dataclass
class HostInfo:
    """主机信息数据模型"""
    os_type: str
    os_version: str
    architecture: str
    cpu_model: str
    cpu_cores: str
    mem_total: str
    disk_total: str
    mac_address: str
    hostname: Optional[str] = None
    uptime: Optional[str] = None
    load_avg: Optional[str] = None
    collection_time: Optional[float] = None
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'HostInfo':
        """从字典创建HostInfo实例"""
        return cls(**data)

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.__dict__


class HostInfoCollector:
    """主机信息采集器"""

    def __init__(self, ssh_timeout: int = 30, command_timeout: int = 25,
                 max_workers: int = 5):
        """
        初始化采集器

        :param ssh_timeout: SSH连接超时(秒)
        :param command_timeout: 命令执行超时(秒)
        :param max_workers: 最大并发工作线程数
        """
        self.ssh_timeout = ssh_timeout
        self.command_timeout = command_timeout
        self.max_workers = max_workers

        # 预定义的采集命令脚本
        self.collect_script = self.script

    @property
    def script(self) -> str:
        """
        采集脚本
        权限要求
            SSH访问权限:
            需要有SSH登录目标主机的权限
            建议创建一个专用的只读账号用于信息采集
            命令执行权限:
            需要执行以下命令的权限:
            uname
            cat /etc/os-release
            lscpu
            free
            df
            ip 或 ifconfig
            文件读取权限:
            需要读取 /etc/os-release 文件的权限
            需要读取 /proc/cpuinfo 和 /proc/meminfo 的权限 (通过命令间接访问)
        """
        result = """#!/bin/bash
# 更健壮的采集脚本
set -e  # 遇到错误立即退出

# 定义fallback函数
unknown_or() {
    "$@" 2>/dev/null || echo "unknown"
}

# 操作系统信息
os_type=$(unknown_or uname -o)
os_version=$( (unknown_or grep 'PRETTY_NAME=' /etc/os-release || unknown_or grep 'VERSION=' /etc/os-release) | head -n1 | cut -d '"' -f 2)
architecture=$(unknown_or uname -m)
hostname=$(unknown_or hostname -f || unknown_or hostname)

# CPU信息
if unknown_or which lscpu >/dev/null; then
    cpu_model=$(unknown_or lscpu | grep -i 'model name' | awk -F: '{print $2}' | xargs)
    cpu_cores=$(unknown_or lscpu | grep -i '^CPU(s):' | awk -F: '{print $2}' | xargs)
else
    cpu_model=$(unknown_or grep -m1 -i 'model name' /proc/cpuinfo | awk -F: '{print $2}' | xargs)
    cpu_cores=$(unknown_or grep -c '^processor' /proc/cpuinfo)
fi

# 内存信息
if unknown_or which free >/dev/null; then
    mem_total=$(unknown_or free -m | awk '/Mem:/{print $2}')
else
    mem_total=$(unknown_or awk '/MemTotal/{printf "%.0f", $2/1024}' /proc/meminfo)
fi

# 磁盘信息
if unknown_or which df >/dev/null; then
    disk_total=$(unknown_or df -h --total 2>/dev/null | awk '/total/{print $2}' || unknown_or df -h | awk '{total+=$2}END{print total "G"}')
else
    disk_total="unknown"
fi

# 网络信息
mac_address=$( (unknown_or ip link show || unknown_or ifconfig -a) 2>/dev/null | awk '/ether/{print $2; exit}' || echo "unknown")

# 系统运行时间和负载
uptime=$(unknown_or uptime -p || unknown_or uptime | sed -n 's/^.*up *//p')
load_avg=$(unknown_or uptime | awk -F'load average: ' '{print $2}' || echo "unknown")

# 输出JSON结果
cat <<EOF
{
    "os_type": "$os_type",
    "os_version": "$os_version",
    "architecture": "$architecture",
    "cpu_model": "$cpu_model",
    "cpu_cores": "$cpu_cores",
    "mem_total": "${mem_total}MB",
    "disk_total": "$disk_total",
    "mac_address": "$mac_address",
    "hostname": "$hostname",
    "uptime": "$uptime",
    "load_avg": "$load_avg"
}
EOF
"""
        return result

    def _parse_result(self, output: str, exec_time: float) -> HostInfo:
        """解析命令输出为HostInfo对象"""
        try:
            data = json.loads(output)
            data["collection_time"] = exec_time
            return HostInfo.from_dict(data)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON output: {str(e)}")
            raise ValueError(f"Invalid JSON output: {str(e)}")

    def collect(self, host: str, username: str,
                password: Optional[str] = None, port: int = 22,
                key_filename: Optional[str] = None) -> HostInfo:
        """
        采集单个主机信息

        :return: HostInfo对象
        :raises: Exception 如果采集失败
        """
        start_time = time.time()
        ssh = SSHClient(timeout=self.ssh_timeout)

        try:
            # 建立连接
            print(f"正在连接主机 {host}...")
            ssh.connect(host, username, password, port, key_filename)
            print(f"成功连接到 {host}")

            # 执行采集命令
            print(f"正在执行采集命令...")
            result = ssh.execute_command(
                self.collect_script, self.command_timeout)
            print(f"命令执行完成，退出状态: {result.exit_status}")

            # 解析结果
            host_info = self._parse_result(
                result.stdout, time.time() - start_time)
            print(f"成功采集并解析来自 {host} 的信息")
            return host_info

        except Exception as e:
            return HostInfo(
                os_type="unknown",
                os_version="unknown",
                architecture="unknown",
                cpu_model="unknown",
                cpu_cores="unknown",
                mem_total="unknown",
                disk_total="unknown",
                mac_address="unknown",
                error=str(e)
            )
        finally:
            ssh.close()

    def test_basic_commands(self, host: str, username: str,
                            password: Optional[str] = None, port: int = 22,
                            key_filename: Optional[str] = None) -> None:
        """测试基本命令执行能力"""
        ssh = SSHClient(timeout=self.ssh_timeout)

        try:
            # 建立连接
            print(f"测试连接到 {host}...")
            ssh.connect(host, username, password, port, key_filename)
            print(f"连接成功")

            # 测试1: 简单echo命令
            print("\n测试1: 执行简单echo命令")
            result1 = ssh.execute_command(
                'echo "Hello World"', self.command_timeout)
            print(f"退出状态: {result1.exit_status}")
            print(f"标准输出: [{result1.stdout}]")
            print(f"标准错误: [{result1.stderr}]")

            # 测试2: 系统信息命令
            print("\n测试2: 系统信息命令")
            result2 = ssh.execute_command('uname -a', self.command_timeout)
            print(f"退出状态: {result2.exit_status}")
            print(f"标准输出: [{result2.stdout}]")
            print(f"标准错误: [{result2.stderr}]")

            # 测试3: JSON格式输出
            print("\n测试3: JSON格式输出")
            json_cmd = 'echo \'{"name":"test","value":123}\''
            result3 = ssh.execute_command(json_cmd, self.command_timeout)
            print(f"退出状态: {result3.exit_status}")
            print(f"标准输出: [{result3.stdout}]")
            print(f"标准错误: [{result3.stderr}]")

            # 测试4: 执行简单脚本
            print("\n测试4: 执行简单脚本")
            script_cmd = '''bash -c "echo '{\"os\":\"'$(uname -s)'\", \"hostname\":\"'$(hostname)'\"}'"'''
            result4 = ssh.execute_command(script_cmd, self.command_timeout)
            print(f"退出状态: {result4.exit_status}")
            print(f"标准输出: [{result4.stdout}]")
            print(f"标准错误: [{result4.stderr}]")

        finally:
            ssh.close()

    def batch_collect(self, hosts: List[Tuple[str, str, Optional[str], int, Optional[str]]]) -> Dict[str, HostInfo]:
        """
        批量采集多个主机信息

        :param hosts: 主机参数列表，每个元素为(host, username, password, port, key_filename)
        :return: 字典 {host: HostInfo}
        """
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_host = {
                executor.submit(
                    self.collect,
                    host=host,
                    username=username,
                    password=password,
                    port=port,
                    key_filename=key_filename
                ): host for (host, username, password, port, key_filename) in hosts
            }

            for future in as_completed(future_to_host):
                host = future_to_host[future]
                try:
                    results[host] = future.result()
                except Exception as e:
                    results[host] = HostInfo(
                        os_type="unknown",
                        os_version="unknown",
                        architecture="unknown",
                        cpu_model="unknown",
                        cpu_cores="unknown",
                        mem_total="unknown",
                        disk_total="unknown",
                        mac_address="unknown",
                        error=str(e)
                    )
                    print(f"Batch collection failed for {host}: {str(e)}")

        return results


def main():
    # 创建采集器实例
    collector = HostInfoCollector(
        ssh_timeout=20,
        command_timeout=15,
        max_workers=3
    )
    # 测试基本命令执行
    # print("\n测试基本命令执行:")
    # collector.test_basic_commands(
    #     host="192.168.1.100",
    #     username="root",
    #     password="asaslhskfgugugaskgdjygcysagdfydgasdbh"
    # )

    # 单主机采集示例
    print("\nSingle host collection:")
    single_host_info = collector.collect(
        host="192.168.1.100",
        username="root",
        password="asaslhskfgugugaskgdjygcysagdfydgasdbh"  # 或使用 key_filename="path/to/key"
    )
    print(json.dumps(single_host_info.to_dict(), indent=2))

    # 批量采集示例
    # print("\nBatch host collection:")
    # hosts_to_collect = [
    #     ("192.168.1.100", "collector", "password1", 22, None),
    #     ("192.168.1.101", "collector", None, 22, "/path/to/key"),
    #     ("192.168.1.102", "admin", "admin123", 2222, None)
    # ]
    #
    # results = collector.batch_collect(hosts_to_collect)
    # for host, info in results.items():
    #     print(f"\nHost: {host}")
    #     print(json.dumps(info.to_dict(), indent=2))


if __name__ == "__main__":
    main()
