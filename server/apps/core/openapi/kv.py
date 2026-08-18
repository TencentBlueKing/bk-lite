"""NATS JetStream KV 注册表读取（外部服务注册，bucket: openapi_registry）。

启动硬约束（docs/operations/server-startup-dependencies.md）：本模块任何
失败都不阻断 server 启动，也不在启动期被调用；bucket 不存在按空注册表处理
并惰性尝试创建（幂等，失败仅告警）；连接失败返回 None，由渲染层降级到
最近一次成功快照。
"""

import asyncio
import json

from apps.core.logger import openapi_logger as logger

BUCKET = "openapi_registry"


async def _fetch_async():
    from nats_client.clients import get_nc_client

    nc = await get_nc_client()
    try:
        js = nc.jetstream()
        try:
            kv = await js.key_value(BUCKET)
        except Exception:
            try:
                kv = await js.create_key_value(bucket=BUCKET)
                logger.warning("openapi_registry bucket 不存在，已惰性创建")
            except Exception:
                logger.warning("openapi_registry bucket 不存在且创建失败，按空注册表处理")
                return {}

        try:
            keys = await kv.keys()
        except Exception:
            # 空 bucket 时 nats-py 抛 NoKeysError
            return {}

        entries = {}
        for key in keys:
            try:
                raw = await kv.get(key)
                entries[key] = json.loads(raw.value)
            except Exception:
                logger.warning("openapi_registry 条目 %s 读取或解析失败，跳过", key)
        return entries
    finally:
        try:
            await nc.close()
        except Exception:
            pass


def fetch_entries():
    """同步读取全部注册条目。

    返回 {service_name: entry_dict}；NATS 不可达等整体失败时返回 None
    （区别于空注册表 {}），调用方据此降级到最近一次成功快照。
    """
    try:
        return asyncio.run(_fetch_async())
    except Exception:
        logger.exception("openapi_registry 读取失败")
        return None
