import json
import asyncio
import requests
import requests.adapters
import time
from apps.log.constants import VICTORIALOGS_HOST, VICTORIALOGS_USER, VICTORIALOGS_PWD, VICTORIALOGS_SSL_VERIFY
from apps.core.logger import log_logger as logger


class VictoriaMetricsAPI:
    def __init__(self):
        self.host = VICTORIALOGS_HOST
        self.username = VICTORIALOGS_USER
        self.password = VICTORIALOGS_PWD
        self.ssl_verify = VICTORIALOGS_SSL_VERIFY

    def field_names(self, start, end, field, limit=100):
        data = {"query": f"{field}:*", "field":field, "start": start, "end": end, "limit": limit}
        response = requests.get(
            f"{self.host}/select/logsql/field_names",
            params=data,
            auth=(self.username, self.password),
            verify=self.ssl_verify,
        )
        response.raise_for_status()
        return response.json()

    def query(self, query, start, end, limit=10):
        data = {"query": query, "start": start, "end": end, "limit": limit}
        response = requests.post(
            f"{self.host}/select/logsql/query",
            params=data,
            auth=(self.username, self.password),
            verify=self.ssl_verify,
        )
        response.raise_for_status()
        result = []
        for line in response.text.strip().splitlines():
            if line:
                result.append(json.loads(line))
        return result

    def hits(self, query, start, end, field, fields_limit=5, step="5m"):
        data = {"query": query, "start": start, "end": end, "field": field, "fields_limit": fields_limit, "step": step}

        response = requests.post(
            f"{self.host}/select/logsql/hits",
            params=data,
            auth=(self.username, self.password),
            verify=self.ssl_verify,
        )
        response.raise_for_status()
        return response.json()

    async def tail_async(self, query):
        """异步版本的tail方法，ASGI兼容实现"""
        data = {"query": query}
        response = None

        try:
            logger.info("开始异步VictoriaLogs tail请求", extra={
                'host': self.host,
                'query': query[:200] + '...' if len(query) > 200 else query
            })

            # 在线程池中执行同步请求，避免阻塞事件循环
            loop = asyncio.get_event_loop()

            def _make_request():
                response = requests.post(
                    f"{self.host}/select/logsql/tail",
                    params=data,
                    auth=(self.username, self.password),
                    verify=self.ssl_verify,
                    stream=True,
                    timeout=(10, 120),  # 连接超时10秒，读取超时120秒
                    headers={
                        'Accept': 'application/x-ndjson, text/plain',
                        'Connection': 'keep-alive',
                        'Cache-Control': 'no-cache'
                    }
                )
                response.raise_for_status()
                response.encoding = 'utf-8'
                return response

            # 在执行器中运行同步请求
            response = await loop.run_in_executor(None, _make_request)

            logger.info("异步VictoriaLogs tail响应成功", extra={
                'status_code': response.status_code
            })

            # 异步生成器，逐行处理数据
            line_count = 0
            first_data_received = False
            start_time = time.time()

            try:
                # 逐行处理响应数据
                for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
                    if line:
                        line_count += 1

                        if not first_data_received:
                            elapsed = time.time() - start_time
                            logger.info("异步VictoriaLogs首个数据到达", extra={
                                'elapsed_time': elapsed
                            })
                            first_data_received = True

                        try:
                            # 让出控制权给其他异步任务
                            await asyncio.sleep(0)
                            yield line.strip()

                            # 每1000行记录一次状态
                            if line_count % 1000 == 0:
                                logger.debug("异步VictoriaLogs数据流状态", extra={
                                    'lines_received': line_count,
                                    'elapsed_time': time.time() - start_time
                                })

                        except Exception as line_error:
                            logger.warning("异步处理VictoriaLogs数据行失败", extra={
                                'error': str(line_error),
                                'line_preview': line[:100] if line else 'empty'
                            })
                            continue
                    else:
                        # 处理空行，让出控制权
                        await asyncio.sleep(0.001)

            finally:
                # 确保响应对象被正确关闭
                if response:
                    response.close()
                    logger.debug("VictoriaLogs响应连接已关闭")

        except requests.exceptions.ConnectTimeout:
            logger.error("异步VictoriaLogs连接超时", extra={
                'host': self.host,
                'timeout': '10秒'
            })
            raise
        except requests.exceptions.ReadTimeout:
            logger.error("异步VictoriaLogs读取超时", extra={
                'host': self.host,
                'timeout': '120秒'
            })
            raise
        except Exception as e:
            logger.error("异步VictoriaLogs tail错误", extra={
                'error': str(e),
                'error_type': type(e).__name__
            })
            raise
        finally:
            # 双重保险：确保响应对象被关闭
            if response:
                try:
                    response.close()
                except:
                    pass  # 忽略关闭时的异常

