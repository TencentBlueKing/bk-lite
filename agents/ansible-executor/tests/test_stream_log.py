import asyncio
import json
import sys
import time

import pytest
from service import ansible_runner as runner_module
from service.ansible_runner import LineEventStreamer, run_command

# ---------------------------------------------------------------------------
# Pure-logic tests: bytes -> per-line events (no subprocess, no NATS).
# ---------------------------------------------------------------------------


def _drain(streamer: LineEventStreamer, chunks: list[bytes]) -> list[str]:
    lines: list[str] = []
    for chunk in chunks:
        lines.extend(streamer.feed(chunk))
    flushed = streamer.flush()
    if flushed is not None:
        lines.append(flushed)
    return lines


def test_line_streamer_splits_complete_lines():
    streamer = LineEventStreamer()
    lines = _drain(streamer, [b"line1\nline2\n"])
    assert lines == ["line1", "line2"]


def test_line_streamer_buffers_partial_line_across_chunks():
    streamer = LineEventStreamer()
    # A single logical line split across two 8192-style chunks.
    lines = _drain(streamer, [b"hello ", b"world\n"])
    assert lines == ["hello world"]


def test_line_streamer_handles_line_boundary_split_mid_byte():
    streamer = LineEventStreamer()
    # The \n itself lands at the start of the next chunk.
    lines = _drain(streamer, [b"abc", b"\ndef\n"])
    assert lines == ["abc", "def"]


def test_line_streamer_flushes_trailing_line_without_newline():
    streamer = LineEventStreamer()
    lines = _drain(streamer, [b"complete\ntrailing-no-newline"])
    assert lines == ["complete", "trailing-no-newline"]


def test_line_streamer_strips_carriage_return():
    streamer = LineEventStreamer()
    lines = _drain(streamer, [b"windows\r\nline\r\n"])
    assert lines == ["windows", "line"]


def test_line_streamer_flush_returns_none_when_empty():
    streamer = LineEventStreamer()
    assert streamer.feed(b"only\n") == ["only"]
    assert streamer.flush() is None


def test_line_streamer_decodes_utf8_with_replacement():
    streamer = LineEventStreamer()
    # Valid UTF-8 multibyte char split across chunks must still decode.
    payload = "中文行".encode("utf-8")
    lines = _drain(streamer, [payload[:2], payload[2:] + b"\n"])
    assert lines == ["中文行"]


def test_line_streamer_chunks_oversized_line_with_visible_marker():
    streamer = LineEventStreamer(max_line_bytes=4)

    lines = _drain(streamer, [b"abcdefghij\n"])

    assert lines == [
        "abcd...[实时日志超长行分段]",
        "efgh...[实时日志超长行分段]",
        "ij",
    ]
    assert streamer.chunked_lines == 2


def test_line_streamer_does_not_split_valid_utf8_character():
    streamer = LineEventStreamer(max_line_bytes=4)

    lines = _drain(streamer, ["中文中文\n".encode("utf-8")])

    assert "�" not in "".join(lines)
    assert "".join(line.replace("...[实时日志超长行分段]", "") for line in lines) == "中文中文"


# ---------------------------------------------------------------------------
# Integration tests: run_command streams stdout line-by-line via callback.
# ---------------------------------------------------------------------------


class FakePublisher:
    def __init__(self, fail: bool = False, delay: float = 0):
        self.calls: list[tuple[str, bytes]] = []
        self.fail = fail
        self.delay = delay

    async def publish(self, subject: str, data: bytes) -> None:
        self.calls.append((subject, data))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("nats down")

    def decoded(self) -> list[dict]:
        return [json.loads(data.decode("utf-8")) for _, data in self.calls]


@pytest.mark.asyncio
async def test_run_command_streams_each_line():
    publisher = FakePublisher()
    script = "import sys\n" "for i in range(3):\n" "    print('line%d' % i)\n"
    code, output, _ = await run_command(
        [sys.executable, "-c", script],
        timeout=10,
        stream_publish=publisher.publish,
        stream_log_topic="bk.ans_exec.stream.exec-1",
        execution_id="exec-1",
    )

    assert code == 0
    # Full output is still accumulated and returned unchanged.
    assert "line0" in output and "line2" in output

    events = publisher.decoded()
    assert "\n".join(e["line"] for e in events).splitlines() == ["line0", "line1", "line2"]
    # Topic correct on every publish.
    assert all(subject == "bk.ans_exec.stream.exec-1" for subject, _ in publisher.calls)
    # Flat JSON contract.
    for event in events:
        assert event["execution_id"] == "exec-1"
        assert event["stream"] == "stdout"
        assert "timestamp" in event and event["timestamp"]
        assert set(event.keys()) == {"execution_id", "stream", "line", "timestamp"}


@pytest.mark.asyncio
async def test_run_command_flushes_trailing_line_without_newline():
    publisher = FakePublisher()
    code, output, _ = await run_command(
        [sys.executable, "-c", "import sys; sys.stdout.write('no-newline-tail')"],
        timeout=10,
        stream_publish=publisher.publish,
        stream_log_topic="bk.stream",
        execution_id="exec-2",
    )

    assert code == 0
    assert output.strip() == "no-newline-tail"
    lines = [e["line"] for e in publisher.decoded()]
    assert lines == ["no-newline-tail"]


@pytest.mark.asyncio
async def test_run_command_no_streaming_without_publisher():
    # Without stream_publish/topic/execution_id, behaviour is unchanged.
    code, output, _ = await run_command(
        [sys.executable, "-c", "print('hello')"],
        timeout=10,
    )
    assert code == 0
    assert output.strip() == "hello"


@pytest.mark.asyncio
async def test_run_command_swallows_publish_errors():
    publisher = FakePublisher(fail=True)
    # Even though every publish raises, the command must complete and return output.
    code, output, meta = await run_command(
        [sys.executable, "-c", "print('still works')"],
        timeout=10,
        stream_publish=publisher.publish,
        stream_log_topic="bk.stream",
        execution_id="exec-3",
    )
    assert code == 0
    assert output.strip() == "still works"
    # Publish was attempted (and raised) at least once.
    assert len(publisher.calls) >= 1
    assert meta["stream_lines_dropped"] >= 1
    assert meta["stream_publish_failures"] >= 1


@pytest.mark.asyncio
async def test_slow_publisher_does_not_consume_command_timeout():
    publisher = FakePublisher(delay=0.05)
    script = "for i in range(100): print('line%d' % i)"

    started = time.monotonic()
    code, output, meta = await run_command(
        [sys.executable, "-c", script],
        timeout=0.2,
        stream_publish=publisher.publish,
        stream_log_topic="bk.stream",
        execution_id="exec-slow",
        stream_queue_size=4,
        stream_batch_size=2,
        stream_flush_timeout=0.05,
    )
    elapsed = time.monotonic() - started

    assert code == 0
    assert "line99" in output
    assert elapsed < 0.5
    assert meta["stream_lines_dropped"] > 0
    assert meta["stream_flush_timed_out"] is True


@pytest.mark.asyncio
async def test_stream_queue_batches_lines_in_order():
    publisher = FakePublisher()
    script = "for i in range(100): print('line%d' % i)"

    code, output, meta = await run_command(
        [sys.executable, "-c", script],
        timeout=2,
        stream_publish=publisher.publish,
        stream_log_topic="bk.stream",
        execution_id="exec-batch",
        stream_queue_size=128,
        stream_batch_size=20,
        stream_flush_timeout=1,
    )

    assert code == 0
    assert "line99" in output
    events = [event for event in publisher.decoded() if event.get("type") != "gap"]
    assert "\n".join(event["line"] for event in events).splitlines() == [f"line{i}" for i in range(100)]
    assert len(events) <= 5
    assert meta["stream_lines_dropped"] == 0
    assert meta["stream_flush_timed_out"] is False


@pytest.mark.asyncio
async def test_stream_queue_saturation_emits_visible_gap_event():
    release = asyncio.Event()
    publishing = asyncio.Event()
    calls = []

    async def gated_publish(subject, data):
        calls.append((subject, data))
        if len(calls) == 1:
            publishing.set()
            await release.wait()

    task = asyncio.create_task(
        run_command(
            [sys.executable, "-c", "for i in range(50): print('line%d' % i)"],
            timeout=1,
            stream_publish=gated_publish,
            stream_log_topic="bk.stream",
            execution_id="exec-gap",
            stream_queue_size=2,
            stream_batch_size=1,
            stream_flush_timeout=1,
        )
    )
    await asyncio.wait_for(publishing.wait(), timeout=1)
    await asyncio.sleep(0.05)
    release.set()
    code, output, meta = await task

    assert code == 0
    assert "line49" in output
    events = [json.loads(data.decode("utf-8")) for _, data in calls]
    gap_events = [event for event in events if event.get("type") == "gap"]
    assert gap_events
    assert gap_events[0]["dropped_lines"] == meta["stream_lines_dropped"]
    assert "实时日志缺口" in gap_events[0]["line"]
    assert meta["stream_lines_dropped"] > 0


@pytest.mark.asyncio
async def test_run_command_cancellation_terminates_subprocess(monkeypatch):
    read_started = asyncio.Event()
    never_finishes = asyncio.Event()
    killed = []

    class BlockingStdout:
        async def read(self, _size):
            read_started.set()
            await never_finishes.wait()

    class FakeProcess:
        stdout = BlockingStdout()
        pid = 4242
        returncode = None

        def kill(self):
            killed.append("kill")
            self.returncode = -9

        async def wait(self):
            self.returncode = -9
            return self.returncode

    process = FakeProcess()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(runner_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(runner_module.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    task = asyncio.create_task(
        run_command(
            ["fake-command"],
            timeout=10,
            stream_publish=FakePublisher().publish,
            stream_log_topic="bk.stream",
            execution_id="exec-cancel",
        )
    )
    await asyncio.wait_for(read_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert killed
    assert process.returncode == -9
