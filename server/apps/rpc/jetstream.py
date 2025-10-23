from nats.js.api import ObjectMeta
from nats.js.errors import BucketNotFoundError
from config.components.nats import NATS_NAMESPACE
from nats_client.clients import get_nc_client
from apps.core.logger import logger


class JetStreamService:
    def __init__(self, bucket_name=NATS_NAMESPACE):
        self.bucket_name = bucket_name
        self.nc = None
        self.js = None
        self.object_store = None

    async def connect(self):
        # 复用 nats_client 的连接逻辑，统一使用 NATS_OPTIONS
        self.nc = await get_nc_client()
        self.js = self.nc.jetstream()
        try:
            self.object_store = await self.js.object_store(self.bucket_name)
        except BucketNotFoundError:
            self.object_store = await self.js.create_object_store(self.bucket_name)
        logger.info(f'Connected to NATS and initialized object store: {self.bucket_name}')

    async def put(self, key, data, description=None):
        meta = ObjectMeta(description=description) if description else None
        info = await self.object_store.put(key, data, meta=meta)
        logger.info(f'Added entry {info.name} ({info.size} bytes)')
        return info

    async def get(self, key):
        result = await self.object_store.get(key)
        logger.info(f'Fetched entry {result.info.name} ({result.info.size} bytes)')
        return result.data, result.info.description

    async def delete(self, key):
        await self.object_store.delete(key)
        logger.info(f'Deleted entry {key}')

    async def list_objects(self):
        try:
            entries = await self.object_store.list()
            logger.info(f'The object store contains {len(entries)} entries')
            return entries
        except Exception as e:
            # Object Store 为空时会抛出 NotFoundError，返回空列表
            logger.info(f'The object store is empty or error occurred: {e}')
            return []

    async def watch_updates(self):
        watcher = await self.object_store.watch(include_history=False)
        while True:
            e = await watcher.updates()
            if e:
                update_type = 'deleted' if e.deleted else 'updated'
                logger.info(f'{self.bucket_name} changed - {e.name} was {update_type}')

    async def close(self):
        await self.nc.close()
        logger.info('Closed connection to NATS')
