package utils

import "fmt"

const CommandOutputLimitBytes = 1024 * 1024

type BoundedBuffer struct {
	limit     int
	buf       []byte
	total     int64
	truncated bool
}

func NewBoundedBuffer(limit int) *BoundedBuffer {
	if limit <= 0 {
		limit = CommandOutputLimitBytes
	}
	return &BoundedBuffer{limit: limit}
}

func (b *BoundedBuffer) Write(p []byte) (int, error) {
	b.total += int64(len(p))
	if len(p) >= b.limit {
		b.buf = append(b.buf[:0], p[len(p)-b.limit:]...)
		b.truncated = true
		return len(p), nil
	}

	overflow := len(b.buf) + len(p) - b.limit
	if overflow > 0 {
		copy(b.buf, b.buf[overflow:])
		b.buf = b.buf[:len(b.buf)-overflow]
		b.truncated = true
	}
	b.buf = append(b.buf, p...)
	return len(p), nil
}

func (b *BoundedBuffer) Bytes() []byte {
	if !b.truncated {
		return append([]byte(nil), b.buf...)
	}

	prefix := []byte(fmt.Sprintf("[output truncated: kept last %d of %d bytes]\n", len(b.buf), b.total))
	out := make([]byte, 0, len(prefix)+len(b.buf))
	out = append(out, prefix...)
	out = append(out, b.buf...)
	return out
}

func (b *BoundedBuffer) String() string {
	return string(b.Bytes())
}

func (b *BoundedBuffer) Len() int {
	return len(b.buf)
}

func (b *BoundedBuffer) TotalLen() int64 {
	return b.total
}

func (b *BoundedBuffer) Truncated() bool {
	return b.truncated
}
