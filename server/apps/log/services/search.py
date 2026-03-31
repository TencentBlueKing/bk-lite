from django.http import StreamingHttpResponse
import time
import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import AsyncIterator

from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.utils.query_log import VictoriaMetricsAPI
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.core.logger import log_logger as logger


class SearchService:
    @staticmethod
    def _append_filter(query, extra_filter):
        base_query = (query or "").strip()
        if not base_query or base_query == "*":
            return extra_filter
        return f"({base_query}) AND {extra_filter}"

    @staticmethod
    def _normalize_count(value):
        if value in [None, ""]:
            return 0
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            logger.warning("日志统计数量转换失败", extra={"value": value})
            return 0

    @staticmethod
    def _build_ratio(count, total):
        if total <= 0:
            return 0.0
        ratio = Decimal(count) / Decimal(total)
        return float(ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    @staticmethod
    def field_values(start_time, end_time, field, limit=100):
        """获取字段值列表"""
        # Create an instance of the VictoriaMetricsAPI
        vm_api = VictoriaMetricsAPI()

        # Perform the field values query
        response = vm_api.field_values(start_time, end_time, field, limit)

        return response

    @staticmethod
    def field_names(start_time, end_time, field, limit=100):
        """兼容旧命名，内部转发到字段值查询"""
        return SearchService.field_values(start_time, end_time, field, limit)

    @staticmethod
    def all_field_names(query, start_time, end_time, log_groups=None):
        """根据当前搜索条件获取字段名列表"""
        final_query, _ = LogGroupQueryBuilder.build_query_with_groups(query, log_groups)

        vm_api = VictoriaMetricsAPI()
        response = vm_api.all_field_names(final_query, start_time, end_time)

        values = response.get("values", []) if isinstance(response, dict) else []
        field_names = []
        for item in values:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if isinstance(value, str) and value:
                field_names.append(value)

        return sorted(set(field_names))

    @staticmethod
    def search_logs(query, start_time, end_time, limit=10, log_groups=None):
        """搜索日志，支持日志分组过滤

        Args:
            query: 用户查询语句
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回结果限制
            log_groups: 日志分组ID列表
        """
        # 处理日志分组规则
        final_query, group_info = LogGroupQueryBuilder.build_query_with_groups(query, log_groups)

        # Create an instance of the VictoriaMetricsAPI
        vm_api = VictoriaMetricsAPI()

        # Perform the query
        response = vm_api.query(final_query, start_time, end_time, limit)

        # 添加分组信息到响应中（用于调试）
        if isinstance(response, dict) and group_info:
            return {**response, "_log_group_info": group_info}

        return response

    @staticmethod
    def search_hits(query, start_time, end_time, field, fields_limit=5, step="5m", log_groups=None):
        """搜索命中统计，支持日志分组过滤"""
        # 处理日志分组规则
        final_query, group_info = LogGroupQueryBuilder.build_query_with_groups(query, log_groups)

        # Create an instance of the VictoriaMetricsAPI
        vm_api = VictoriaMetricsAPI()

        # Perform the hits query
        response = vm_api.hits(final_query, start_time, end_time, field, fields_limit, step)

        # 添加分组信息到响应中（用于调试）
        if isinstance(response, dict) and group_info:
            return {**response, "_log_group_info": group_info}

        return response

    @staticmethod
    def top_stats(query, start_time, end_time, attr, top_num=5, log_groups=None):
        """按字段返回 TopN 统计结果，支持日志分组过滤。"""
        value_filter_query = SearchService._append_filter(query, f"{attr}:*")
        final_filter_query, group_info = LogGroupQueryBuilder.build_query_with_groups(value_filter_query, log_groups)

        vm_api = VictoriaMetricsAPI()

        total_query = f"{final_filter_query} | stats count() as total_count"
        total_response = vm_api.query(total_query, start_time, end_time, 1)
        total = 0
        if total_response:
            total = SearchService._normalize_count(total_response[0].get("total_count"))

        top_query = f"{final_filter_query} | stats by ({attr}) count() as entry_count | sort by (entry_count) desc | limit {top_num}"
        top_response = vm_api.query(top_query, start_time, end_time, top_num)

        items = []
        for row in top_response:
            count = SearchService._normalize_count(row.get("entry_count"))
            items.append(
                {
                    "value": row.get(attr, ""),
                    "count": count,
                    "ratio": SearchService._build_ratio(count, total),
                }
            )

        response = {
            "attr": attr,
            "top_num": top_num,
            "total": total,
            "items": items,
        }
        if group_info:
            response["_log_group_info"] = group_info
        return response

    @staticmethod
    def tail(query, log_groups=None):
        """实时日志流，支持日志分组过滤 - ASGI兼容版本"""
        # 处理日志分组规则
        final_query, group_info = LogGroupQueryBuilder.build_query_with_groups(query, log_groups)

        async def async_event_stream() -> AsyncIterator[str]:
            """异步事件流生成器，与ASGI兼容"""
            api = VictoriaMetricsAPI()
            connection_start_time = time.time()
            max_connection_time = VictoriaLogsConstants.MAX_CONNECTION_TIME
            data_count = 0

            try:
                last_activity_time = time.time()
                keepalive_interval = VictoriaLogsConstants.KEEPALIVE_INTERVAL
                heartbeat_interval = 3.0

                logger.info(
                    "开始异步SSE tail连接",
                    extra={
                        "query": final_query[:100] + "..." if len(final_query) > 100 else final_query,
                        "log_groups": log_groups,
                    },
                )

                # 使用异步版本的tail方法
                async for line in api.tail_async(final_query):
                    current_time = time.time()

                    # 检查连接时间限制
                    if current_time - connection_start_time > max_connection_time:
                        logger.info(
                            "SSE连接达到最大时间限制",
                            extra={
                                "duration": current_time - connection_start_time,
                                "data_sent": data_count,
                            },
                        )
                        break

                    # 检查是否需要发送心跳或keepalive
                    time_since_activity = current_time - last_activity_time

                    if time_since_activity > heartbeat_interval:
                        # 发送心跳检测（3秒间隔）
                        try:
                            yield ": heartbeat\n\n"
                            last_activity_time = current_time
                        except Exception as e:
                            logger.info(
                                "检测到客户端断开(心跳)",
                                extra={
                                    "duration": current_time - connection_start_time,
                                    "data_sent": data_count,
                                    "error": str(e),
                                },
                            )
                            break

                    elif time_since_activity > keepalive_interval:
                        # 发送keepalive（45秒间隔）
                        try:
                            yield ": keepalive\n\n"
                            last_activity_time = current_time
                        except Exception as e:
                            logger.info(
                                "检测到客户端断开(保活)",
                                extra={
                                    "duration": current_time - connection_start_time,
                                    "data_sent": data_count,
                                    "error": str(e),
                                },
                            )
                            break

                    # 发送实际数据
                    try:
                        yield f"data: {line}\n\n"
                        data_count += 1
                        last_activity_time = current_time
                        await asyncio.sleep(0)
                    except Exception as e:
                        logger.info(
                            "检测到客户端断开(数据)",
                            extra={
                                "duration": current_time - connection_start_time,
                                "data_sent": data_count,
                                "error": str(e),
                            },
                        )
                        break

            except Exception as e:
                connection_duration = time.time() - connection_start_time
                logger.error(
                    "异步SSE tail连接异常",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "duration": connection_duration,
                        "data_sent": data_count,
                    },
                )
            finally:
                connection_duration = time.time() - connection_start_time
                logger.info(
                    "异步SSE tail连接结束",
                    extra={"duration": connection_duration, "data_sent": data_count},
                )

        response = StreamingHttpResponse(async_event_stream(), content_type="text/event-stream")
        # ASGI兼容的响应头设置
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["X-Accel-Buffering"] = "no"

        return response
