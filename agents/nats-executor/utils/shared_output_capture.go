package utils

import (
	"bytes"
	"io"
	"sync"
	"unicode/utf8"
)

const CommandOutputLimitBytes = 1024 * 1024

type OutputSnapshot struct {
	Stdout        []byte
	Stderr        []byte
	Limit         int
	TotalWritten  int64
	StdoutDropped int64
	StderrDropped int64
	Truncated     bool
}

type SharedOutputCapture struct {
	mu            sync.Mutex
	limit         int
	used          int
	stdout        bytes.Buffer
	stderr        bytes.Buffer
	totalWritten  int64
	stdoutDropped int64
	stderrDropped int64
	truncated     bool
}

type captureStream string

const (
	captureStdout captureStream = "stdout"
	captureStderr captureStream = "stderr"
)

func NewSharedOutputCapture(limit int) *SharedOutputCapture {
	if limit <= 0 {
		limit = CommandOutputLimitBytes
	}

	return &SharedOutputCapture{limit: limit}
}

func (c *SharedOutputCapture) StdoutWriter() io.Writer {
	return sharedOutputWriter{capture: c, stream: captureStdout}
}

func (c *SharedOutputCapture) StderrWriter() io.Writer {
	return sharedOutputWriter{capture: c, stream: captureStderr}
}

func (c *SharedOutputCapture) Snapshot() OutputSnapshot {
	c.mu.Lock()
	defer c.mu.Unlock()

	return OutputSnapshot{
		Stdout:        append([]byte(nil), c.stdout.Bytes()...),
		Stderr:        append([]byte(nil), c.stderr.Bytes()...),
		Limit:         c.limit,
		TotalWritten:  c.totalWritten,
		StdoutDropped: c.stdoutDropped,
		StderrDropped: c.stderrDropped,
		Truncated:     c.truncated,
	}
}

type sharedOutputWriter struct {
	capture *SharedOutputCapture
	stream  captureStream
}

func (w sharedOutputWriter) Write(p []byte) (int, error) {
	return w.capture.write(w.stream, p)
}

func (c *SharedOutputCapture) write(stream captureStream, p []byte) (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.totalWritten += int64(len(p))
	remaining := c.limit - c.used
	if remaining < 0 {
		remaining = 0
	}

	kept := len(p)
	if kept > remaining {
		kept = remaining
	}

	if kept > 0 {
		switch stream {
		case captureStdout:
			_, _ = c.stdout.Write(p[:kept])
		case captureStderr:
			_, _ = c.stderr.Write(p[:kept])
		}
		c.used += kept
	}

	dropped := len(p) - kept
	if dropped > 0 {
		c.truncated = true
		switch stream {
		case captureStdout:
			c.stdoutDropped += int64(dropped)
		case captureStderr:
			c.stderrDropped += int64(dropped)
		}
	}

	return len(p), nil
}

const truncatedOutputNotice = "\n...[output truncated]"

func FormatCapturedOutput(stdout, stderr string, snapshot OutputSnapshot) string {
	output := stdout + stderr
	if !snapshot.Truncated {
		return output
	}

	return appendTruncationNotice(output, truncatedOutputNotice, snapshot.Limit)
}

func appendTruncationNotice(output, notice string, limit int) string {
	if limit <= 0 {
		return notice
	}
	if len(notice) >= limit {
		return truncateUTF8ToByteLimit(notice, limit)
	}

	available := limit - len(notice)
	trimmed := truncateUTF8ToByteLimit(output, available)
	return trimmed + notice
}

func truncateUTF8ToByteLimit(value string, limit int) string {
	if limit <= 0 {
		return ""
	}
	if len(value) <= limit {
		return value
	}

	end := limit
	for end > 0 && !utf8.ValidString(value[:end]) {
		end--
	}
	if end <= 0 {
		return ""
	}
	return value[:end]
}
