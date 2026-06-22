"""
共享的 SQL 安全护栏与敏感字段策略 (postgres / mssql / mysql / oracle 公用)。

====================================================================
重要安全说明 (READ ME — DEFENSE IN DEPTH, NOT A SANDBOX)
====================================================================
本模块提供的校验是 **纵深防御 (defense-in-depth)** 的一层,而不是唯一防线。

1. 关键字黑名单 (``validate_sql_safety``) 本质上是可被绕过的 —— 任何基于
   字符串/正则的黑名单都无法穷尽所有写操作或注入变体。它的作用是“尽早拦截
   明显危险的语句”,降低 LLM 误生成写操作的概率。

2. 在黑名单之上,我们叠加一层**白名单/解析式**校验 (``_assert_single_readonly_statement``):
   要求语句解析为单条只读语句 (SELECT / WITH / EXPLAIN),拒绝多语句、堆叠查询
   (stacked queries)、以及把注释当作绕过手段的写法。

3. **真正的防护必须由数据库侧的最小权限只读账号 (least-privilege read-only DB role)
   提供** —— 即:连接所用的 DB 用户在数据库层面就不具备任何写/DDL/执行存储过程的
   权限。这是基础设施/运维层面的要求,代码本身无法替代。任何部署本工具的环境都
   应当为这些工具配置只读数据库账号。

调用方在执行查询时还应开启只读事务 (如 ``SET TRANSACTION READ ONLY``),作为
运行时的额外保险。
"""

import asyncio
import concurrent.futures
import re

from loguru import logger

# --------------------------------------------------------------------------- #
# 敏感字段策略 (统一来源)
# --------------------------------------------------------------------------- #
# 结果集列名过滤用 —— 命中即整列剔除 (精确小写匹配)
SENSITIVE_COLUMNS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "key",
        "api_key",
        "apikey",
        "access_key",
        "access_token",
        "refresh_token",
        "private_key",
        "session_key",
        "encryption_key",
        "auth_token",
        "credential",
        "auth",
        "hash",
        "salt",
        "otp",
        "bearer",
        "jwt",
        "certificate",
        "cert",
        "passphrase",
        "pin",
        "cvv",
        "ssn",
        "credit_card",
        "bank_account",
        "routing_number",
    }
)

# 列名子串匹配用 (get_sample_data 等场景,任意子串命中即视为敏感)
SENSITIVE_KEYWORDS = SENSITIVE_COLUMNS

# SELECT 子句敏感关键字检测用 (在 select...from 之间出现即拦截)
SELECT_CLAUSE_SENSITIVE_KEYWORDS = ("password", "secret", "token", "key", "hash", "otp", "credential")

# --------------------------------------------------------------------------- #
# 各方言禁止关键字 (写操作 / DDL / 危险扩展)
# --------------------------------------------------------------------------- #
# 跨方言通用的写/DDL 关键字
_COMMON_FORBIDDEN = (
    "insert",
    "update",
    "delete",
    "drop",
    "create",
    "alter",
    "truncate",
    "grant",
    "revoke",
    "rename",
    "replace",
    "merge",
    "call",
    "execute",
    "kill",
    "lock",
)

_DIALECT_FORBIDDEN = {
    "postgres": (
        "copy",
        "set",
        "reset",
        "vacuum",
        "analyze",
        "cluster",
        "reindex",
        "pg_terminate_backend",
        "pg_cancel_backend",
    ),
    "mssql": (
        "exec",
        "sp_",
        "xp_",
        "bulk",
        "backup",
        "restore",
        "dbcc",
        "shutdown",
        "reconfigure",
        "deny",
        "openquery",
        "openrowset",
        "opendatasource",
    ),
    "mysql": (
        "load",
        "handler",
        "flush",
        "purge",
        "reset",
        "change",
        "install",
        "uninstall",
        "prepare",
        "deallocate",
        "unlock",
    ),
    "oracle": (
        "purge",
        "flashback",
        "shutdown",
        "startup",
        "dbms_",
        "utl_",
    ),
}


def get_forbidden_keywords(dialect: str) -> tuple:
    """返回某方言的完整禁止关键字列表 (通用 + 方言特有)。"""
    return _COMMON_FORBIDDEN + _DIALECT_FORBIDDEN.get(dialect, ())


def _strip_sql_comments(sql: str) -> str:
    """移除 -- 行注释和 /* */ 块注释,避免被当作绕过手段。"""
    # 块注释
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # 行注释
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def _assert_single_readonly_statement(sql: str) -> tuple[bool, str]:
    """
    白名单式纵深防御:要求语句解析为单条只读语句。

    - 必须以 SELECT / WITH / EXPLAIN 开头 (去除注释后)
    - 拒绝堆叠/多条语句 (分号分隔的多语句)
    - 拒绝把注释当作绕过手段 (注释已在黑名单阶段单独拦截,这里再防御一次)
    """
    stripped = _strip_sql_comments(sql).strip()
    if not stripped:
        return False, "SQL为空或仅包含注释"

    lowered = stripped.lower()
    if not (lowered.startswith("select") or lowered.startswith("with") or lowered.startswith("explain")):
        return False, "仅允许只读语句 (SELECT / WITH / EXPLAIN)"

    # 多语句 / 堆叠查询:去除结尾分号后若仍含分号则拒绝
    body = stripped.rstrip().rstrip(";")
    if ";" in body:
        return False, "禁止执行多条SQL语句 (堆叠查询)"

    return True, ""


def validate_sql_safety(sql: str, dialect: str) -> tuple[bool, str]:
    """
    验证SQL语句的安全性 (黑名单 + 白名单纵深防御)。

    Args:
        sql: 待验证的SQL语句
        dialect: 方言标识 (postgres / mssql / mysql / oracle)

    Returns:
        tuple: (是否安全, 错误信息)

    注意:这是纵深防御的一层,真正的隔离必须依赖数据库侧只读账号 (见模块 docstring)。
    """
    sql_lower = sql.lower().strip()

    # --- 黑名单层:禁止写/DDL/危险关键字 ---
    for keyword in get_forbidden_keywords(dialect):
        # 使用单词边界检查,避免误判(如 inserted_at 字段名)。
        # 注意前缀类关键字 (sp_/xp_/dbms_/utl_) 以下划线结尾,\b 仍能正确匹配其前边界。
        pattern = r"\b" + re.escape(keyword)
        if keyword.endswith("_"):
            # 前缀关键字:匹配 sp_xxx 这类
            if re.search(pattern, sql_lower):
                return False, f"SQL包含禁止的关键字: {keyword}"
        else:
            if re.search(pattern + r"\b", sql_lower):
                return False, f"SQL包含禁止的关键字: {keyword}"

    # --- 黑名单层:必须以SELECT或WITH开头 ---
    if not sql_lower.startswith("select") and not sql_lower.startswith("with"):
        return False, "SQL必须以SELECT或WITH开头"

    # --- 黑名单层:禁止分号分隔的多条语句 ---
    if sql.count(";") > 1 or (sql.count(";") == 1 and not sql.strip().endswith(";")):
        return False, "禁止执行多条SQL语句"

    # --- 黑名单层:禁止注释注入 (注释可被用于绕过关键字检测) ---
    if "--" in sql or "/*" in sql:
        return False, "SQL不允许包含注释符号"

    # --- 白名单层 (纵深防御):必须解析为单条只读语句 ---
    ok, msg = _assert_single_readonly_statement(sql)
    if not ok:
        return False, msg

    return True, ""


# --------------------------------------------------------------------------- #
# 敏感字段检测 / 过滤
# --------------------------------------------------------------------------- #
def detect_select_star(sql: str) -> bool:
    """检测 SELECT * FROM 形式 (规范化空白后)。"""
    sql_normalized = " ".join(sql.lower().split())
    return bool(re.search(r"\bselect\s+\*\s+from\b", sql_normalized))


def detect_sensitive_in_select(sql: str) -> str | None:
    """
    检测 SELECT 子句中是否出现敏感关键字,命中则返回该关键字,否则返回 None。
    """
    sql_normalized = " ".join(sql.lower().split())
    for keyword in SELECT_CLAUSE_SENSITIVE_KEYWORDS:
        if re.search(rf"\bselect\b.*\b{keyword}\b.*\bfrom\b", sql_normalized):
            return keyword
    return None


def is_sensitive_column(name: str) -> bool:
    """列名是否命中敏感关键字 (子串匹配,大小写不敏感)。"""
    lowered = name.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def filter_sensitive_columns(rows: list) -> list:
    """从结果集 (dict 列表) 中剔除敏感列 (精确列名匹配)。"""
    if not rows:
        return rows
    keys_to_remove = [k for k in rows[0] if k.lower() in SENSITIVE_COLUMNS]
    if not keys_to_remove:
        return rows
    return [{k: v for k, v in row.items() if k not in keys_to_remove} for row in rows]


# --------------------------------------------------------------------------- #
# 错误脱敏 (F046 / F077)
# --------------------------------------------------------------------------- #
def sanitize_db_error(exc: Exception, context: str = "SQL查询") -> str:
    """
    服务端记录完整异常 (含堆栈),对外仅返回脱敏后的通用错误信息。

    原始 DB 错误常包含主机名、连接参数、DSN、SQLSTATE 等敏感信息,不应回传给
    LLM/上层。此处统一:服务端 ``logger.exception`` 记录全量,返回值不含任何
    连接细节。

    Args:
        exc: 捕获到的异常
        context: 业务上下文描述,用于日志归类

    Returns:
        str: 脱敏后的通用错误信息
    """
    logger.exception(f"{context}失败 (详情见服务端日志)")
    return f"{context}失败,请检查SQL语句或联系管理员。"


# --------------------------------------------------------------------------- #
# 阻塞调用卸载 (F038)
# --------------------------------------------------------------------------- #
def run_blocking(func, *args, **kwargs):
    """
    执行阻塞型 (同步) DB 调用,在异步上下文中自动卸载到线程,避免阻塞事件循环。

    这些 @tool 函数本身是同步的,但会被 LangGraph 的异步 ToolNode 调度执行,
    其中的 connect/query/close 是阻塞 IO。若当前线程已有运行中的事件循环,则通过
    ``asyncio.run_coroutine_threadsafe(asyncio.to_thread(...))`` 之外更简单的方式:
    检测到事件循环时改用线程池执行;否则直接同步执行 —— 这样既不改变同步调用方
    的行为,又能在异步图中让出事件循环。

    Returns:
        func(*args, **kwargs) 的返回值
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环:同步执行 (普通同步调用方,行为不变)
        return func(*args, **kwargs)

    # 处于异步事件循环线程中:在独立线程执行阻塞调用,并阻塞等待其结果。

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(func, *args, **kwargs).result()
