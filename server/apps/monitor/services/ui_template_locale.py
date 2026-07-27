"""UI 模板按 locale 切换中英文字段。

UI.json 的 form_fields/table_columns 中每条带 label 字段(中文)。
同时支持 label_en(英文);如果用户 locale 属于英语系,且 label_en 非空,
就用 label_en 替换 label 再返回。

通用规则:任意 string 字段若有对应的 `<field>_en` 字段且非空,英语 locale 下用之替换。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_EN_LOCALES = {"en", "en-us", "en-gb"}

# UI.json 的历史模板中有一小组重复的输入提示尚未提供 ``*_en`` 字段。
# 仅对这里审定过的精确文案回退，避免把任意中文内容当作可自动翻译的文本。
_EN_FALLBACKS = {
    "SNMP Community 字符串": "SNMP Community String",
    "加密协议 (DES/AES)": "Privacy Protocol (DES/AES)",
    "安全名称": "Security Name",
    "目标主机 IP": "Target Host IP",
    "认证协议 (MD5/SHA)": "Authentication Protocol (MD5/SHA)",
    "请输入 IP 地址": "Enter an IP address",
    "超时时间（秒）": "Timeout (seconds)",
    "选择 SNMP 版本": "Select SNMP Version",
    "选择安全级别": "Select Security Level",
    "主机地址": "Host Address",
    "Docer守护进程连接地址，默认为 unix:///var/run/docker.sock": "Docker daemon address; defaults to unix:///var/run/docker.sock",
    "IP地址": "IP Address",
    "数据库类型": "Database Type",
    "采样窗口": "Sampling Window",
    "https://example.com 或 https://[2001:db8::1]/": "https://example.com or https://[2001:db8::1]/",
    "分页大小": "Page Size",
    "可选，如 PING\\r\\n": "Optional, for example PING",
    "可选，如 PONG": "Optional, for example PONG",
    "密码（可选）": "Password (optional)",
    "数据库名称": "Database Name",
    "数据库连接的最长等待时间（秒）": "Database connection timeout (seconds)",
    "最长连接时长（秒）": "Maximum connection lifetime (seconds)",
    "用户名（可选）": "Username (optional)",
    "私钥口令": "Private key passphrase",
    "采集指标配置名称": "Collector configuration name",
    "采集超时时间（秒）": "Collection timeout (seconds)",
    "URL必须以http://或https://开头": "URL must start with http:// or https://",
    "地址需以 http:// 或 https:// 开头": "Address must start with http:// or https://",
    "服务器地址必须是以http://或https://开头的完整 debug/vars 地址": "Server address must be a complete debug/vars URL starting with http:// or https://",
    "服务器地址必须以http://或https://开头": "Server address must start with http:// or https://",
    "请输入有效的域名、IPv4或IPv6地址": "Enter a valid domain name, IPv4 address, or IPv6 address",
    "URL必须以http://或https://开头，IPv6地址需使用方括号": "URL must start with http:// or https://; IPv6 addresses must use brackets",
    "请输入有效的域名、IPv4或IPv6地址（IPv6无需方括号）": "Enter a valid domain name, IPv4 address, or IPv6 address (IPv6 does not need brackets)",
    "推荐仅采集 Linux 的 ext4、xfs、btrfs，或 Windows 的 NTFS、ReFS；留空表示不按类型限制。": "We recommend collecting only Linux ext4, xfs, and btrfs, or Windows NTFS and ReFS. Leave empty to avoid filesystem-type filtering.",
    "临时盘/容器盘：tmpfs、devtmpfs、overlay、aufs、squashfs；光盘：iso9660；常见 U 盘：vfat、exfat、fat、fat32。黑名单优先于仅采集列表；不默认排除 ntfs。": "Temporary or container filesystems: tmpfs, devtmpfs, overlay, aufs, squashfs; optical media: iso9660; common USB filesystems: vfat, exfat, fat, fat32. The denylist takes precedence over the allowlist; NTFS is not excluded by default.",
    "从设备请求数据的超时时间，超过配置时间（例如 10 秒）的请求将被视为失败": "Timeout for requesting data from the device. Requests exceeding the configured duration, for example 10 seconds, are treated as failures.",
    "监控的目标主机的 IP 地址，用于标识数据收集的来源": "IP address of the monitored target host, used to identify the source of collected data.",
    "安全级别设置，例如 authPriv 表示同时使用认证和隐私（加密）": "Security-level setting; for example, authPriv enables both authentication and privacy (encryption).",
    "指定要使用的 SNMP 协议版本，例如 v2c 或 v3，定义通信机制和安全级别": "SNMP protocol version to use, such as v2c or v3, which defines the communication mechanism and security level.",
    "用于 SNMPv2c 的认证字符串，类似于密码，允许访问设备的 SNMP 数据": "Authentication string for SNMPv2c, similar to a password, that allows access to the device's SNMP data.",
    "用于 SNMPv3 认证的用户名": "Username for SNMPv3 authentication.",
    "用于保护传输数据的加密协议": "Encryption protocol used to protect data in transit.",
    "用于保护认证过程的认证协议": "Authentication protocol used to protect the authentication process.",
    "用于加密的密码，与选择的加密协议对应": "Password used for encryption, corresponding to the selected encryption protocol.",
    "用于认证的密码，与选择的认证协议对应": "Password used for authentication, corresponding to the selected authentication protocol.",
    "配置SNMP端口号，通常使用161端口与设备进行通信": "SNMP port number, usually port 161, used to communicate with the device.",
    "与设备进行通信的主机": "Host used to communicate with the device.",
    "与设备进行通信的端口": "Port used to communicate with the device.",
    "监控的目标网址链接，以检测其可用性和性能": "Target website URL to monitor for availability and performance.",
    "JMX Exporter 本地监听端口，Telegraf 将从该端口抓取指标。": "Local JMX Exporter listen port from which Telegraf scrapes metrics.",
    "HTTPS 场景下是否跳过服务端证书校验": "Whether to skip server-certificate verification for HTTPS.",
    "指定程序运行时应监听的端口号，用于接受外部请求和连接": "Port on which the program should listen at runtime to accept external requests and connections.",
    "监控对象的服务器地址": "Server address of the monitored object.",
    "HTTPS 双向认证时使用的客户端密钥路径": "Client key path used for HTTPS mutual authentication.",
    "HTTPS 双向认证时使用的客户端证书路径": "Client certificate path used for HTTPS mutual authentication.",
    "指定当前程序的数据库密码": "Database password for the current program.",
    "指定当前程序的数据库用户名": "Database username for the current program.",
    "数据库类型，例如 MySQL、PostgreSQL 等": "Database type, for example MySQL or PostgreSQL.",
    "监控的目标网址链接，以检测其可用性和性能。": "Target website URL to monitor for availability and performance.",
    "逗号分隔；黑名单优先于仅采集列表，例如 vfat,exfat,ntfs。": "Comma-separated; the denylist takes precedence over the allowlist, for example vfat,exfat,ntfs.",
    "指定当前程序的版本详情": "Version details of the current program.",
    "是否启用 SASL 认证（用户名和密码）": "Whether to enable SASL authentication with a username and password.",
    "用于处理和响应通过发布端口接收的请求，包括请求的解析、处理和返回结果的完整流程": "Handles and responds to requests received through the publishing port, including parsing, processing, and returning results.",
    "按正则包含要采集的 Topic": "Regular expression for topics to include in collection.",
    "按正则排除不需要采集的 Topic": "Regular expression for topics to exclude from collection.",
    "按正则包含要采集的消费组": "Regular expression for consumer groups to include in collection.",
    "按正则排除不需要采集的消费组": "Regular expression for consumer groups to exclude from collection.",
    "要监控的服务名称，确保其与实际运行的服务一致": "Name of the service to monitor; ensure that it matches the running service.",
    "etcd Prometheus 指标地址，填写完整 URL": "etcd Prometheus metrics endpoint; enter the complete URL.",
    "HTTPS 访问时使用的 CA 证书路径": "CA certificate path used for HTTPS access.",
    "InfluxDB v1 debug 接口地址，通常为 http://host:8086/debug/vars": "InfluxDB v1 debug endpoint, typically http://host:8086/debug/vars.",
    "如接口启用 Basic Auth 可填写用户名": "Username to provide when the endpoint enables Basic Auth.",
    "如接口启用 Basic Auth 可填写密码": "Password to provide when the endpoint enables Basic Auth.",
    "单次请求 `debug/vars` 接口的超时时间（单位：秒）": "Timeout for a single request to the debug/vars endpoint, in seconds.",
    "HTTPS 场景下使用的 CA 证书路径": "CA certificate path used for HTTPS.",
    "用于连接 MySQL 数据库的用户名": "Username used to connect to the MySQL database.",
    "用于连接 MySQL 数据库的密码": "Password used to connect to the MySQL database.",
    "监控的Docker容器所在主机的网络地址，用于准确定位和采集性能数据": "Network address of the host running the monitored Docker container, used to locate it and collect performance data.",
    "监控CPU使用情况，包括利用率百分比、平均负载以及系统时间与用户时间的占比": "Monitors CPU usage, including utilization percentage, average load, and system versus user time.",
    "监控磁盘使用情况，包括磁盘空间、读/写速率以及其他相关指标": "Monitors disk usage, including disk space, read/write rates, and other related metrics.",
    "监控磁盘输入/输出操作的性能和活动情况": "Monitors disk input/output performance and activity.",
    "监控内存使用情况，包括内存利用率和可用内存": "Monitors memory usage, including memory utilization and available memory.",
    "监控网络性能，包括网络流量、带宽使用率和延迟": "Monitors network performance, including traffic, bandwidth utilization, and latency.",
    "监控运行进程的信息，包括进程数量、CPU 使用率和内存消耗": "Monitors running-process information, including process count, CPU utilization, and memory consumption.",
    "监控整体系统性能和运行状况，包括系统运行时间、平均负载以及一般活动水平等指标": "Monitors overall system performance and health, including uptime, average load, and general activity metrics.",
    "监控Nvidia-GPU使用情况，包括利用率百分比、显存使用和温度等指标": "Monitors Nvidia GPU usage, including utilization percentage, video-memory usage, and temperature.",
    "逗号分隔；留空表示不限制类型，例如 ext4,xfs。": "Comma-separated; leave empty to avoid type restrictions, for example ext4,xfs.",
    "目标主机的IP地址": "IP address of the target host.",
    "目标主机操作系统类型": "Operating-system type of the target host.",
    "逗号分隔；留空表示不限制类型，例如 ext4,xfs 或 NTFS,ReFS。": "Comma-separated; leave empty to avoid type restrictions, for example ext4,xfs or NTFS,ReFS.",
    "SSH/WinRM 登录用户名": "SSH/WinRM login username.",
    "Linux SSH 认证方式。Windows 始终使用 WinRM 密码认证。": "Linux SSH authentication method. Windows always uses WinRM password authentication.",
    "SSH/WinRM 登录密码": "SSH/WinRM login password.",
    "Linux SSH 私钥内容，仅认证方式为 SSH密钥 时使用": "Linux SSH private-key contents, used only when the authentication method is SSH key.",
    "Linux SSH 私钥口令，可为空": "Linux SSH private-key passphrase; may be empty.",
    "连接端口。Linux SSH 默认 22，Windows WinRM 默认 5986。": "Connection port. Linux SSH defaults to 22 and Windows WinRM defaults to 5986.",
    "Windows WinRM 协议": "Windows WinRM protocol.",
    "推荐 NTLM。Basic 需要目标 Windows 开启 Basic 认证，默认通常未开启。": "NTLM is recommended. Basic requires Basic authentication to be enabled on the target Windows host, which is usually disabled by default.",
    "HTTPS WinRM 是否校验证书。自签证书场景建议关闭。": "Whether HTTPS WinRM validates certificates. Disable it for self-signed certificates.",
    "目标 Windows 主机的 IP 地址": "IP address of the target Windows host.",
    "WMI 查询账号，支持 domain\\user 或 user@domain": "WMI query account; supports domain\\user or user@domain.",
    "WMI 查询账号密码": "WMI query account password.",
    "WMI 命名空间，默认 root\\cimv2": "WMI namespace; defaults to root\\cimv2.",
    "逗号分隔；留空表示不限制类型，例如 NTFS,ReFS。": "Comma-separated; leave empty to avoid type restrictions, for example NTFS,ReFS.",
    "逗号分隔；黑名单优先于仅采集列表，例如 FAT,FAT32,exFAT。": "Comma-separated; the denylist takes precedence over the allowlist, for example FAT,FAT32,exFAT.",
    "WMI 连接和查询超时时间（秒）": "WMI connection and query timeout in seconds.",
    "监控数据采集间隔（秒）": "Monitoring-data collection interval in seconds.",
    "表示使用 LAN+ 协议进行访问（通常用于较新版本的 IPMI）": "Indicates access through the LAN+ protocol, usually used by newer IPMI versions.",
    "HAProxy stats 页地址（不含账密），Telegraf 采集时自动追加 ;csv": "HAProxy stats page address without credentials; Telegraf automatically appends ;csv during collection.",
    "stats 页 basic-auth 用户名（未开启认证则留空）": "Basic-auth username for the stats page; leave empty when authentication is disabled.",
    r"WMI 查询账号，支持 domain\\user 或 user@domain": "WMI query account; supports domain\\user or user@domain.",
    r"WMI 命名空间，默认 root\\cimv2": "WMI namespace; defaults to root\\cimv2.",
    "stats 页 basic-auth 密码（未开启认证则留空）": "Basic-auth password for the stats page; leave empty when authentication is disabled.",
    "监控数据的采集时间间隔（单位为秒）": "Monitoring-data collection interval in seconds.",
    "TCP 探测目标主机，支持域名、IPv4 或 IPv6（无需手动加方括号）。": "TCP probe target host; supports domain names, IPv4, and IPv6 without manually adding brackets.",
    "TCP 探测目标端口。": "TCP probe target port.",
    "单次 TCP 连接的超时时间（单位：秒）。": "Timeout for a single TCP connection in seconds.",
    "建连后发送的字符串，留空表示仅做端口连通性探测。": "String sent after connecting; leave empty to perform only a port-connectivity probe.",
    "期望在响应中匹配到的字符串，需与发送内容配合使用。": "String expected in the response; use it together with the sent content.",
    "访问 BES JMX 服务的用户名。": "Username for accessing the BES JMX service.",
    "访问 BES JMX 服务的密码。": "Password for accessing the BES JMX service.",
    "BES 需先开启远程 JMX/RMI 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi。": "Enable remote BES JMX/RMI and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi.",
    "达梦数据库登录用户名": "Dameng database login username.",
    "达梦数据库登录密码": "Dameng database login password.",
    "DM-Exporter 本地监听端口，Telegraf 将从该端口抓取指标": "Local DM-Exporter listen port from which Telegraf scrapes metrics.",
    "达梦数据库主机地址": "Dameng database host address.",
    "达梦数据库服务端口": "Dameng database service port.",
    "内置达梦采集配置名称，对应 dm.collector.yml 中的 collector_name": "Built-in Dameng collection configuration name, corresponding to collector_name in dm.collector.yml.",
    "DM-Exporter 单次 SQL 采集超时时间（单位：秒）": "DM-Exporter timeout for a single SQL collection in seconds.",
    "DM-Exporter 数据库连接最长复用时间（单位：分钟）": "Maximum DM-Exporter database-connection reuse time in minutes.",
    "IBM MQ 服务连接地址，格式为 ip(port)，例如 10.0.0.5(1414)": "IBM MQ service connection address in ip(port) format, for example 10.0.0.5(1414).",
    "要监控的队列管理器名称，例如 QM1": "Queue-manager name to monitor, for example QM1.",
    "用于客户端连接的服务器连接通道名称，例如 SVRCONN": "Server-connection channel name used for client connections, for example SVRCONN.",
    "连接队列管理器使用的用户名（可选）": "Username used to connect to the queue manager (optional).",
    "连接队列管理器使用的密码（可选）": "Password used to connect to the queue manager (optional).",
    "需要监控的队列过滤表达式，默认 * 表示所有队列，可用逗号分隔，! 前缀表示排除": "Queue filter expression to monitor. The default * means all queues; use commas to separate values and ! as an exclusion prefix.",
    "需要监控的通道过滤表达式，默认 * 表示所有通道，可用逗号分隔，! 前缀表示排除": "Channel filter expression to monitor. The default * means all channels; use commas to separate values and ! as an exclusion prefix.",
    "队列管理器字符集编码（CCSID），通常无需填写；如出现编码异常可设为 819 或 1208": "Queue-manager character-set encoding (CCSID). It is normally unnecessary; set 819 or 1208 if encoding issues occur.",
    "节点上 IBM MQ redistributable client 的安装目录。探针以客户端方式连接 MQ，依赖该目录下的客户端库；默认 /opt/mqm，若客户端安装在其他目录请修改": "IBM MQ redistributable-client installation directory on the node. The probe connects as a client and requires the client libraries in this directory; default is /opt/mqm.",
    "IBM MQ 客户端动态库路径（LD_LIBRARY_PATH），探针运行时据此加载 MQ 客户端库；默认 /opt/mqm/lib64，须与 MQ 客户端安装目录一致": "IBM MQ client dynamic-library path (LD_LIBRARY_PATH) used by the probe at runtime; defaults to /opt/mqm/lib64 and must match the client installation directory.",
    "探针在本机暴露 /metrics 的监听端口，供采集器抓取": "Local probe listen port exposing /metrics for the collector to scrape.",
    "访问 JBoss JMX 服务的用户名。": "Username for accessing the JBoss JMX service.",
    "访问 JBoss JMX 服务的密码。": "Password for accessing the JBoss JMX service.",
    "JBoss/WildFly 需先开启远程 JMX 或 management endpoint 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:remote+http://127.0.0.1:9990。": "Enable remote JMX or the management endpoint for JBoss/WildFly and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:remote+http://127.0.0.1:9990.",
    "访问 Jetty JMX 服务的用户名。": "Username for accessing the Jetty JMX service.",
    "访问 Jetty JMX 服务的密码。": "Password for accessing the Jetty JMX service.",
    "Jetty 需先开启远程 JMX 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi。": "Enable remote Jetty JMX and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi.",
    "数据库连接的最长等待时间，单位为秒，超过该时间的连接请求将被终止": "Maximum database-connection wait time in seconds; connection requests exceeding it are terminated.",
    "采集超时时间，单位为秒，超过该时间的采集请求将被终止": "Collection timeout in seconds; collection requests exceeding it are terminated.",
    "采集指标配置名称，对应`collector_name`，一般使用模糊匹": "Collection metric configuration name corresponding to collector_name; fuzzy matching is generally used.",
    "最长连接时长，单位为秒，超过该时间的连接将被终止": "Maximum connection lifetime in seconds; connections exceeding it are terminated.",
    "要监控的 OceanBase 租户名（tenant）": "OceanBase tenant name to monitor.",
    "Nacos Prometheus 指标地址，例如 http://127.0.0.1:8848/nacos/actuator/prometheus。": "Nacos Prometheus metrics endpoint, for example http://127.0.0.1:8848/nacos/actuator/prometheus.",
    "访问指标接口的用户名，可选。": "Username for accessing the metrics endpoint (optional).",
    "访问指标接口的密码，可选。": "Password for accessing the metrics endpoint (optional).",
    "填写 tlqstat 或规范化绝对路径。": "Enter tlqstat or a normalized absolute path.",
    "可选，只允许目标机上的规范化绝对文件路径。": "Optional; only normalized absolute file paths on the target host are allowed.",
    "监控采集周期，单位秒。": "Monitoring collection interval in seconds.",
    "访问 TongWeb JMX 服务的用户名。": "Username for accessing the TongWeb JMX service.",
    "访问 TongWeb JMX 服务的密码。": "Password for accessing the TongWeb JMX service.",
    "TongWeb 需先开启远程 JMX/RMI 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi。": "Enable remote TongWeb JMX/RMI and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi.",
    "访问 WebLogic JMX 服务的用户名。": "Username for accessing the WebLogic JMX service.",
    "访问 WebLogic JMX 服务的密码。": "Password for accessing the WebLogic JMX service.",
    "WebLogic 需先开启远程 JMX/RMI 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:rmi:///jndi/rmi://127.0.0.1:1097/jmxrmi。": "Enable remote WebLogic JMX/RMI and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:rmi:///jndi/rmi://127.0.0.1:1097/jmxrmi.",
    "访问 WebSphere JMX 服务的用户名。": "Username for accessing the WebSphere JMX service.",
    "访问 WebSphere JMX 服务的密码。": "Password for accessing the WebSphere JMX service.",
    "WebSphere 需先开启远程 JMX 并确保采集节点网络可达，填写 JMX 连接地址，例如 service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi。": "Enable remote WebSphere JMX and ensure network reachability from the collection node; enter a JMX connection address such as service:jmx:rmi:///jndi/rmi://127.0.0.1:1099/jmxrmi.",
}

_EN_GUIDE_FALLBACK = "See the plugin guide for field-specific configuration details."


def _is_english(locale: str) -> bool:
    return (locale or "").lower().startswith("en")


def _localize_node(node: Any, locale: str) -> Any:
    """递归遍历节点,英语 locale 下用每个字段的 <name>_en 变体替换。"""
    if not _is_english(locale):
        return node
    if isinstance(node, dict):
        # 优先做 key 翻译:对 dict 中每个 string 字段,若存在对应的 <name>_en 变体,
        # 且变体非空,则替换。
        keys_snapshot = list(node.keys())
        for k in keys_snapshot:
            v = node[k]
            if isinstance(v, str):
                en_key = f"{k}_en"
                if en_key in node and isinstance(node[en_key], str) and node[en_key].strip():
                    node[k] = node[en_key]
                elif v in _EN_FALLBACKS:
                    node[k] = _EN_FALLBACKS[v]
                elif k == "guide_short" and any("\u4e00" <= char <= "\u9fff" for char in v):
                    # 不把未审校的长运维说明伪装成自动翻译；英文界面显示稳定的引导语。
                    node[k] = _EN_GUIDE_FALLBACK
            elif isinstance(v, (dict, list)):
                _localize_node(v, locale)
    elif isinstance(node, list):
        for item in node:
            _localize_node(item, locale)
    return node


def localize_ui_template(content: dict, locale: str) -> dict:
    """根据 locale 返回 UI.json 的本地化版本。空 dict 直接返回。"""
    if not content:
        return content
    if not _is_english(locale):
        return content
    return _localize_node(deepcopy(content), locale)
