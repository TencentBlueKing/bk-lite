"""JetStream 指标发布的异步确认与双信贷窗口。"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class JetStreamMessage:
    """一条可去重的 JetStream 消息。"""

    payload: bytes
    message_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if not self.message_id:
            raise ValueError("message_id must not be empty")


@dataclass(frozen=True)
class JetStreamPublishWindowSettings:
    max_pending_messages: int = 1024
    max_pending_bytes: int = 128 * 1024 * 1024
    puback_timeout_seconds: float = 30.0
    max_attempts: int = 2
    expected_stream: str = "CMDB_METRICS"

    def __post_init__(self) -> None:
        if self.max_pending_messages <= 0:
            raise ValueError("max_pending_messages must be greater than zero")
        if self.max_pending_bytes <= 0:
            raise ValueError("max_pending_bytes must be greater than zero")
        if self.puback_timeout_seconds <= 0:
            raise ValueError("puback_timeout_seconds must be greater than zero")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if not str(self.expected_stream).strip():
            raise ValueError("expected_stream must not be empty")


@dataclass(frozen=True)
class JetStreamPublishWindowSnapshot:
    pending_messages: int
    pending_bytes: int
    peak_pending_messages: int
    peak_pending_bytes: int
    confirmed_total: int
    retry_total: int
    puback_timeout_total: int
    rejected_total: int
    puback_duration_seconds_p95: float
    puback_duration_seconds_p99: float


class JetStreamWindowPublishError(RuntimeError):
    """窗口内至少一条消息未获得 PubAck。"""

    delivery_detected = True

    def __init__(
        self,
        *,
        attempted_indices: tuple[int, ...],
        confirmed_indices: tuple[int, ...],
        error: BaseException,
    ) -> None:
        self.attempted_indices = attempted_indices
        self.confirmed_indices = confirmed_indices
        self.error = error
        super().__init__(
            "JetStream publish window incomplete: "
            f"confirmed={len(confirmed_indices)}/{len(attempted_indices)}, "
            f"error_type={type(error).__name__}"
        )
        self.__cause__ = error


class JetStreamPublishWindow:
    """在所有调用之间共享消息数与字节数信贷，并等待逐消息 PubAck。"""

    def __init__(
        self,
        jetstream_provider: Callable,
        *,
        settings: JetStreamPublishWindowSettings | None = None,
    ) -> None:
        self._provider = jetstream_provider
        self.settings = settings or JetStreamPublishWindowSettings()
        self._condition = asyncio.Condition()
        self._pending_messages = 0
        self._pending_bytes = 0
        self._peak_pending_messages = 0
        self._peak_pending_bytes = 0
        self._confirmed_total = 0
        self._retry_total = 0
        self._puback_timeout_total = 0
        self._rejected_total = 0
        self._puback_durations: deque[float] = deque(maxlen=500)

    def snapshot(self) -> JetStreamPublishWindowSnapshot:
        ordered_durations = sorted(self._puback_durations)
        return JetStreamPublishWindowSnapshot(
            pending_messages=self._pending_messages,
            pending_bytes=self._pending_bytes,
            peak_pending_messages=self._peak_pending_messages,
            peak_pending_bytes=self._peak_pending_bytes,
            confirmed_total=self._confirmed_total,
            retry_total=self._retry_total,
            puback_timeout_total=self._puback_timeout_total,
            rejected_total=self._rejected_total,
            puback_duration_seconds_p95=_percentile(ordered_durations, 0.95),
            puback_duration_seconds_p99=_percentile(ordered_durations, 0.99),
        )

    async def publish(
        self,
        subject: str,
        messages: Iterable[JetStreamMessage],
        *,
        before_publish: Callable[[int], bool] | None = None,
    ) -> int:
        """懒消费消息并并行发布；返回获得 PubAck 的消息数。"""
        pending: set[asyncio.Task] = set()
        attempted_indices: list[int] = []
        confirmed_indices: list[int] = []
        first_error: BaseException | None = None

        async def cancel_pending() -> None:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                pending.clear()

        async def collect_done(*, wait_for_one: bool) -> None:
            nonlocal first_error
            if not pending:
                return
            try:
                if wait_for_one:
                    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                else:
                    done = set(pending)
                    await asyncio.wait(done)
            except asyncio.CancelledError:
                await cancel_pending()
                raise
            for task in done:
                pending.discard(task)
                index = int(getattr(task, "message_index"))
                try:
                    await task
                except BaseException as error:  # 每条失败在批次边界统一归因
                    if first_error is None:
                        first_error = error
                else:
                    confirmed_indices.append(index)

        try:
            for index, message in enumerate(messages):
                if before_publish is not None and not before_publish(index):
                    continue
                if len(message.payload) > self.settings.max_pending_bytes:
                    raise ValueError("message payload exceeds JetStream byte window")
                while len(pending) >= self.settings.max_pending_messages:
                    await collect_done(wait_for_one=True)
                attempted_indices.append(index)
                task = asyncio.create_task(
                    self._publish_one(subject, message),
                    name=f"jetstream-puback:{message.message_id[:64]}",
                )
                task.message_index = index  # type: ignore[attr-defined]
                pending.add(task)

            await collect_done(wait_for_one=False)
        except BaseException:
            await cancel_pending()
            raise
        if first_error is not None:
            raise JetStreamWindowPublishError(
                attempted_indices=tuple(attempted_indices),
                confirmed_indices=tuple(sorted(confirmed_indices)),
                error=first_error,
            ) from first_error
        return len(confirmed_indices)

    async def _publish_one(self, subject: str, message: JetStreamMessage) -> None:
        last_error: BaseException | None = None
        for attempt in range(self.settings.max_attempts):
            if attempt:
                self._retry_total += 1
            await self._reserve(len(message.payload))
            attempt_started_at = time.monotonic()
            future = None
            try:
                async with asyncio.timeout(self.settings.puback_timeout_seconds):
                    jetstream = self._provider()
                    if inspect.isawaitable(jetstream):
                        jetstream = await jetstream
                    future = await jetstream.publish_async(
                        subject,
                        message.payload,
                        wait_stall=self.settings.puback_timeout_seconds,
                        stream=self.settings.expected_stream,
                        headers={"Nats-Msg-Id": message.message_id},
                    )
                    await asyncio.shield(future)
            except asyncio.CancelledError:
                if future is not None and not future.done():
                    future.cancel()
                raise
            except Exception as error:
                last_error = error
                if isinstance(error, TimeoutError):
                    self._puback_timeout_total += 1
                if future is not None and not future.done():
                    future.cancel()
            else:
                self._puback_durations.append(time.monotonic() - attempt_started_at)
                self._confirmed_total += 1
                return
            finally:
                await self._release(len(message.payload))
        self._rejected_total += 1
        assert last_error is not None
        raise last_error

    async def _reserve(self, payload_bytes: int) -> None:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._pending_messages < self.settings.max_pending_messages
                and self._pending_bytes + payload_bytes <= self.settings.max_pending_bytes
            )
            self._pending_messages += 1
            self._pending_bytes += payload_bytes
            self._peak_pending_messages = max(self._peak_pending_messages, self._pending_messages)
            self._peak_pending_bytes = max(self._peak_pending_bytes, self._pending_bytes)

    async def _release(self, payload_bytes: int) -> None:
        async with self._condition:
            self._pending_messages -= 1
            self._pending_bytes -= payload_bytes
            self._condition.notify_all()


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    return ordered[int((len(ordered) - 1) * fraction)]
