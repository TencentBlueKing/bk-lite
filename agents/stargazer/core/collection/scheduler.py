"""跨 CollectionRun 公平派发目标的全局调度模块。"""

from __future__ import annotations

import asyncio
import operator
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, Iterable, Iterator, Mapping, TypeVar

from core.collection.enums import WorkloadClass

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class _RunState(Generic[T, R]):
    items: Iterator[T]
    handler: Callable[[T], Awaitable[R]]
    results: list[R | None]
    done: asyncio.Future[tuple[R, ...]]
    workload: WorkloadClass = WorkloadClass.CONFIGURATION
    capacity_group: str = "default"
    completed: int = 0
    exhausted: bool = False
    enqueued_at: float = 0.0
    first_dispatched: bool = False
    pending: int = 0
    pending_known: bool = True
    tasks: set[asyncio.Task] = field(default_factory=set)


class CollectionScheduler:
    """以 round-robin 和全局窗口公平执行多个 Run 的目标。"""

    def __init__(
        self,
        *,
        max_in_flight: int,
        topology_max_in_flight: int | None = None,
        allow_topology_idle_borrow: bool = True,
        workload_weights: Mapping[WorkloadClass | str, int] | None = None,
        capacity_group_limits: Mapping[str, int] | None = None,
        metrics=None,
    ) -> None:
        if max_in_flight <= 0:
            raise ValueError("max_in_flight must be greater than zero")
        if topology_max_in_flight is not None and topology_max_in_flight <= 0:
            raise ValueError("topology_max_in_flight must be greater than zero")
        self._max_in_flight = int(max_in_flight)
        del allow_topology_idle_borrow  # 软配额统一支持空闲借满，仅保留历史形参。
        if workload_weights is None:
            if topology_max_in_flight is None:
                workload_weights = {WorkloadClass.CONFIGURATION: max_in_flight}
            else:
                workload_weights = {
                    WorkloadClass.CONFIGURATION: max_in_flight - int(topology_max_in_flight),
                    WorkloadClass.NETWORK_TOPOLOGY: int(topology_max_in_flight),
                }
        normalized_weights = {WorkloadClass(key): int(value) for key, value in workload_weights.items()}
        if not normalized_weights or any(value <= 0 for value in normalized_weights.values()):
            raise ValueError("workload weights must be positive")
        self._workload_weights = normalized_weights
        normalized_group_limits = {str(key).strip(): int(value) for key, value in (capacity_group_limits or {}).items()}
        if any(not key or value <= 0 for key, value in normalized_group_limits.items()):
            raise ValueError("capacity group limits must be positive")
        self._capacity_group_limits = normalized_group_limits
        self._metrics = metrics
        self._condition = asyncio.Condition()
        self._runs: dict[str, _RunState] = {}
        self._order: deque[str] = deque()
        self._dispatcher: asyncio.Task | None = None
        self._closing = False
        self.active = 0
        self.active_by_workload = {workload: 0 for workload in WorkloadClass}
        self.active_by_capacity_group: dict[str, int] = {}
        self.peak = 0
        self.completed_total = 0

    @property
    def pending(self) -> int:
        return sum(state.pending for state in self._runs.values())

    @property
    def topology_active(self) -> int:
        return self.active_by_workload[WorkloadClass.NETWORK_TOPOLOGY]

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

    @property
    def pending_by_workload(self) -> dict[WorkloadClass, int]:
        result = {workload: 0 for workload in WorkloadClass}
        for state in self._runs.values():
            result[state.workload] += max(0, state.pending)
        return result

    @property
    def borrowed_by_workload(self) -> dict[WorkloadClass, int]:
        return {
            workload: max(
                0,
                self.active_by_workload[workload] - self._workload_weights.get(workload, 0),
            )
            for workload in WorkloadClass
        }

    @property
    def pending_by_capacity_group(self) -> dict[str, int]:
        result = {group: 0 for group in self._capacity_group_limits}
        for state in self._runs.values():
            result[state.capacity_group] = result.get(state.capacity_group, 0) + max(0, state.pending)
        return result

    @property
    def capacity_group_limits(self) -> dict[str, int]:
        return dict(self._capacity_group_limits)

    async def execute(
        self,
        run_id: str,
        items: Iterable[T],
        handler: Callable[[T], Awaitable[R]],
        *,
        workload: WorkloadClass | str = WorkloadClass.CONFIGURATION,
        capacity_group: str = "default",
    ) -> tuple[R, ...]:
        loop = asyncio.get_running_loop()
        workload_class = WorkloadClass.CONFIGURATION if workload == "general" else WorkloadClass(workload)
        if workload_class not in self._workload_weights:
            raise ValueError(f"workload is not configured: {workload_class.value}")
        capacity_group_name = str(capacity_group or "default").strip()
        length_hint = operator.length_hint(items, -1)
        state = _RunState(
            items=iter(items),
            handler=handler,
            results=[],
            done=loop.create_future(),
            workload=workload_class,
            capacity_group=capacity_group_name,
            enqueued_at=time.monotonic(),
            pending=max(0, length_hint),
            pending_known=length_hint >= 0,
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
                if state.pending_known and state.pending == 0:
                    state.exhausted = True
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
                self.active_by_workload[state.workload] += 1
                self.active_by_capacity_group[state.capacity_group] = self.active_by_capacity_group.get(state.capacity_group, 0) + 1
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
                self.active_by_workload[state.workload] = max(0, self.active_by_workload[state.workload] - 1)
                group_active = max(
                    0,
                    self.active_by_capacity_group.get(state.capacity_group, 0) - 1,
                )
                if group_active:
                    self.active_by_capacity_group[state.capacity_group] = group_active
                else:
                    self.active_by_capacity_group.pop(state.capacity_group, None)
                self._condition.notify_all()

    def _has_dispatchable_run(self) -> bool:
        if self.active >= self._max_in_flight:
            return False
        return any(
            state is not None and not state.exhausted and self._run_has_capacity(state)
            for run_id in self._order
            if (state := self._runs.get(run_id)) is not None
        )

    def _take_next_dispatchable_run(self) -> str | None:
        for _ in range(len(self._order)):
            run_id = self._order.popleft()
            state = self._runs.get(run_id)
            if state is None or state.exhausted:
                continue
            if self._run_has_capacity(state):
                return run_id
            self._order.append(run_id)
        return None

    def _run_has_capacity(self, state: _RunState) -> bool:
        return self._workload_has_capacity(state.workload) and self._capacity_group_has_capacity(state.capacity_group)

    def _capacity_group_has_capacity(self, capacity_group: str) -> bool:
        limit = self._capacity_group_limits.get(capacity_group, self._max_in_flight)
        return self.active_by_capacity_group.get(capacity_group, 0) < limit

    def _workload_has_capacity(self, workload: WorkloadClass) -> bool:
        if self.active >= self._max_in_flight:
            return False
        targets = self._effective_workload_targets()
        return self.active_by_workload[workload] < targets.get(workload, 0)

    def _effective_workload_targets(self) -> dict[WorkloadClass, int]:
        """按当前仍有待派发目标的类别重新归一化软配额。"""

        waiting = self._waiting_workloads()
        if not waiting:
            return {}
        total_weight = sum(self._workload_weights[item] for item in waiting)
        raw = {item: self._max_in_flight * self._workload_weights[item] / total_weight for item in waiting}
        targets = {item: int(value) for item, value in raw.items()}
        remainder = self._max_in_flight - sum(targets.values())
        order = sorted(
            waiting,
            key=lambda item: (-(raw[item] - targets[item]), item.value),
        )
        for item in order[:remainder]:
            targets[item] += 1
        return targets

    def _waiting_workloads(self) -> set[WorkloadClass]:
        return {state.workload for state in self._runs.values() if not state.exhausted and (not state.pending_known or state.pending > 0)}

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
