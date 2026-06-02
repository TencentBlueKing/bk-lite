"""Memory Engine ViewSet - API endpoints for memory engine management."""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.opspilot.memory.engines.registry import MemoryEngineRegistry, check_sdk_availability

logger = logging.getLogger(__name__)


class MemoryEngineViewSet(ViewSet):
    """记忆引擎 API

    提供引擎列表、Schema 查询、连接测试等功能。
    """

    @action(detail=False, methods=["get"], url_path="")
    def list_engines(self, request):
        """获取所有可用的记忆引擎列表

        GET /api/opspilot/memory_engines/
        """
        engines = MemoryEngineRegistry.list_engines()
        sdk_availability = check_sdk_availability()

        # 标记每个引擎的可用性
        for engine in engines:
            engine_type = engine.get("type")
            if engine_type == "local":
                engine["available"] = True
            elif engine_type == "mem0":
                engine["available"] = sdk_availability.get("mem0", False)
            elif engine_type == "zep":
                engine["available"] = sdk_availability.get("zep", False)
            elif engine_type == "custom":
                engine["available"] = sdk_availability.get("httpx", True)
            else:
                engine["available"] = True

        return Response({"result": True, "data": engines})

    @action(detail=False, methods=["get"], url_path="(?P<engine_type>[^/.]+)/schema")
    def get_schema(self, request, engine_type=None):
        """获取指定引擎的配置参数定义

        GET /api/opspilot/memory_engines/{engine_type}/schema/
        """
        try:
            schema = MemoryEngineRegistry.get_schema(engine_type)
            return Response({"result": True, "data": schema})
        except ValueError as e:
            return Response(
                {"result": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="(?P<engine_type>[^/.]+)/test")
    def test_connection(self, request, engine_type=None):
        """测试引擎连接

        POST /api/opspilot/memory_engines/{engine_type}/test/
        Body: {"config": {...}}
        """
        try:
            config = request.data.get("config", {})

            # 获取引擎类
            engine_class = MemoryEngineRegistry.get_engine_class(engine_type)

            # 创建临时引擎实例进行测试
            # 由于测试时还没有 memory_space_id，我们需要特殊处理
            if engine_type == "local":
                return Response(
                    {
                        "result": True,
                        "data": {"success": True, "message": "本地存储无需测试"},
                    }
                )

            # 对于其他引擎，创建一个临时实例
            # 这里我们直接调用引擎的测试方法，但需要模拟配置
            class TempEngine(engine_class):
                def __init__(self, config):
                    self.memory_space_id = 0
                    self._memory_space = None
                    self._config = config

            temp_engine = TempEngine(config)
            result = temp_engine.test_connection()

            return Response({"result": True, "data": result})
        except ValueError as e:
            return Response(
                {"result": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Connection test failed: {e}", exc_info=True)
            return Response(
                {
                    "result": True,
                    "data": {"success": False, "message": str(e)},
                }
            )
