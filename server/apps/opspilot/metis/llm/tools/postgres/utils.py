"""PostgreSQL通用工具函数"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.runnables import RunnableConfig
from loguru import logger


def prepare_context(config: RunnableConfig = None) -> dict:
    """
    准备PostgreSQL连接上下文

    从config中提取数据库连接参数,返回连接配置字典

    Args:
        config: RunnableConfig对象,包含配置参数

    Returns:
        dict: 数据库连接配置
    """
    if config is None:
        config = {}

    # 从config的configurable中提取参数
    configurable = config.get("configurable", {}) if isinstance(
        config, dict) else getattr(config, "configurable", {})

    db_config = {
        "host": configurable.get("host", "localhost"),
        "port": configurable.get("port", 5432),
        "database": configurable.get("database", "postgres"),
        "user": configurable.get("user", "postgres"),
        "password": configurable.get("password", ""),
    }

    return db_config


def get_db_connection(config: RunnableConfig = None, database: str = None):
    """
    获取数据库连接

    Args:
        config: RunnableConfig对象
        database: 可选的数据库名,如果提供则覆盖config中的database

    Returns:
        psycopg2.connection: 数据库连接对象
    """
    db_config = prepare_context(config)

    # 如果提供了database参数,则覆盖配置中的database
    if database:
        db_config["database"] = database

    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"数据库连接失败: {e}")
        raise


def execute_readonly_query(query: str, params: tuple = None, config: RunnableConfig = None, database: str = None):
    """
    安全执行只读查询

    Args:
        query: SQL查询语句
        params: 查询参数(用于参数化查询)
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

        # 开启只读事务
        cursor.execute("BEGIN TRANSACTION READ ONLY")

        # 执行查询
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # 获取结果
        results = cursor.fetchall()

        # 提交事务
        conn.commit()

        # 转换为列表字典
        return [dict(row) for row in results]

    except psycopg2.Error as e:
        logger.error(f"查询执行失败: {e}")
        if conn:
            conn.rollback()
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

    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
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


def parse_pg_version(config: RunnableConfig = None) -> dict:
    """
    解析PostgreSQL版本信息

    Args:
        config: RunnableConfig对象

    Returns:
        dict: 版本信息
    """
    try:
        result = execute_readonly_query(
            "SELECT version() as version", config=config)
        version_string = result[0]["version"]

        # 解析版本号
        # 例如: "PostgreSQL 14.5 on x86_64-pc-linux-gnu..."
        parts = version_string.split()
        version_number = parts[1] if len(parts) > 1 else "unknown"
        major_version = int(version_number.split(
            '.')[0]) if '.' in version_number else 0

        return {
            "full_version": version_string,
            "version_number": version_number,
            "major_version": major_version
        }
    except Exception as e:
        logger.error(f"解析版本失败: {e}")
        return {
            "full_version": "unknown",
            "version_number": "unknown",
            "major_version": 0
        }


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
        if hasattr(obj, 'isoformat'):
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
