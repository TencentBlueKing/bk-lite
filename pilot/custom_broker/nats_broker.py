import asyncio
import json
from asyncio import AbstractEventLoop
from typing import Any, Dict, Optional, Text

import nats
from core.server_settings import server_settings
from loguru import logger
from rasa.core.brokers.broker import EventBroker
from rasa.utils.endpoints import EndpointConfig


class NATSEventBroker(EventBroker):
    """NATS event broker for publishing Rasa events."""

    def __init__(
        self,
        host: Text,
        namespace: Optional[Text] = None,
        event_loop: Optional[AbstractEventLoop] = None,
        **kwargs: Any,
    ):
        self.host = host
        self.namespace = namespace or "bklite"
        self.event_loop = event_loop or asyncio.get_event_loop()
        self._nc = None

    @classmethod
    async def from_endpoint_config(
        cls,
        broker_config: EndpointConfig,
        event_loop: Optional[AbstractEventLoop] = None,
    ) -> Optional["NATSEventBroker"]:
        """Creates a NATSEventBroker from endpoint configuration."""
        if broker_config is None:
            return None

        return cls(
            host=broker_config.url,
            namespace=broker_config.kwargs.get("namespace"),
            event_loop=event_loop,
            **broker_config.kwargs,
        )

    async def _connect(self):
        """Connect to NATS server."""
        if self._nc is None or self._nc.is_closed:
            try:
                options = {"servers": [self.host]}
                self._nc = await nats.connect(**options)
                logger.info("Connected to NATS server success")
            except Exception as e:
                logger.error(f"Failed to connect to NATS server: {e}")
                raise

    def publish(self, event: Dict[Text, Any], headers=None) -> None:
        """Publishes an event to NATS by calling consume_bot_event method."""
        # Add bot_id to event
        event["bot_id"] = server_settings.munchkin_bot_id

        try:
            # Run the async publish in the event loop
            if self.event_loop.is_running():
                # If event loop is already running, schedule the coroutine
                asyncio.create_task(self._async_publish(event))
            else:
                # If event loop is not running, run until complete
                self.event_loop.run_until_complete(self._async_publish(event))

        except Exception as e:
            logger.error(f"Failed to publish event to NATS: {e}")

    async def _async_publish(self, event: Dict[Text, Any]) -> None:
        """Async method to publish event to NATS consume_bot_event."""
        try:
            await self._connect()

            # Create the subject for consume_bot_event in the specified namespace
            subject = f"{self.namespace}.consume_bot_event"

            # Serialize event to JSON
            event_data = json.dumps(event).encode()

            # Publish to NATS
            await self._nc.publish(subject, event_data)

            logger.info(f"NATSEventBroker published event to {subject}: {event}")

        except Exception as e:
            logger.error(f"Failed to async publish event to NATS: {e}")
            raise

    def is_ready(self) -> bool:
        """Check if the NATS connection is ready."""
        return self._nc is not None and not self._nc.is_closed

    async def close(self) -> None:
        """Close the NATS connection."""
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
            logger.info("NATS connection closed")
