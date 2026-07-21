import asyncio
import threading

import pytest

from apps.log.utils.query_log import VictoriaMetricsAPI


class _IdleStreamResponse:
    status_code = 200

    def __init__(self):
        self.started = threading.Event()
        self.closed = threading.Event()
        self.finished = threading.Event()
        self.encoding = "utf-8"

    def raise_for_status(self):
        pass

    def iter_lines(self, chunk_size=None, decode_unicode=False):
        self.started.set()
        try:
            self.closed.wait()
            if False:
                yield None
        finally:
            self.finished.set()

    def close(self):
        self.closed.set()


class _EndlessStreamResponse(_IdleStreamResponse):
    def __init__(self):
        super().__init__()
        self.lines_read = 0

    def iter_lines(self, chunk_size=None, decode_unicode=False):
        self.started.set()
        try:
            while not self.closed.is_set():
                self.lines_read += 1
                yield f"line-{self.lines_read}"
        finally:
            self.finished.set()


@pytest.mark.asyncio
async def test_tail_async_idle_wait_does_not_busy_poll(mocker):
    fake_resp = _IdleStreamResponse()
    mocker.patch("apps.log.utils.query_log.requests.post", return_value=fake_resp)

    real_sleep = asyncio.sleep
    zero_sleep_count = 0

    async def tracked_sleep(delay):
        nonlocal zero_sleep_count
        if delay == 0:
            zero_sleep_count += 1
        await real_sleep(delay)

    mocker.patch("apps.log.utils.query_log.asyncio.sleep", side_effect=tracked_sleep)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.local"
    stream = api.tail_async("*")
    next_line = asyncio.create_task(stream.__anext__())

    await asyncio.to_thread(fake_resp.started.wait, 0.5)
    await real_sleep(0.05)
    assert zero_sleep_count == 0

    next_line.cancel()
    with pytest.raises(asyncio.CancelledError):
        await next_line
    assert fake_resp.finished.wait(0.5)


@pytest.mark.asyncio
async def test_tail_async_cancel_releases_producer_blocked_by_backpressure(mocker):
    fake_resp = _EndlessStreamResponse()
    mocker.patch("apps.log.utils.query_log.requests.post", return_value=fake_resp)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.local"
    stream = api.tail_async("*")

    assert await stream.__anext__() == "line-1"
    for _ in range(100):
        if fake_resp.lines_read >= 258:
            break
        await asyncio.sleep(0.01)
    assert fake_resp.lines_read >= 258, "生产线程未进入满队列背压等待"

    await stream.aclose()

    assert fake_resp.closed.is_set()
    assert fake_resp.finished.wait(0.5), "取消后生产线程未退出"
