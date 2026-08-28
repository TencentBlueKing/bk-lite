"""跨 CollectionRun 公平派发目标的全局调度模块。"""

from __future__ import annotations

import asyncio
import operator
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class _RunState(Generic[T, R]):
    items: Iterator[T]
    handler: Callable[[T], Awaitable[R]]
    results: list[R | None]
    done: asyncio.Future[tuple[R, ...]]
    workload: str = "general"
    completed: int = 0
    exhausted: bool = False
    enqueued_at: float = 0.0
    first_dispatched: bool = False
    pending: int = 0
    tasks: set[asyncio.Task] = field(default_factory=set)


class CollectionScheduler:
    """以 round-robin 和全局窗口公平执行多个 Run 的目标。"""

    def __init__(
        self,
        *,
        max_in_flight: int,
        topology_max_in_flight: int | None = None,
        allow_topology_idle_borrow: bool = True,
        metrics=None,
    ) -> None:
        if max_in_flight <= 0:
            raise ValueError("max_in_flight must be greater than zero")
        if topology_max_in_flight is not None and topology_max_in_flight <= 0:
            raise ValueError("topology_max_in_flight must be greater than zero")
        self._max_in_flight = int(max_in_flight)
        self._topology_max_in_flight = None if topology_max_in_flight is None else int(topology_max_in_flight)
        self._allow_topology_idle_borrow = bool(allow_topology_idle_borrow)
        self._metrics = metrics
        self._condition = asyncio.Condition()
        self._runs: dict[str, _RunState] = {}
        self._order: deque[str] = deque()
        self._dispatcher: asyncio.Task | None = None
        self._closing = False
        self.active = 0
        self.topology_active = 0
        self.peak = 0
        self.completed_total = 0

    @property
    def pending(self) -> int:
        return sum(state.pending for state in self._runs.values())

    @property
    def capacity(self) -> int:
        return self._max_in_flight

    @property
    def pending_runs(self) -> int:
        return len(self._runs)

    @property
    def completed(self) -> int:
        """仍在调度中的 Run 已完成目标数。"""

        return sum(state.completed for state in self._runs.values())

    async def execute(
        self,
        run_id: str,
        items: Iterable[T],
        handler: Callable[[T], Awaitable[R]],
        *,
        workload: str = "general",
    ) -> tuple[R, ...]:
        loop = asyncio.get_running_loop()
        workload_class = "network_topology" if self._topology_max_in_flight is not None and workload == "network_topology" else "general"
        state = _RunState(
            items=iter(items),
            handler=handler,
            results=[],
            done=loop.create_future(),
            workload=workload_class,
            enqueued_at=time.monotonic(),
            pending=max(0, operator.length_hint(items, 0)),
        )
        async with self._condition:
            if self._closing:
                raise RuntimeError("collection scheduler is shutting down")
            if run_id in self._runs:
                raise ValueError(f"run already registered: {run_id}")
            self._runs[run_id] = state
            # 新 Run 优先获得下一空闲槽位，避免大 Run 的剩余目标插队。
            self._order.appendleft(run_id)
            if self._dispatcher is None or self._dispatcher.done():
                self._dispatcher = asyncio.create_task(self._dispatch_loop(), name="collection-target-dispatcher")
            self._condition.notify_all()
        try:
            return await state.done
        except asyncio.CancelledError:
            await self._cancel_run(run_id)
            raise

    async def shutdown(self) -> None:
        async with self._condition:
            self._closing = True
            states = tuple(self._runs.values())
            tasks = tuple(task for state in states for task in state.tasks if not task.done())
            for state in states:
                if not state.done.done():
                    state.done.cancel()
            self._runs.clear()
            self._order.clear()
            self._condition.notify_all()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        dispatcher = self._dispatcher
        if dispatcher is not None and not dispatcher.done():
            dispatcher.cancel()
            await asyncio.gather(dispatcher, return_exceptions=True)

    async def _dispatch_loop(self) -> None:
        while True:
            tasks_created = 0
            async with self._condition:
                await self._condition.wait_for(lambda: self._closing or self._has_dispatchable_run())
                if self._closing:
                    return
                run_id = self._take_next_dispatchable_run()
                if run_id is None:
                    continue
                state = self._runs.get(run_id)
                if state is None or state.exhausted:
                    continue
                try:
                    item = next(state.items)
                except StopIteration:
                    state.exhausted = True
                    if state.completed == len(state.results) and not state.done.done():
                        state.done.set_result(tuple(state.results))
                        self._runs.pop(run_id, None)
                    continue
                index = len(state.results)
                state.pending = max(0, state.pending - 1)
                state.results.append(None)
                dispatched_at = time.monotonic()
                if not state.first_dispatched:
                    state.first_dispatched = True
                    if self._metrics is not None:
                        self._metrics.observe(
                            "run_first_schedule_wait_seconds",
                            dispatched_at - state.enqueued_at,
                        )
                if self._metrics is not None:
                    self._metrics.increment("scheduler_dispatch_total")
                    self._metrics.observe(
                        "target_schedule_wait_seconds",
                        dispatched_at - state.enqueued_at,
                    )
                self._order.append(run_id)
                self.active += 1
                if state.workload == "network_topology":
                    self.topology_active += 1
                self.peak = max(self.peak, self.active)
                task = asyncio.create_task(
                    self._run_item(run_id, state, index, item, dispatched_at),
                    name=f"collection-target:{run_id}:{index}",
                )
                state.tasks.add(task)
                tasks_created = 1
            if tasks_created:
                # quantum 固定为 1：每创建一个目标 Task 都让定时器和 I/O 获得运行机会。
                if self._metrics is not None:
                    self._metrics.increment("scheduler_yield_total")
                await asyncio.sleep(0)

    async def _run_item(
        self,
        run_id: str,
        state: _RunState[T, R],
        index: int,
        item: T,
        dispatched_at: float,
    ) -> None:
        current = asyncio.current_task()
        if self._metrics is not None:
            self._metrics.observe(
                "target_dispatch_to_started_seconds",
                time.monotonic() - dispatched_at,
            )
        try:
            result = await state.handler(item)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Run 级执行异常由调用方决定状态
            if not state.done.done():
                state.done.set_exception(exc)
            await self._cancel_run(run_id, exclude=current)
        else:
            state.results[index] = result
            state.completed += 1
            self.completed_total += 1
            if state.exhausted and state.completed == len(state.results) and not state.done.done():
                state.done.set_result(tuple(state.results))
                async with self._condition:
                    self._runs.pop(run_id, None)
        finally:
            async with self._condition:
                state.tasks.discard(current)
                self.active = max(0, self.active - 1)
                if state.workload == "network_topology":
                    self.topology_active = max(0, self.topology_active - 1)
                self._condition.notify_all()

    def _has_dispatchable_run(self) -> bool:
        if self.active >= self._max_in_flight:
            return False
        return any(
            state is not None and not state.exhausted and self._workload_has_capacity(state.workload)
            for run_id in self._order
            if (state := self._runs.get(run_id)) is not None
        )

    def _take_next_dispatchable_run(self) -> str | None:
        for _ in range(len(self._order)):
            run_id = self._order.popleft()
            state = self._runs.get(run_id)
            if state is None or state.exhausted:
                continue
            if self._workload_has_capacity(state.workload):
                return run_id
            self._order.append(run_id)
        return None

    def _workload_has_capacity(self, workload: str) -> bool:
        if self.active >= self._max_in_flight:
            return False
        topology_limit = self._topology_max_in_flight
        if topology_limit is None:
            return True
        if workload == "network_topology":
            return self.topology_active < self._effective_topology_limit()
        if not self._topology_is_waiting():
            return True
        general_active = self.active - self.topology_active
        general_reserved = max(0, self._max_in_flight - topology_limit)
        return general_active < general_reserved + self.topology_active

    def _effective_topology_limit(self) -> int:
        """普通目标完全空闲时，允许拓扑借用普通容量的一半。"""

        topology_limit = self._topology_max_in_flight
        assert topology_limit is not None
        if not self._allow_topology_idle_borrow or self._general_is_present():
            return topology_limit
        general_capacity = max(0, self._max_in_flight - topology_limit)
        return min(self._max_in_flight, topology_limit + general_capacity // 2)

    def _general_is_present(self) -> bool:
        if self.active > self.topology_active:
            return True
        return any(
            state is not None and not state.exhausted and state.workload == "general"
            for run_id in self._order
            if (state := self._runs.get(run_id)) is not None
        )

    def _topology_is_waiting(self) -> bool:
        return any(
            state is not None and not state.exhausted and state.workload == "network_topology"
            for run_id in self._order
            if (state := self._runs.get(run_id)) is not None
        )

    async def _cancel_run(self, run_id: str, *, exclude: asyncio.Task | None = None) -> None:
        async with self._condition:
            state = self._runs.pop(run_id, None)
            if state is None:
                return
            self._order = deque(item for item in self._order if item != run_id)
            tasks = tuple(task for task in state.tasks if task is not exclude and not task.done())
            self._condition.notify_all()
        for task in tasks:
            task.cancel()
