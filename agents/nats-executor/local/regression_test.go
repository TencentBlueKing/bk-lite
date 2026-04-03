package local

import (
	"encoding/json"
	"strings"
	"testing"

	"nats-executor/utils"
)

func TestRegressionLocalExecuteOutputDecoding(t *testing.T) {
	wrappedCmd := wrapCmdCommand("ipconfig")
	if !strings.Contains(wrappedCmd, "chcp 65001") {
		t.Fatalf("expected cmd command wrapper to switch code page, got %q", wrappedCmd)
	}

	wrapped := wrapPowerShellCommand("Write-Output test")
	if !strings.Contains(wrapped, "[Console]::OutputEncoding") {
		t.Fatalf("expected PowerShell command wrapper to force UTF-8 output, got %q", wrapped)
	}

	utf16Output := []byte{0xff, 0xfe, 0x2d, 0x4e, 0x87, 0x65, 0x93, 0x8f, 0xfa, 0x51}
	if got := decodeExecuteOutput(utf16Output, ShellTypePowerShell); got != "中文输出" {
		t.Fatalf("expected UTF-16LE output to decode, got %q", got)
	}

	gbkOutput := []byte{0xd6, 0xd0, 0xce, 0xc4, 0xca, 0xe4, 0xb3, 0xf6}
	if got := decodeExecuteOutput(gbkOutput, ShellTypeCmd); got != "中文输出" {
		t.Fatalf("expected GBK output to decode, got %q", got)
	}

	plainOutput := []byte("plain text")
	if got := decodeExecuteOutput(plainOutput, ShellTypeSh); got != "plain text" {
		t.Fatalf("expected non-Windows output to remain unchanged, got %q", got)
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
