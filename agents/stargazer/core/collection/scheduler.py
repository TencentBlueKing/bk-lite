"""跨 CollectionRun 公平派发目标的全局调度模块。"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class _RunState(Generic[T, R]):
    items: tuple[T, ...]
    handler: Callable[[T], Awaitable[R]]
    results: list[R | None]
    done: asyncio.Future[tuple[R, ...]]
    next_index: int = 0
    completed: int = 0
    tasks: set[asyncio.Task] = field(default_factory=set)


class CollectionScheduler:
    """以 round-robin 和全局窗口公平执行多个 Run 的目标。"""

    def __init__(self, *, max_in_flight: int) -> None:
        if max_in_flight <= 0:
            raise ValueError("max_in_flight must be greater than zero")
        self._max_in_flight = int(max_in_flight)
        self._condition = asyncio.Condition()
        self._runs: dict[str, _RunState] = {}
        self._order: deque[str] = deque()
        self._dispatcher: asyncio.Task | None = None
        self._closing = False
        self.active = 0
        self.peak = 0

    async def execute(
        self,
        run_id: str,
        items: Iterable[T],
        handler: Callable[[T], Awaitable[R]],
    ) -> tuple[R, ...]:
        item_tuple = tuple(items)
        if not item_tuple:
            return ()
        loop = asyncio.get_running_loop()
        state = _RunState(
            items=item_tuple,
            handler=handler,
            results=[None] * len(item_tuple),
            done=loop.create_future(),
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
                self._dispatcher = asyncio.create_task(
                    self._dispatch_loop(), name="collection-target-dispatcher"
                )
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
            tasks = tuple(
                task for state in states for task in state.tasks if not task.done()
            )
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
            async with self._condition:
                await self._condition.wait_for(
                    lambda: self._closing
                    or (self.active < self._max_in_flight and bool(self._order))
                )
                if self._closing:
                    return
                while self.active < self._max_in_flight and self._order:
                    run_id = self._order.popleft()
                    state = self._runs.get(run_id)
                    if state is None or state.next_index >= len(state.items):
                        continue
                    index = state.next_index
                    state.next_index += 1
                    if state.next_index < len(state.items):
                        self._order.append(run_id)
                    self.active += 1
                    self.peak = max(self.peak, self.active)
                    task = asyncio.create_task(
                        self._run_item(run_id, state, index),
                        name=f"collection-target:{run_id}:{index}",
                    )
                    state.tasks.add(task)

    async def _run_item(self, run_id: str, state: _RunState[T, R], index: int) -> None:
        current = asyncio.current_task()
        try:
            result = await state.handler(state.items[index])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Run 级执行异常由调用方决定状态
            if not state.done.done():
                state.done.set_exception(exc)
            await self._cancel_run(run_id, exclude=current)
        else:
            state.results[index] = result
            state.completed += 1
            if state.completed == len(state.items) and not state.done.done():
                state.done.set_result(tuple(state.results))
                async with self._condition:
                    self._runs.pop(run_id, None)
        finally:
            async with self._condition:
                state.tasks.discard(current)
                self.active = max(0, self.active - 1)
                self._condition.notify_all()

    async def _cancel_run(
        self, run_id: str, *, exclude: asyncio.Task | None = None
    ) -> None:
        async with self._condition:
            state = self._runs.pop(run_id, None)
            if state is None:
                return
            self._order = deque(item for item in self._order if item != run_id)
            tasks = tuple(
                task for task in state.tasks if task is not exclude and not task.done()
            )
            self._condition.notify_all()
        for task in tasks:
            task.cancel()
