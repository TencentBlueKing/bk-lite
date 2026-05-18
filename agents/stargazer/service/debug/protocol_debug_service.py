# -- coding: utf-8 --
# @File: protocol_debug_service.py
# @Time: 2026/05/08
"""
协议诊断统一入口，按 action 分发到对应执行函数。
"""

from sanic.log import logger


class ProtocolDebugService:
    def __init__(self, data: dict):
        self.data = data

    async def execute(self) -> dict:
        """
        按 action 分发到对应执行函数。
        统一捕获异常，映射到 stage + summary。
        记录 duration_ms。
        """
        from service.debug.ipmi_debug import run_ipmi_debug, run_ipmi_test_connection
        from service.debug.snmp_debug import run_bulk_walk, run_get_oid, run_snmp_test_connection

        action = self.data.get("action")
        protocol = self.data.get("protocol")

        logger.info(f"[ProtocolDebugService] protocol={protocol} action={action} target={self.data.get('target')}")

        try:
            if action == "test_connection":
                if protocol == "snmp":
                    return await run_snmp_test_connection(self.data)
                elif protocol == "ipmi":
                    return await run_ipmi_test_connection(self.data)
                else:
                    return self._error_result("param", f"不支持的协议: {protocol}")

            elif action == "raw_collect":
                return await run_bulk_walk(self.data)

            elif action == "get_oid":
                return await run_get_oid(self.data)

            elif action == "ipmi_collect":
                return await run_ipmi_debug(self.data)

            else:
                return self._error_result("param", f"不支持的 action: {action}")

        except Exception as e:
            logger.exception(f"[ProtocolDebugService] unexpected error: {e}")
            return self._error_result("unknown", f"未知错误: {e}")

    @staticmethod
    def _error_result(stage: str, summary: str) -> dict:
        return {
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": summary,
            "duration_ms": 0,
        }
