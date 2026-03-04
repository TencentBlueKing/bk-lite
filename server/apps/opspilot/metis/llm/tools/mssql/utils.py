"""MSSQL通用工具函数"""

import json

import pyodbc
from langchain_core.runnables import RunnableConfig
from loguru import logger


def prepare_context(config: RunnableConfig = None) -> dict:
    """
    准备MSSQL连接上下文

    从config中提取数据库连接参数,返回连接配置字典

    Args:
        config: RunnableConfig对象,包含配置参数

    Returns:
        dict: 数据库连接配置
    """
    if config is None:
        config = {}

    # 从config的configurable中提取参数
    configurable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})

    db_config = {
        "host": configurable.get("host", "localhost"),
        "port": configurable.get("port", 1433),
        "database": configurable.get("database", "master"),
        "user": configurable.get("user", "sa"),
        "password": configurable.get("password", ""),
    }

    return db_config


def get_available_driver() -> str:
    """
    获取可用的MSSQL ODBC驱动名称

    按优先级顺序尝试以下驱动:
    1. ODBC Driver 18 for SQL Server
    2. ODBC Driver 17 for SQL Server
    3. SQL Server (旧版驱动)

    Returns:
        str: 可用的驱动名称

    Raises:
        RuntimeError: 如果没有找到可用的驱动
    """
    # 按优先级排序的驱动列表
    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]

    try:
        available_drivers = pyodbc.drivers()
        for driver in preferred_drivers:
            if driver in available_drivers:
                return driver
    except Exception as e:
        logger.warning(f"获取ODBC驱动列表失败: {e}")

    # 如果无法获取驱动列表,返回默认驱动让pyodbc尝试
    raise RuntimeError("未找到可用的SQL Server ODBC驱动。请安装以下驱动之一: " "ODBC Driver 18 for SQL Server, ODBC Driver 17 for SQL Server, 或 SQL Server")


def get_db_connection(config: RunnableConfig = None, database: str = None):
    """
    获取数据库连接

    Args:
        config: RunnableConfig对象
        database: 可选的数据库名,如果提供则覆盖config中的database

    Returns:
        pyodbc.Connection: 数据库连接对象
    """
    db_config = prepare_context(config)

    # 如果提供了database参数,则覆盖配置中的database
    if database:
        db_config["database"] = database

    try:
        driver = get_available_driver()
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={db_config['host']},{db_config['port']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['user']};"
            f"PWD={db_config['password']}"
        )

        # 对于Driver 18,可能需要额外的TrustServerCertificate设置
        if "18" in driver:
            conn_str += ";TrustServerCertificate=yes"

        conn = pyodbc.connect(conn_str, timeout=10)
        return conn
    except pyodbc.Error as e:
        logger.error(f"数据库连接失败: {e}")
        raise


def execute_readonly_query(query: str, params: tuple = None, config: RunnableConfig = None, database: str = None):
    """
    安全执行只读查询

    Args:
        query: SQL查询语句
        params: 查询参数(用于参数化查询),使用?作为占位符
        config: RunnableConfig对象
        database: 可选的数据库名,如果提供则连接到指定数据库

    Returns:
        list: 查询结果列表
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection(config, database=database)
        cursor = conn.cursor()

        # 执行查询
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # 获取列名
        columns = [column[0] for column in cursor.description]

        # 获取结果并转换为字典列表
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return results

    except pyodbc.Error as e:
        logger.error(f"查询执行失败: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def format_size(bytes_value: int) -> str:
    """
    格式化字节大小为可读格式

    Args:
        bytes_value: 字节数

    Returns:
        str: 格式化后的大小字符串(如 "1.5 GB")
    """
    if bytes_value is None:
        return "0 B"

    bytes_value = int(bytes_value)

    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0

    return f"{bytes_value:.2f} EB"


def format_duration(milliseconds: float) -> str:
    """
    格式化时间为可读格式

    Args:
        milliseconds: 毫秒数

    Returns:
        str: 格式化后的时间字符串(如 "1.5s", "200ms")
    """
    if milliseconds is None:
        return "0ms"

    milliseconds = float(milliseconds)

    if milliseconds < 1:
        return f"{milliseconds * 1000:.2f}μs"
    elif milliseconds < 1000:
        return f"{milliseconds:.2f}ms"
    elif milliseconds < 60000:
        return f"{milliseconds / 1000:.2f}s"
    elif milliseconds < 3600000:
        return f"{milliseconds / 60000:.2f}min"
    else:
        return f"{milliseconds / 3600000:.2f}h"


def parse_mssql_version(config: RunnableConfig = None) -> dict:
    """
    解析MSSQL版本信息

    Args:
        config: RunnableConfig对象

    Returns:
        dict: 版本信息
    """
    try:
        result = execute_readonly_query("SELECT @@VERSION as version, SERVERPROPERTY('ProductVersion') as product_version", config=config)
        version_string = result[0]["version"]
        product_version = result[0]["product_version"]

        # 解析主版本号
        major_version = int(product_version.split(".")[0]) if product_version else 0

        return {"full_version": version_string, "version_number": product_version, "major_version": major_version}
    except Exception as e:
        logger.error(f"解析版本失败: {e}")
        return {"full_version": "unknown", "version_number": "unknown", "major_version": 0}


def safe_json_dumps(data: dict) -> str:
    """
    安全的JSON序列化,处理特殊类型

    Args:
        data: 要序列化的数据

    Returns:
        str: JSON字符串
    """

    def default_handler(obj):
        """处理无法序列化的对象"""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)

    return json.dumps(data, default=default_handler, ensure_ascii=False, indent=2)


def calculate_percentage(part: float, total: float) -> float:
    """
    计算百分比

    Args:
        part: 部分值
        total: 总值

    Returns:
        float: 百分比(0-100)
    """
    if total == 0:
        return 0.0
    return round((part / total) * 100, 2)
