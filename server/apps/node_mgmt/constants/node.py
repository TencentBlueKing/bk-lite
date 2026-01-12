class NodeConstants:
    """节点相关常量"""

    # 节点服务地址key
    SERVER_URL_KEY = "NODE_SERVER_URL"
    
    # NATS 服务器地址key
    NATS_SERVERS_KEY = "NATS_SERVERS"
    
    # 需要替换代理地址的环境变量key列表
    PROXY_ADDRESS_REPLACE_KEYS = [SERVER_URL_KEY, NATS_SERVERS_KEY]

    # 节点支持的操作系统
    LINUX_OS = "linux"
    WINDOWS_OS = "windows"

    # 操作系统显示名称
    LINUX_OS_DISPLAY = "Linux"
    WINDOWS_OS_DISPLAY = "Windows"

    # 权限相关常量
    DEFAULT_PERMISSION = ["View", "Operate"]
    MODULE = "node"
