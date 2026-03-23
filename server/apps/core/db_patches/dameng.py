"""
达梦数据库（DamengDB）兼容性补丁集合。

补丁分为两类：
1. 早期补丁 (apply_early_patches): 必须在 Django 开始使用缓存前应用
   - 在 config/components/database.py 中调用
   - 包括 DatabaseCache 写入禁用、CursorWrapper 错误日志抑制
   - **重要**: 包括 cursor.execute 串行化锁，解决 ASGI 并发死锁问题
2. 常规补丁 (patch): 在 CoreConfig.ready() 中应用
   - 包括 JSONField 反序列化、bulk_create/bulk_update 兼容性、JSON 查询兼容性
3. ASGI 补丁: 直接在 asgi.py 中应用
   - 修复 ASGI 模式下 sync_to_async(thread_sensitive=True) 导致的线程阻塞问题
   - 必须在 Django application 初始化之前应用

并发死锁问题分析：
- 达梦驱动 (dmPython) 在多线程并发访问时可能产生死锁
- Django ASGI 模式下，每个请求的 ORM 操作被 sync_to_async 包装后在线程池执行
- 当多个线程同时执行 cursor.execute 时，驱动内部的锁可能导致相互等待
- 解决方案：使用全局锁串行化所有 cursor.execute 操作
"""

import json
import logging
import threading
import time

from django.db import IntegrityError
from django.db.models import QuerySet
from django.db.models.fields.json import JSONField

logger = logging.getLogger(__name__)

# 标记早期补丁是否已应用，避免重复
_early_patches_applied = False

# ============================================================
# 达梦数据库全局锁 - 解决 ASGI 并发死锁问题
# ============================================================
# 由于达梦驱动可能不是完全线程安全的，使用全局锁确保
# 同一时间只有一个线程在执行数据库操作
_dameng_global_lock = threading.RLock()

# 锁等待超时时间（秒），超过此时间记录警告
_LOCK_WAIT_WARNING_THRESHOLD = 5.0


def _sanitize_unicode_for_gbk(value):
    """
    将字符串中无法用 GBK 编码的 Unicode 字符转换为可兼容的形式。

    达梦数据库驱动可能使用 GBK 编码，某些 Unicode 字符（如 ⚠ U+26A0）
    无法用 GBK 编码，会导致 UnicodeEncodeError。

    处理策略：
    - 尝试用 GBK 编码字符串
    - 如果失败，将无法编码的字符替换为 '?' 或 Unicode 转义序列
    - 使用 'replace' 错误处理，将无法编码的字符替换为 '?'

    Args:
        value: 要处理的值（可以是字符串、列表、元组或其他类型）

    Returns:
        处理后的值，字符串中的不兼容字符被替换
    """
    if value is None:
        return value

    if isinstance(value, str):
        try:
            # 尝试用 GBK 编码，如果成功说明没有问题
            value.encode("gbk")
            return value
        except UnicodeEncodeError:
            # 有无法编码的字符，使用 replace 策略
            # 将无法用 GBK 编码的字符替换为 '?'
            return value.encode("gbk", errors="replace").decode("gbk")

    if isinstance(value, (list, tuple)):
        # 递归处理列表或元组中的每个元素
        sanitized = [_sanitize_unicode_for_gbk(item) for item in value]
        return type(value)(sanitized)

    # 其他类型直接返回
    return value


def apply_early_patches():
    """
    应用必须在 Django 启动早期执行的补丁。

    这些补丁需要在 Django 开始使用缓存之前应用，
    因此在 config/components/database.py 中调用。

    重要补丁：
    1. _patch_cursor_execute_with_lock: 串行化 cursor.execute，解决 ASGI 并发死锁
    2. _patch_database_cache_set: 禁用 DatabaseCache 写入
    3. _patch_cursor_wrapper_suppress_cache_error: 抑制缓存错误日志
    """
    global _early_patches_applied
    if _early_patches_applied:
        return
    _early_patches_applied = True

    # 1. 最重要的补丁：串行化 cursor.execute，解决 ASGI 并发死锁
    _patch_cursor_execute_with_lock()

    # 2. 禁用 DatabaseCache 写入
    _patch_database_cache_set()

    # 3. 抑制缓存错误日志
    _patch_cursor_wrapper_suppress_cache_error()

    logger.info("DamengDB early patches applied (cursor lock, DatabaseCache, CursorWrapper)")


def _patch_cursor_execute_with_lock():
    """
    串行化达梦数据库的 cursor.execute 操作，解决 ASGI 并发死锁问题。

    问题分析：
    1. 达梦驱动 (dmPython) 在多线程并发执行 SQL 时可能产生死锁
    2. Django ASGI 模式下，ORM 操作被 sync_to_async 包装，在线程池中执行
    3. 当多个线程同时调用 cursor.execute 时，驱动内部可能相互等待
    4. 表现为：第一个请求正常，后续请求全部卡死

    解决方案：
    使用全局 RLock 包装所有 cursor.execute 调用，确保同一时间只有一个线程
    在执行数据库操作。虽然会降低并发性能，但能保证系统稳定运行。

    性能影响：
    - 所有数据库操作变为串行执行
    - 单个请求的性能不受影响
    - 并发请求需要排队等待
    - 对于 IO 密集型应用（如 API 服务），影响相对较小
    """
    try:
        import dmPython
        from cw_cornerstone.db.dameng.backend.wrapper import CursorWrapper
    except ImportError:
        logger.warning("[DAMENG_LOCK] cw_cornerstone dameng wrapper not found, cursor lock patch skipped")
        return

    # 保存原始的父类 execute 方法引用
    from dmDjango.base import CursorWrapper as BaseCursorWrapper

    base_execute = BaseCursorWrapper.execute

    # 保存原始的 replace_sql_params 静态方法
    replace_sql_params = CursorWrapper.replace_sql_params

    def locked_execute(self, sql, params=None):
        """
        带全局锁的 execute 方法。

        确保同一时间只有一个线程在执行数据库操作，
        避免达梦驱动的并发死锁问题。

        额外处理：
        - 对参数进行 Unicode 字符净化，避免 GBK 编码错误
        """
        start_time = time.time()
        lock_acquired = False
        current_thread = threading.current_thread()
        sql_preview = (sql[:80] + "...") if sql and len(sql) > 80 else sql

        # 预处理参数：将无法用 GBK 编码的 Unicode 字符进行替换
        # 这解决了达梦驱动使用 GBK 编码时的 UnicodeEncodeError 问题
        sanitized_params = _sanitize_unicode_for_gbk(params) if params else params

        logger.debug(f"[DAMENG_LOCK] Thread={current_thread.name}({current_thread.ident}) WAITING for lock, sql={sql_preview}")

        try:
            lock_acquired = _dameng_global_lock.acquire(blocking=True, timeout=60.0)

            if not lock_acquired:
                logger.error(f"[DAMENG_LOCK] Thread={current_thread.name}({current_thread.ident}) TIMEOUT after 60s, sql={sql_preview}")
                raise TimeoutError("Failed to acquire database lock within 60 seconds")

            wait_time = time.time() - start_time
            logger.debug(
                f"[DAMENG_LOCK] Thread={current_thread.name}({current_thread.ident}) ACQUIRED lock after {wait_time:.3f}s, sql={sql_preview}"
            )
            if wait_time > _LOCK_WAIT_WARNING_THRESHOLD:
                logger.warning(f"[DAMENG_LOCK] Lock wait time {wait_time:.2f}s exceeded threshold")

            try:
                exec_start = time.time()
                result = base_execute(self, sql, sanitized_params)
                exec_time = time.time() - exec_start
                logger.debug(f"[DAMENG_LOCK] Thread={current_thread.name}({current_thread.ident}) EXECUTED in {exec_time:.3f}s, sql={sql_preview}")
                return result

            except dmPython.DatabaseError as e:
                error_code = getattr(e.args[0], "code", None) if e.args else None

                # 处理 -70005 错误（text 字段过长问题，保留原逻辑）
                if sanitized_params and error_code == -70005:
                    new_sql = replace_sql_params(sql)
                    whole_sql = new_sql % tuple(sanitized_params)
                    try:
                        return base_execute(self, whole_sql)
                    except dmPython.DatabaseError as e2:
                        logger.error("dameng execution whole_sql %s error: %s", sql, e2)
                        raise

                # 检查是否是 DJANGO_CACHE 表的唯一约束冲突
                is_cache_table = sql and "DJANGO_CACHE" in sql.upper()
                is_unique_violation = error_code == -6602

                if not (is_cache_table and is_unique_violation):
                    logger.error("dameng execution sql %s error: %s", sql, e)
                raise

        finally:
            if lock_acquired:
                _dameng_global_lock.release()
                logger.debug(f"[DAMENG_LOCK] Thread={current_thread.name}({current_thread.ident}) RELEASED lock, sql={sql_preview}")

    CursorWrapper.execute = locked_execute
    logger.info("[DAMENG_LOCK] cursor.execute patched with global lock for ASGI concurrency safety")


def patch():
    """
    应用常规的达梦数据库补丁。

    这些补丁在 CoreConfig.ready() 中调用，
    用于修复 ORM 层面的兼容性问题。
    """
    # 确保早期补丁已应用（以防 database.py 中的调用失败）
    apply_early_patches()

    # 修复 JSONField 双重编码问题（最关键的补丁）
    _patch_adapt_json_value()  # 必须最先应用，修复 adapt_json_value 的双重编码
    _patch_jsonfield_get_prep_value()  # 确保 get_prep_value 也正确处理
    _patch_jsonfield_from_db_value()
    _patch_jsonfield_for_bulk_update()
    _patch_bulk_create_ignore_conflicts()
    _patch_jsonfield_contains_lookup()
    logger.info("DamengDB ORM patches applied (JSONField, bulk_create, JSON contains)")


def _patch_adapt_json_value():
    """
    修复 Django 默认 adapt_json_value 导致的 JSONField 双重编码问题。

    问题根源：
    Django JSONField.get_db_prep_value 的调用链是：
    1. get_db_prep_value(value, prepared=False)
    2.   -> get_prep_value(value) 返回 JSON 字符串，如 '[1]'
    3.   -> connection.ops.adapt_json_value('[1]', encoder)
    4.   -> json.dumps('[1]') 返回 '"[1]"' <- 双重编码！

    Django 的默认 adapt_json_value 实现是：
        def adapt_json_value(self, value, encoder):
            return json.dumps(value, cls=encoder)

    这个实现假设传入的 value 是原始 Python 对象，但实际上 get_prep_value
    已经返回了 JSON 字符串，导致字符串被再次序列化。

    修复策略：
    覆盖达梦 DatabaseOperations 的 adapt_json_value 方法，
    如果传入的值已经是字符串，直接返回，不再进行 json.dumps。
    """
    try:
        from cw_cornerstone.db.dameng.backend.operations import DatabaseOperations
    except ImportError:
        logger.warning("cw_cornerstone.db.dameng.backend.operations not found, adapt_json_value patch skipped")
        return

    def patched_adapt_json_value(self, value, encoder):
        """
        达梦数据库的 adapt_json_value 补丁。

        如果值已经是字符串（由 get_prep_value 序列化），直接返回。
        否则执行标准的 JSON 序列化。
        """
        if value is None:
            return value

        # 如果已经是字符串，说明 get_prep_value 已经序列化过了，直接返回
        if isinstance(value, str):
            return value

        # 对于原始 Python 对象，执行 JSON 序列化
        return json.dumps(value, cls=encoder, ensure_ascii=False)

    DatabaseOperations.adapt_json_value = patched_adapt_json_value
    logger.debug("DatabaseOperations.adapt_json_value patched to prevent double JSON encoding")


def _patch_jsonfield_get_prep_value():
    """
    修复 cw-cornerstone 达梦后端对 JSONField.get_prep_value 的双重编码问题。

    问题：
    cw-cornerstone 的 patch 会对所有非字符串值执行 json.dumps(value)，
    但 Django 的 JSONField.get_prep_value 本身已经会对值进行 JSON 序列化。
    这导致数据被双重编码：
    - Python [1] -> Django get_prep_value -> "[1]" -> cw-cornerstone json.dumps -> '"[1]"'
    - 最终数据库存储的是 "[1]" 而不是 [1]

    修复策略：
    覆盖 get_prep_value，如果值已经是字符串（说明已经被序列化过），则直接返回。
    只对 dict/list 等原生 Python 对象执行一次 json.dumps。
    """

    def patched_get_prep_value(self, value):
        if value is None:
            return value

        # 如果已经是字符串，说明可能已经被序列化过，直接返回
        # 这样可以防止 cw-cornerstone 再次 json.dumps
        if isinstance(value, str):
            return value

        # 对于 dict/list 等，执行标准的 JSON 序列化
        return json.dumps(value, cls=self.encoder, ensure_ascii=False)

    JSONField.get_prep_value = patched_get_prep_value
    logger.debug("JSONField.get_prep_value patched to prevent double JSON encoding")


def _patch_jsonfield_from_db_value():
    """
    修复达梦数据库 JSONField 读取时不自动反序列化的问题。

    问题：
    达梦数据库将 JSONField 存储为 TEXT/NCLOB 类型，读取时返回的是字符串而非 Python 对象。
    cw-cornerstone 只 patch 了 get_prep_value（写入时序列化），
    但没有 patch from_db_value（读取时反序列化）。

    额外问题：
    由于历史数据可能被双重 JSON 编码（json.dumps 执行了两次），
    导致数据库中存储的是类似 '"[...]"' 的字符串，
    第一次 json.loads 后得到的仍然是字符串而非 list/dict。

    修复策略：
    patch JSONField.from_db_value，递归反序列化直到得到真正的 Python dict/list 对象，
    同时设置最大递归深度防止无限循环。
    """
    original_from_db_value = JSONField.from_db_value

    def patched_from_db_value(self, value, expression, connection):
        if value is None:
            return value

        # 如果已经是 dict 或 list，直接返回（某些情况下可能已经被反序列化）
        if isinstance(value, (dict, list)):
            return value

        # 如果是字符串，尝试 JSON 反序列化
        if isinstance(value, str):
            if value == "":
                # 空字符串返回对应的默认值（根据字段定义）
                return None

            # 递归解码，处理双重 JSON 编码的历史数据
            # 最大递归深度为 3，防止无限循环
            max_depth = 3
            current_value = value
            for _ in range(max_depth):
                try:
                    decoded = json.loads(current_value, cls=self.decoder)
                    # 如果解码后是 dict 或 list，返回结果
                    if isinstance(decoded, (dict, list)):
                        return decoded
                    # 如果解码后仍然是字符串，继续尝试解码（处理双重编码）
                    if isinstance(decoded, str):
                        current_value = decoded
                        continue
                    # 其他类型（int, float, bool, None）直接返回
                    return decoded
                except (json.JSONDecodeError, TypeError):
                    # 解析失败，返回当前值
                    return current_value

            # 超过最大递归深度，返回当前值
            return current_value

        # 其他情况调用原始方法
        return original_from_db_value(self, value, expression, connection)

    JSONField.from_db_value = patched_from_db_value
    logger.debug("JSONField.from_db_value patched for DamengDB TEXT deserialization")


def _patch_jsonfield_for_bulk_update():
    """
    修复 cw-cornerstone 达梦后端对 JSONField.get_prep_value 的 patch 缺陷。

    问题链：
    1. Django bulk_update 生成 Case(When(pk=x, then=Value([...]))) 表达式
    2. JSONField.get_db_prep_value 调用 get_prep_value(value)，此时 value 是 Case 表达式
    3. cw-cornerstone patch 后的 get_prep_value 对所有非字符串值做 json.dumps(value)
    4. json.dumps(Case(...)) → TypeError: Object of type Case is not JSON serializable

    修复策略：
    patch get_db_prep_value（cw-cornerstone 未触及此方法），
    在调用 get_prep_value 之前拦截 Expression 对象（Case/When 等有 resolve_expression
    的对象），直接返回，交由后续的 SQL 编译流程处理。
    """
    original_get_db_prep_value = JSONField.get_db_prep_value

    def patched_get_db_prep_value(self, value, connection, prepared=False):
        # 拦截 Expression 对象，避免进入 get_prep_value 被 json.dumps 序列化
        if hasattr(value, "resolve_expression"):
            return value
        return original_get_db_prep_value(self, value, connection, prepared)

    JSONField.get_db_prep_value = patched_get_db_prep_value
    logger.debug("JSONField.get_db_prep_value patched for DamengDB bulk_update compatibility")


def _patch_bulk_create_ignore_conflicts():
    """
    修复达梦数据库不支持 bulk_create(ignore_conflicts=True) 的问题。

    达梦不支持 PostgreSQL 的 ON CONFLICT DO NOTHING 语法，
    dmDjango 设置了 supports_ignore_conflicts = False，
    导致 Django 直接抛出 NotSupportedError。

    修复策略：
    monkey-patch QuerySet.bulk_create，当 ignore_conflicts=True 时，
    降级为逐条 save()，静默跳过已存在的记录（IntegrityError）。
    """
    original_bulk_create = QuerySet.bulk_create

    def patched_bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if not ignore_conflicts:
            return original_bulk_create(
                self,
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

        # 达梦降级：逐条插入，遇到唯一约束冲突则跳过
        created = []
        for obj in objs:
            try:
                obj.save(using=self.db)
                created.append(obj)
            except IntegrityError:
                logger.debug(
                    "bulk_create ignore_conflicts fallback: skipped duplicate %s(pk=%s)",
                    type(obj).__name__,
                    obj.pk,
                )
        return created

    QuerySet.bulk_create = patched_bulk_create
    logger.debug("QuerySet.bulk_create patched for DamengDB ignore_conflicts compatibility")


def _patch_jsonfield_contains_lookup():
    """
    修复达梦数据库 JSONField 的 __contains 查询问题。

    问题：
    在 PostgreSQL 中，JSONField 使用 @> 操作符进行 JSON 包含查询，
    例如 team__contains=1 会查询 JSON 数组中包含元素 1 的记录。

    在达梦中，JSONField 存储为 TEXT 类型，需要使用 LIKE 模式匹配。

    修复策略：
    注册自定义的 Lookup，将 JSON 数组包含查询转换为字符串模式匹配。
    匹配标准 JSON 格式: [1], [1, 2], [2, 1] 等

    数据库存储格式示例：
    - [1] - 单元素数组
    - [1, 2, 3] - 带空格的多元素数组（Python json.dumps 默认格式）
    - [1,2,3] - 不带空格的多元素数组（紧凑格式）
    """
    from django.db.models import Lookup
    from django.db.models.fields.json import JSONField

    class DamengJSONContains(Lookup):
        """达梦数据库的 JSON 数组包含查询 Lookup"""

        lookup_name = "contains"

        def as_sql(self, compiler, connection):
            lhs, lhs_params = self.process_lhs(compiler, connection)
            # 不调用 process_rhs，因为我们需要原始的 Python 值而非 JSON 序列化后的值
            # self.rhs 包含原始的查询值（在 get_prep_lookup 之前被保存）
            value = self.rhs

            # 如果值已经是 JSON 字符串（可能被其他地方序列化了），尝试解析
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass

            # 如果是字典或列表，使用 LIKE 匹配序列化后的字符串
            if isinstance(value, (dict, list)):
                json_str = json.dumps(value, ensure_ascii=False)
                # 转义 LIKE 特殊字符
                json_str = json_str.replace("%", r"\%").replace("_", r"\_")
                pattern = f"%{json_str}%"
                return f"{lhs} LIKE %s", lhs_params + [pattern]

            # 对于简单值（int, str 等），构建精确匹配模式
            # 匹配 JSON 数组中的元素: [1], [1, 2], [2, 1], [2, 1, 3]
            # 或字符串数组: ["llm"], ["llm", "embed"], 等
            #
            # 数据库中可能的存储格式：
            # - [1] (单元素数字)
            # - ["llm"] (单元素字符串)
            # - [1, 2] (开头，带空格)
            # - ["llm", "embed"] (字符串数组，带空格)
            # - [1,2] (开头，不带空格)
            # - [2, 1] (结尾，带空格)
            # - [2,1] (结尾，不带空格)
            # - [2, 1, 3] (中间，带空格)
            # - [2,1,3] (中间，不带空格)
            #
            # 使用 json.dumps 将值序列化为 JSON 格式，
            # 这样字符串 "llm" 会变成 '"llm"'，数字 1 还是 '1'
            json_value = json.dumps(value, ensure_ascii=False)
            # 转义 LIKE 特殊字符
            json_value_escaped = json_value.replace("%", r"\%").replace("_", r"\_")

            patterns = [
                f"[{json_value_escaped}]",  # 匹配 [1] 或 ["llm"] 单元素数组
                f"[{json_value_escaped}, %",  # 匹配 [1, ...] 或 ["llm", ...] 数组开头（带空格）
                f"[{json_value_escaped},%",  # 匹配 [1,...] 或 ["llm",...] 数组开头（不带空格）
                f"%, {json_value_escaped}, %",  # 匹配 [..., 1, ...] 中间（带空格）
                f"%,{json_value_escaped},%",  # 匹配 [...,1,...] 中间（不带空格）
                f"%, {json_value_escaped}]",  # 匹配 [..., 1] 结尾（带空格）
                f"%,{json_value_escaped}]",  # 匹配 [...,1] 结尾（不带空格）
            ]

            # 构建 OR 条件
            conditions = " OR ".join([f"{lhs} LIKE %s" for _ in patterns])
            return f"({conditions})", lhs_params * len(patterns) + patterns

    # 注册新的 lookup（覆盖默认的）
    JSONField.register_lookup(DamengJSONContains)
    logger.debug("JSONField.contains lookup patched for DamengDB")


def _patch_database_cache_set():
    """
    达梦数据库下禁用 DatabaseCache 的写入操作。

    问题：
    达梦数据库的 DatabaseCache 在并发写入时会触发唯一约束冲突（CODE:-6602），
    且异常处理后会导致数据库连接处于不可用状态，造成整个服务卡死。

    修复策略：
    在达梦数据库环境下，将 DatabaseCache 的写入操作（set/add）降级为空操作，
    仅保留读取功能。这样可以避免并发写入问题，同时缓存读取仍然可用。

    注意：
    这意味着 db 缓存在达梦环境下实际上变成了"只读缓存"。
    如果需要完整的缓存功能，建议配置 Redis 作为缓存后端。
    """
    from django.core.cache.backends.db import DatabaseCache

    def noop_base_set(self, mode, key, value, timeout=None):
        """空操作：跳过写入，直接返回成功"""
        logger.debug(
            "[DAMENG_CACHE] DatabaseCache write skipped (noop), key=%s",
            key,
        )
        return True

    DatabaseCache._base_set = noop_base_set
    logger.info("DatabaseCache writes disabled for DamengDB compatibility (reads still work)")


def _patch_cursor_wrapper_suppress_cache_error():
    """
    修复达梦 CursorWrapper 在发生错误后连接状态异常的问题。

    注意：此补丁的功能已合并到 _patch_cursor_execute_with_lock 中，
    保留此函数是为了向后兼容。

    如果 _patch_cursor_execute_with_lock 已成功应用，此函数不做任何操作。
    如果 _patch_cursor_execute_with_lock 失败（如达梦驱动未安装），
    此函数也不做任何操作，因为没有达梦驱动的环境不需要此补丁。
    """
    # 功能已合并到 _patch_cursor_execute_with_lock，此处保留为空操作
    logger.debug("CursorWrapper.execute error handling merged into _patch_cursor_execute_with_lock")
