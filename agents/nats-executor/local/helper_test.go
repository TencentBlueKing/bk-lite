package local

import (
	"strconv"
	"strings"
	"testing"

	"nats-executor/utils"

	"github.com/nats-io/nats.go"
)

func TestLocalHelpersSupportBDDScenarios(t *testing.T) {
	t.Run("happy path keeps short output intact", func(t *testing.T) {
		if got := string(sampleBytes([]byte("hello"), 10)); got != "hello" {
			t.Fatalf("unexpected sample bytes: %q", got)
		}
		if got := truncateForLog("hello", 10); got != "hello" {
			t.Fatalf("unexpected truncated log: %q", got)
		}
		if got := formatSCPLogContext("scp upload"); got != "scp upload" {
			t.Fatalf("unexpected log context: %q", got)
		}
	})

	t.Run("corner case truncates long samples and excerpts", func(t *testing.T) {
		if got := string(sampleBytes([]byte("abcdef"), 3)); got != "abc" {
			t.Fatalf("unexpected sample bytes: %q", got)
		}
		if got := truncateForLog("abcdef", 3); got != "abc..." {
			t.Fatalf("unexpected truncated log: %q", got)
		}
		if got := outputExcerpt("line1\nline2\rline3"); !strings.Contains(got, "line1 | line2") {
			t.Fatalf("unexpected output excerpt: %q", got)
		}
	})

	t.Run("corner case uses default transfer context", func(t *testing.T) {
		if got := formatSCPLogContext("   "); got != "transfer=unknown" {
			t.Fatalf("unexpected default log context: %q", got)
		}
	})
}

func TestSCPStreamLogWriterFlushesBufferedTail(t *testing.T) {
	writer := newSCPStreamLogWriter("instance-1", "stderr", ShellTypeSh, "scp upload")

	written, err := writer.Write([]byte("first line\nsecond"))
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if written != len("first line\nsecond") {
		t.Fatalf("unexpected written size: %d", written)
	}
	if got := writer.buffer.String(); got != "second" {
		t.Fatalf("expected tail to remain buffered, got %q", got)
	}

	writer.Flush()
	if writer.buffer.Len() != 0 {
		t.Fatalf("expected flush to clear buffer, got %q", writer.buffer.String())
	}
}

func TestFormatCapturedExecuteOutputIncludesStdoutStderrAndTruncation(t *testing.T) {
	snapshot := utils.OutputSnapshot{
		Stdout:        []byte("stdout payload"),
		Stderr:        []byte("stderr payload"),
		Limit:         128,
		Truncated:     true,
		StdoutDropped: 16,
		StderrDropped: 8,
		TotalWritten:  128,
	}

	got := formatCapturedExecuteOutput(snapshot, ShellTypeSh)
	for _, want := range []string{"stdout payload", "stderr payload", "output truncated"} {
		if !strings.Contains(got, want) {
			t.Fatalf("expected formatted output to contain %q, got %q", want, got)
		}
	}
}

func TestLooksLikeUTF16LEAndSCPFailureAnalysisCornerCases(t *testing.T) {
	if !looksLikeUTF16LE([]byte{'h', 0x00, 'i', 0x00}) {
		t.Fatal("expected utf16-like payload to be detected")
	}
	if looksLikeUTF16LE([]byte("plain text")) {
		t.Fatal("did not expect utf8 payload to look like utf16le")
	}

	testCases := []struct {
		name     string
		output   string
		exitCode int
	}{
		{name: "permission denied", output: "Permission denied", exitCode: 1},
		{name: "connection refused", output: "Connection refused", exitCode: 1},
		{name: "path missing", output: "No such file or directory", exitCode: 1},
		{name: "host key changed", output: "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED", exitCode: 6},
		{name: "sshpass missing", output: "sshpass: command not found", exitCode: 5},
	}

	for _, tt := range testCases {
		t.Run(tt.name, func(t *testing.T) {
			analyzeSCPFailure("instance-1", tt.output, tt.exitCode)
		})
	}

	for _, exitCode := range []int{2, 3, 4, 5, 6, 9} {
		t.Run("exit-code-branch-"+strconv.Itoa(exitCode), func(t *testing.T) {
			analyzeSCPFailure("instance-1", "ssh: connect to host demo port 22: Connection timed out", exitCode)
		})
	}
}

func TestLocalCrossPlatformHelperScenarios(t *testing.T) {
	if got, strategy := decodeExecuteOutputWithStrategyForOS([]byte("plain text"), ShellTypeCmd, "windows"); got != "plain text" || strategy != "utf8" {
		t.Fatalf("unexpected utf8 strategy: output=%q strategy=%q", got, strategy)
	}

	gbkOutput := []byte{0xd6, 0xd0, 0xce, 0xc4, 0xca, 0xe4, 0xb3, 0xf6}
	if got, strategy := decodeExecuteOutputWithStrategyForOS(gbkOutput, ShellTypeCmd, "windows"); got != "中文输出" || strategy != "gbk" {
		t.Fatalf("unexpected gbk strategy: output=%q strategy=%q", got, strategy)
	}

	if got := wrapPowerShellCommandForOS("Write-Output test", "windows"); !strings.Contains(got, "[Console]::OutputEncoding") {
		t.Fatalf("expected windows powershell wrapper, got %q", got)
	}
	if got := wrapPowerShellCommandForOS("echo test", "linux"); got != "echo test" {
		t.Fatalf("unexpected non-windows powershell wrapper: %q", got)
	}

	if got := wrapCmdCommandForOS("echo test", "windows"); !strings.HasPrefix(got, "chcp 65001 >nul && ") {
		t.Fatalf("expected windows cmd wrapper, got %q", got)
	}
	if got := wrapCmdCommandForOS("echo test", "linux"); got != "echo test" {
		t.Fatalf("unexpected non-windows cmd wrapper: %q", got)
	}

	msg := natsInboundMsg{Msg: &nats.Msg{Data: []byte("payload")}}
	if got := string(msg.Payload()); got != "payload" {
		t.Fatalf("unexpected payload: %q", got)
	}

	writer := newSCPStreamLogWriter("instance-1", "stdout", ShellTypeSh, "ctx")
	writer.logLine("   \n")
}
