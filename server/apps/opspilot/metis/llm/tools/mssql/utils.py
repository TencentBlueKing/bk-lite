"""MSSQL通用工具函数"""

import json
import re
from numbers import Number

import pyodbc
from langchain_core.runnables import RunnableConfig
from loguru import logger

from apps.opspilot.metis.llm.tools.common.sql_guard import run_blocking

# 合法的数据库标识符:字母、数字、下划线,长度受限,防止 SQL 注入(如 ']' 逃逸 [] 引用)
_VALID_DATABASE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,128}$")


def quote_database_identifier(database: str) -> str:
    """
    校验并安全引用数据库标识符,用于 ``USE [<database>]`` 语句。

    数据库名通常来自 LLM,直接插值存在注入风险(如 ``]`` 可逃逸方括号引用)。
    此处对标识符做严格白名单校验,非法时抛出异常而非执行。

    Args:
        database: 数据库名

    Returns:
        str: 已用方括号安全包裹的标识符,如 ``[mydb]``

    Raises:
        ValueError: 数据库名为空或包含非法字符
    """
    if not database or not _VALID_DATABASE_IDENTIFIER.match(database):
        raise ValueError(f"非法的数据库名: {database!r}。仅允许字母、数字和下划线,且长度为1-128。")
    return f"[{database}]"

UNIT_FIELD_FORMATTERS = {
    "size_bytes": lambda value: format_size(value),
    "total_size_bytes": lambda value: format_size(value),
    "used_size_bytes": lambda value: format_size(value),
    "total_time_ms": lambda value: format_duration(value),
    "avg_time_ms": lambda value: format_duration(value),
    "max_time_ms": lambda value: format_duration(value),
    "total_cpu_time_ms": lambda value: format_duration(value),
    "threshold_ms": lambda value: format_duration(value),
    "wait_time_ms": lambda value: format_duration(value),
    "duration_ms": lambda value: format_duration(value),
    "usage_percent": lambda value: f"{float(value):.2f}%",
    "size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "used_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "free_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "log_send_queue_kb": lambda value: format_size(float(value) * 1024),
    "redo_queue_kb": lambda value: format_size(float(value) * 1024),
    "data_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "log_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "total_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "total_space_kb": lambda value: format_size(float(value) * 1024),
    "used_space_kb": lambda value: format_size(float(value) * 1024),
    "unused_space_kb": lambda value: format_size(float(value) * 1024),
    "wait_time_s": lambda value: format_duration(float(value) * 1000),
    "max_wait_time_ms": lambda value: format_duration(value),
    "signal_wait_time_s": lambda value: format_duration(float(value) * 1000),
    "signal_wait_percent": lambda value: f"{float(value):.2f}%",
    "locked_pages_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "memory_used_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "virtual_memory_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "committed_memory_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "memory_utilization_percentage": lambda value: f"{float(value):.2f}%",
    "sql_cpu_percent": lambda value: f"{float(value):.2f}%",
    "system_idle_percent": lambda value: f"{float(value):.2f}%",
    "other_process_cpu_percent": lambda value: f"{float(value):.2f}%",
    "mb_read": lambda value: format_size(float(value) * 1024 * 1024),
    "mb_written": lambda value: format_size(float(value) * 1024 * 1024),
    "io_stall_read_ms": lambda value: format_duration(value),
    "avg_read_latency_ms": lambda value: format_duration(value),
    "io_stall_write_ms": lambda value: format_duration(value),
    "avg_write_latency_ms": lambda value: format_duration(value),
    "total_io_stall_ms": lambda value: format_duration(value),
    "size_on_disk_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "duration_seconds": lambda value: format_duration(float(value) * 1000),
    "backup_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "compressed_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "hours_since_full_backup": lambda value: format_duration(float(value) * 60 * 60 * 1000),
    "hours_since_log_backup": lambda value: format_duration(float(value) * 60 * 60 * 1000),
    "max_latency_seconds": lambda value: format_duration(float(value) * 1000),
    "first_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "last_size_mb": lambda value: format_size(float(value) * 1024 * 1024),
    "growth_mb": lambda value: format_size(abs(float(value)) * 1024 * 1024),
    "daily_growth_mb": lambda value: format_size(abs(float(value)) * 1024 * 1024),
    "growth_percent": lambda value: f"{float(value):.2f}%",
}

LEGACY_FORMATTED_FIELD_ALIASES = {
    "total_time_ms": ["total_time_formatted"],
    "avg_time_ms": ["avg_time_formatted"],
    "max_time_ms": ["max_time_formatted"],
    "wait_time_ms": ["wait_time_formatted"],
    "duration_ms": ["duration_formatted"],
    "size_mb": ["size_formatted"],
    "log_send_queue_kb": ["log_send_queue_formatted"],
    "redo_queue_kb": ["redo_queue_formatted"],
    "data_size_mb": ["data_size_formatted"],
    "log_size_mb": ["log_size_formatted"],
    "total_space_kb": ["total_space_formatted"],
    "used_space_kb": ["used_space_formatted"],
    "wait_time_s": ["wait_time_formatted"],
    "max_wait_time_ms": ["max_wait_time_formatted"],
    "memory_used_mb": ["memory_used_formatted"],
    "virtual_memory_mb": ["virtual_memory_formatted"],
    "mb_read": ["mb_read_formatted"],
    "mb_written": ["mb_written_formatted"],
    "size_on_disk_mb": ["size_on_disk_formatted"],
    "avg_read_latency_ms": ["avg_read_latency_formatted"],
    "avg_write_latency_ms": ["avg_write_latency_formatted"],
    "duration_seconds": ["duration_formatted"],
    "backup_size_mb": ["backup_size_formatted"],
    "compressed_size_mb": ["compressed_size_formatted"],
    "max_latency_seconds": ["max_latency_formatted"],
    "last_size_mb": ["size_formatted"],
    "growth_mb": ["growth_formatted"],
}


def prepare_context(config: RunnableConfig = None) -> dict:
    """
    准备MSSQL连接上下文

    从config中提取数据库连接参数,支持多实例和旧式单实例配置

    Args:
        config: RunnableConfig对象,包含配置参数

    Returns:
        dict: 数据库连接配置
    """
    if config is None:
        config = {}

    configurable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})

    from apps.opspilot.metis.llm.tools.mssql.connection import (
        build_mssql_config_from_instance,
        get_mssql_instances_from_configurable,
        resolve_mssql_instance,
    )

    instances, default_instance_id = get_mssql_instances_from_configurable(configurable)
    if instances:
        instance = resolve_mssql_instance(instances, default_instance_id)
        return build_mssql_config_from_instance(instance)

    return {
        "host": configurable.get("host", "localhost"),
        "port": configurable.get("port", 1433),
        "database": configurable.get("database", "master"),
        "user": configurable.get("user", "sa"),
        "password": configurable.get("password", ""),
    }


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
    raise RuntimeError("未找到可用的SQL Server ODBC驱动。请安装以下驱动之一: ODBC Driver 18 for SQL Server, ODBC Driver 17 for SQL Server, 或 SQL Server")


def get_db_connection(config: RunnableConfig = None, database: str = None, instance_name: str = None, instance_id: str = None):
    """
    获取数据库连接

    Args:
        config: RunnableConfig对象
        database: 可选的数据库名,如果提供则覆盖config中的database
        instance_name: 可选的实例名称,用于多实例场景
        instance_id: 可选的实例ID,用于多实例场景

    Returns:
        pyodbc.Connection: 数据库连接对象
    """
    if instance_name or instance_id:
        from apps.opspilot.metis.llm.tools.mssql.connection import get_mssql_connection
        conn = get_mssql_connection(config, instance_name=instance_name, instance_id=instance_id)
        if database:
            conn.execute(f"USE {quote_database_identifier(database)}")
        return conn

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
            f"PWD={db_config['password']};"
            # 连接层声明只读意图,作为只读事务强制的一部分 (F066)
            f"ApplicationIntent=ReadOnly"
        )

        # 对于Driver 18,可能需要额外的TrustServerCertificate设置
        if "18" in driver:
            conn_str += ";TrustServerCertificate=yes"

        conn = pyodbc.connect(conn_str, timeout=10)
        return conn
    except pyodbc.Error:
        # 不记录连接参数/异常详情,避免泄露 host/账号/口令信息 (F077)
        logger.exception("MSSQL数据库连接失败")
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
    def _run():
        conn = None
        cursor = None

        try:
            conn = get_db_connection(config, database=database)

            # 只读事务强制 (F066):与 PostgreSQL 的 ``SET TRANSACTION READ ONLY`` 对齐。
            # T-SQL 无直接的 "READ ONLY 事务" 语法,这里采用两层措施:
            #   1) 连接层声明读取意图 ``ApplicationIntent=ReadOnly`` (见 get_db_connection)
            #   2) 关闭 autocommit,显式开启事务,查询后仅 rollback (绝不 commit),
            #      确保即便误含写操作也不会被持久化。
            # 真正的写入拦截仍应由数据库侧只读账号保证 (见 sql_guard 模块说明)。
            try:
                conn.autocommit = False
            except pyodbc.Error:
                logger.warning("MSSQL关闭autocommit失败,继续依赖只读账号防护")
            cursor = conn.cursor()

            # 执行查询
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # 获取列名
            columns = [column[0] for column in cursor.description]

            # 获取结果并转换为字典列表
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

        except pyodbc.Error:
            # 不记录原始错误详情(可能含连接信息);由上层统一脱敏处理
            logger.exception("MSSQL查询执行失败")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                # 只读语义:回滚而非提交,确保只读事务中不持久化任何变更
                try:
                    conn.rollback()
                except pyodbc.Error:
                    pass
                conn.close()

    # 阻塞 IO 在异步上下文中卸载到线程,避免阻塞事件循环 (F038)
    return run_blocking(_run)


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


def _is_numeric_value(value) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _format_unit_display(key: str, value) -> str | None:
    formatter = UNIT_FIELD_FORMATTERS.get(key.lower())
    if formatter is None:
        return None
    return formatter(value)


def enrich_unit_fields(data):
    """递归为带单位语义的数字字段补充人类可读展示值。"""
    if isinstance(data, list):
        return [enrich_unit_fields(item) for item in data]

    if isinstance(data, dict):
        enriched = {}
        for key, value in data.items():
            enriched_value = enrich_unit_fields(value)
            enriched[key] = enriched_value

            if key.endswith("_formatted"):
                alias_key = f"{key[:-10]}_display"
                if alias_key not in data:
                    enriched[alias_key] = enriched_value
                continue

            if key.endswith(("_formatted", "_display")) or not _is_numeric_value(value):
                continue

            display_value = _format_unit_display(key, value)
            if display_value is None:
                continue

            display_key = f"{key}_display"
            if display_key not in data:
                enriched[display_key] = display_value

            for alias_key in LEGACY_FORMATTED_FIELD_ALIASES.get(key.lower(), []):
                if alias_key not in data:
                    enriched[alias_key] = display_value

        return enriched

    return data


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

    return json.dumps(enrich_unit_fields(data), default=default_handler, ensure_ascii=False, indent=2)


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
