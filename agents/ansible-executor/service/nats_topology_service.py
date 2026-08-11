"""Ansible Executor 的 JetStream stream/consumer 拓扑声明。"""

from core.config import logger
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import NotFoundError


class NATSTopologyMixin:
    async def _ensure_stream_and_consumer(self):
        subject_pattern = f"{self.config.js_subject_prefix}.>"
        retry_subject = f"ansible_executor.callback.retry.{self.config.nats_instance_id}"

        try:
            owner_stream = await self.js.find_stream_name_by_subject(subject_pattern)
        except NotFoundError:
            owner_stream = None
        if owner_stream and owner_stream != self.config.js_stream:
            logger.warning(
                "subject '%s' already belongs to stream '%s'; reuse this stream for restart compatibility",
                subject_pattern,
                owner_stream,
            )
            self.config.js_stream = owner_stream

        try:
            retry_owner_stream = await self.js.find_stream_name_by_subject(retry_subject)
            expected_retry_stream = f"{self.config.js_stream}_CALLBACK_RETRY"
            if retry_owner_stream != expected_retry_stream:
                raise ValueError(
                    f"retry subject '{retry_subject}' is already owned by stream '{retry_owner_stream}'. "
                    "Please change NATS_INSTANCE_ID or callback retry subject prefix."
                )
        except NotFoundError:
            pass

        stream_config = StreamConfig(
            name=self.config.js_stream,
            subjects=[subject_pattern],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_msgs=-1,
            max_age=0,
        )
        try:
            await self.js.stream_info(self.config.js_stream)
            await self.js.update_stream(stream_config)
        except NotFoundError:
            await self.js.add_stream(stream_config)
        except Exception as error:
            if "overlap" in str(error).lower():
                owner_stream = await self.js.find_stream_name_by_subject(subject_pattern)
                raise ValueError(
                    f"stream subject conflict: '{subject_pattern}' is already owned by '{owner_stream}'. "
                    "Set a unique ANSIBLE_JS_NAMESPACE or ANSIBLE_JS_SUBJECT_PREFIX."
                ) from error
            raise

        durable_name = f"{self.config.js_durable}-{self.config.nats_instance_id}"
        consumer_config = ConsumerConfig(
            durable_name=durable_name,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=subject_pattern,
            ack_wait=float(self.config.js_ack_wait),
            max_deliver=self.config.js_max_deliver,
            backoff=[float(value) for value in (self.config.js_backoff or [])] or None,
        )
        durable_name = await self._replace_filtered_consumer(
            self.config.js_stream,
            subject_pattern,
            durable_name,
            consumer_config,
            "main",
        )
        self.psub = await self.js.pull_subscribe(
            subject_pattern,
            durable=durable_name,
            stream=self.config.js_stream,
        )

        retry_stream = f"{self.config.js_stream}_CALLBACK_RETRY"
        retry_stream_config = StreamConfig(
            name=retry_stream,
            subjects=[retry_subject],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_msgs=-1,
            max_age=0,
        )
        try:
            await self.js.stream_info(retry_stream)
            await self.js.update_stream(retry_stream_config)
        except NotFoundError:
            await self.js.add_stream(retry_stream_config)
        except Exception as error:
            if "overlap" in str(error).lower():
                owner_stream = await self.js.find_stream_name_by_subject(retry_subject)
                raise ValueError(
                    f"retry stream subject conflict: '{retry_subject}' is already owned by '{owner_stream}'. "
                    "Change NATS_INSTANCE_ID or callback retry subject prefix."
                ) from error
            raise

        retry_durable = f"{self.config.js_durable}-callback-retry-{self.config.nats_instance_id}"
        retry_consumer_config = ConsumerConfig(
            durable_name=retry_durable,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=retry_subject,
            ack_wait=float(self.config.js_ack_wait),
            max_deliver=self.config.js_max_deliver,
            backoff=[float(value) for value in (self.config.js_backoff or [])] or None,
        )
        retry_durable = await self._replace_filtered_consumer(
            retry_stream,
            retry_subject,
            retry_durable,
            retry_consumer_config,
            "callback retry",
        )
        self.retry_subject = retry_subject
        self.retry_psub = await self.js.pull_subscribe(
            retry_subject,
            durable=retry_durable,
            stream=retry_stream,
        )

    async def _replace_filtered_consumer(self, stream, subject, durable, config, label):
        existing_consumer = None
        for info in await self.js.consumers_info(stream):
            current = info.config
            if current and getattr(current, "filter_subject", "") == subject:
                existing_consumer = info.name
                break
        if existing_consumer and existing_consumer != durable:
            logger.warning(
                "reuse existing %s consumer '%s' for filter '%s' on stream '%s'",
                label,
                existing_consumer,
                subject,
                stream,
            )
            durable = existing_consumer
            config.durable_name = durable
        try:
            await self.js.consumer_info(stream, durable)
            await self.js.delete_consumer(stream, durable)
            await self.js.add_consumer(stream, config)
        except NotFoundError:
            await self.js.add_consumer(stream, config)
        return durable
