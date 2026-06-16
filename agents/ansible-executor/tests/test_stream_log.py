import json
import sys

import pytest
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


# ---------------------------------------------------------------------------
# Integration tests: run_command streams stdout line-by-line via callback.
# ---------------------------------------------------------------------------


class FakePublisher:
    def __init__(self, fail: bool = False):
        self.calls: list[tuple[str, bytes]] = []
        self.fail = fail

    async def publish(self, subject: str, data: bytes) -> None:
        self.calls.append((subject, data))
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
    assert [e["line"] for e in events] == ["line0", "line1", "line2"]
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
    code, output, _ = await run_command(
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
