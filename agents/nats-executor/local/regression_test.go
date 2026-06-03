package local

import (
	"encoding/json"
	"fmt"
	"runtime"
	"strings"
	"testing"

	"nats-executor/utils"
)

func TestRegressionLocalExecuteOutputDecoding(t *testing.T) {
	wrappedCmd := wrapCmdCommand("ipconfig")
	if runtime.GOOS == "windows" && !strings.Contains(wrappedCmd, "chcp 65001") {
		t.Fatalf("expected cmd command wrapper to switch code page, got %q", wrappedCmd)
	}

	wrapped := wrapPowerShellCommand("Write-Output test")
	if runtime.GOOS == "windows" && !strings.Contains(wrapped, "[Console]::OutputEncoding") {
		t.Fatalf("expected PowerShell command wrapper to force UTF-8 output, got %q", wrapped)
	}

	utf16Output := []byte{0xff, 0xfe, 0x2d, 0x4e, 0x87, 0x65, 0x93, 0x8f, 0xfa, 0x51}
	if got := decodeExecuteOutput(utf16Output, ShellTypePowerShell); got != "中文输出" {
		t.Fatalf("expected UTF-16LE output to decode, got %q", got)
	}

	gbkOutput := []byte{0xd6, 0xd0, 0xce, 0xc4, 0xca, 0xe4, 0xb3, 0xf6}
	if got := decodeExecuteOutput(gbkOutput, ShellTypeCmd); runtime.GOOS == "windows" && got != "中文输出" {
		t.Fatalf("expected GBK output to decode, got %q", got)
	}

	plainOutput := []byte("plain text")
	if got := decodeExecuteOutput(plainOutput, ShellTypeSh); got != "plain text" {
		t.Fatalf("expected non-Windows output to remain unchanged, got %q", got)
	}
}

func TestRegressionLocalExecuteOutputDecodingStrategy(t *testing.T) {
	utf16Output := []byte{0xff, 0xfe, 0x2d, 0x4e, 0x87, 0x65, 0x93, 0x8f, 0xfa, 0x51}
	if got, strategy := decodeExecuteOutputWithStrategy(utf16Output, ShellTypeCmd); got != "中文输出" || strategy != "utf16le" {
		t.Fatalf("expected UTF-16LE strategy, got output=%q strategy=%q", got, strategy)
	}

	gbkOutput := []byte{0xd6, 0xd0, 0xce, 0xc4, 0xca, 0xe4, 0xb3, 0xf6}
	if got, strategy := decodeExecuteOutputWithStrategy(gbkOutput, ShellTypeCmd); got != "中文输出" || strategy != "gbk" {
		if runtime.GOOS == "windows" || strategy != "raw" {
			t.Fatalf("expected GBK strategy, got output=%q strategy=%q", got, strategy)
		}
	}

	utf8Output := []byte("plain text")
	if got, strategy := decodeExecuteOutputWithStrategy(utf8Output, ShellTypeCmd); got != "plain text" || strategy != "utf8" {
		t.Fatalf("expected UTF-8 strategy, got output=%q strategy=%q", got, strategy)
	}
}

func TestRegressionLocalHandlerTimeoutContract(t *testing.T) {
	payload := []byte(`{"args":[{"command":"sleep 2","execute_timeout":1,"shell":"sh"}],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected timeout response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success {
		t.Fatalf("expected timeout failure, got %+v", result)
	}
	if result.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected code: %+v", result)
	}
	if !strings.Contains(result.Error, "timed out") {
		t.Fatalf("unexpected error: %+v", result)
	}
}

func TestRegressionLocalHandlerMalformedPayloadContract(t *testing.T) {
	response, ok := handleDownloadToLocalMessage([]byte(`{"args":[{"bucket_name":1}],"kwargs":{}}`), "instance-1", nil)
	if !ok {
		t.Fatal("expected explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected response: %+v", result)
	}
	if !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected error: %+v", result)
	}
}

func TestRegressionLocalExecuteCapsCapturedOutput(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "yes 1234567890 | head -c 1500000",
		ExecuteTimeout: 5,
		Shell:          ShellTypeSh,
	}, "instance-1")

	if !response.Success {
		t.Fatalf("expected command success, got %+v", response)
	}
	if len(response.Output) > utils.CommandOutputLimitBytes {
		t.Fatalf("expected capped output, got %d bytes", len(response.Output))
	}
	if !strings.Contains(response.Output, "output truncated") {
		t.Fatalf("expected truncation marker, got prefix %q", response.Output[:min(len(response.Output), 128)])
	}
}

func TestRegressionLocalExecuteAppliesSharedCapAcrossStdoutAndStderr(t *testing.T) {
	half := utils.CommandOutputLimitBytes / 2
	response := Execute(ExecuteRequest{
		Command:        fmt.Sprintf("python3 -c \"import sys; sys.stdout.write('o'*%d); sys.stderr.write('e'*%d)\"", half+4096, half+4096),
		ExecuteTimeout: 5,
		Shell:          ShellTypeSh,
	}, "instance-1")

	if !response.Success {
		t.Fatalf("expected command success, got %+v", response)
	}
	if len(response.Output) > utils.CommandOutputLimitBytes {
		t.Fatalf("expected shared capped output, got %d bytes", len(response.Output))
	}
	if !strings.Contains(response.Output, "output truncated") {
		t.Fatal("expected truncation marker for shared cap")
	}
	if !strings.Contains(response.Output, strings.Repeat("o", 64)) {
		t.Fatal("expected stdout content to be present")
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
