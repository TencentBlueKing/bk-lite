package ssh

import (
	"encoding/json"
	"errors"
	"testing"
)

type publishedEvent struct {
	topic   string
	payload []byte
}

type stubPublisher struct {
	events []publishedEvent
	err    error
}

func (p *stubPublisher) Publish(topic string, payload []byte) error {
	p.events = append(p.events, publishedEvent{topic: topic, payload: append([]byte(nil), payload...)})
	return p.err
}

func TestStreamLogWriterPublishesCompleteLinesAndFlushesTail(t *testing.T) {
	publisher := &stubPublisher{}
	writer := newStreamLogWriter(publisher, "ssh.stream.instance-1", "exec-1", "stdout")

	if n, err := writer.Write([]byte("line-1\nline")); err != nil || n != len("line-1\nline") {
		t.Fatalf("unexpected first write result: n=%d err=%v", n, err)
	}
	if len(publisher.events) != 1 {
		t.Fatalf("expected first complete line to be published, got %d events", len(publisher.events))
	}

	if n, err := writer.Write([]byte("-2\n\n")); err != nil || n != len("-2\n\n") {
		t.Fatalf("unexpected second write result: n=%d err=%v", n, err)
	}
	writer.Flush()

	if len(publisher.events) != 2 {
		t.Fatalf("expected two published lines, got %d", len(publisher.events))
	}

	assertEvent := func(index int, wantTopic, wantExecutionID, wantStream, wantLine string) {
		t.Helper()
		event := publisher.events[index]
		if event.topic != wantTopic {
			t.Fatalf("event %d topic = %q, want %q", index, event.topic, wantTopic)
		}

		var payload streamEvent
		if err := json.Unmarshal(event.payload, &payload); err != nil {
			t.Fatalf("failed to decode event %d: %v", index, err)
		}
		if payload.ExecutionID != wantExecutionID || payload.Stream != wantStream || payload.Line != wantLine {
			t.Fatalf("unexpected event %d payload: %+v", index, payload)
		}
		if payload.Timestamp == "" {
			t.Fatalf("expected timestamp on event %d", index)
		}
	}

	assertEvent(0, "ssh.stream.instance-1", "exec-1", "stdout", "line-1")
	assertEvent(1, "ssh.stream.instance-1", "exec-1", "stdout", "line-2")
}

func TestStreamLogWriterSkipsEmptyLinesAndPublishErrors(t *testing.T) {
	publisher := &stubPublisher{err: errors.New("nats unavailable")}
	writer := newStreamLogWriter(publisher, "ssh.stream.instance-1", "exec-1", "stderr")

	if _, err := writer.Write([]byte("warn\n\n")); err != nil {
		t.Fatalf("write should ignore publish errors, got %v", err)
	}
	writer.Flush()

	if len(publisher.events) != 1 {
		t.Fatalf("expected one publish attempt for the non-empty line, got %d", len(publisher.events))
	}

	var payload streamEvent
	if err := json.Unmarshal(publisher.events[0].payload, &payload); err != nil {
		t.Fatalf("failed to decode payload: %v", err)
	}
	if payload.Stream != "stderr" {
		t.Fatalf("unexpected stream: %+v", payload)
	}
}

func TestStreamLogWriterHandlesNoopPaths(t *testing.T) {
	t.Run("empty write returns without publishing", func(t *testing.T) {
		publisher := &stubPublisher{}
		writer := newStreamLogWriter(publisher, "ssh.stream.instance-1", "exec-1", "stdout")

		if n, err := writer.Write(nil); err != nil || n != 0 {
			t.Fatalf("unexpected empty write result: n=%d err=%v", n, err)
		}
		if len(publisher.events) != 0 {
			t.Fatalf("expected no events for empty write, got %d", len(publisher.events))
		}
		writer.Flush()
	})

	t.Run("flush with empty buffer is a no-op", func(t *testing.T) {
		publisher := &stubPublisher{}
		writer := newStreamLogWriter(publisher, "ssh.stream.instance-1", "exec-1", "stdout")
		writer.Flush()
		if len(publisher.events) != 0 {
			t.Fatalf("expected no events for empty flush, got %d", len(publisher.events))
		}
	})

	t.Run("publish skips missing topic and empty lines", func(t *testing.T) {
		publisher := &stubPublisher{}
		writer := newStreamLogWriter(publisher, "", "exec-1", "stdout")
		writer.publish("line")
		writer.publish("")
		if len(publisher.events) != 0 {
			t.Fatalf("expected no events when topic or line is invalid, got %d", len(publisher.events))
		}
	})
}
