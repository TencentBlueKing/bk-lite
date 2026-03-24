package local

import (
	"runtime"
	"strings"
	"testing"
	"time"

	"nats-executor/utils"
)

func TestExecute(t *testing.T) {
	req := ExecuteRequest{
		Command:        "echo 'test'",
		ExecuteTimeout: 5,
	}
	instanceId := "test-instance"
	response := Execute(req, instanceId)

	if !response.Success {
		t.Errorf("Execute failed: %s", response.Error)
	}
	t.Logf("Output: %s", response.Output)
}

// 测试默认 shell（sh）
func TestExecuteDefaultShell(t *testing.T) {
	req := ExecuteRequest{
		Command:        "echo 'default shell test'",
		ExecuteTimeout: 5,
		// 不指定 Shell，应该默认使用 sh
	}
	response := Execute(req, "test-default-shell")

	if !response.Success {
		t.Errorf("Default shell execute failed: %s", response.Error)
	}
	t.Logf("Output: %s", response.Output)
}

// 测试 bash
func TestExecuteBash(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Skipping bash test on Windows")
	}

	req := ExecuteRequest{
		Command:        "echo 'bash test'",
		ExecuteTimeout: 5,
		Shell:          "bash",
	}
	response := Execute(req, "test-bash")

	if !response.Success {
		t.Errorf("Bash execute failed: %s", response.Error)
	}
	t.Logf("Output: %s", response.Output)
}

// 测试 Windows bat/cmd
func TestExecuteBat(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping bat test on non-Windows")
	}

	req := ExecuteRequest{
		Command:        "echo bat test",
		ExecuteTimeout: 5,
		Shell:          "bat",
	}
	response := Execute(req, "test-bat")

	if !response.Success {
		t.Errorf("Bat execute failed: %s", response.Error)
	}
	t.Logf("Output: %s", response.Output)
}

// 测试 PowerShell
func TestExecutePowerShell(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping PowerShell test on non-Windows")
	}

	req := ExecuteRequest{
		Command:        "Write-Output 'powershell test'",
		ExecuteTimeout: 5,
		Shell:          "powershell",
	}
	response := Execute(req, "test-powershell")

	if !response.Success {
		t.Errorf("PowerShell execute failed: %s", response.Error)
	}
	t.Logf("Output: %s", response.Output)
}

// 测试超时
func TestExecuteTimeout(t *testing.T) {
	req := ExecuteRequest{
		Command:        "sleep 10",
		ExecuteTimeout: 2,
		Shell:          "sh",
	}
	response := Execute(req, "test-timeout")

	if response.Success {
		t.Error("Expected timeout but command succeeded")
	}
	t.Logf("Error: %s", response.Error)
}

func TestExecuteFailureIncludesExitCodeAndOutput(t *testing.T) {
	req := ExecuteRequest{
		Command:        "printf 'boom'; exit 7",
		ExecuteTimeout: 5,
		Shell:          "sh",
	}

	response := Execute(req, "test-failure")

	if response.Success {
		t.Fatal("expected command to fail")
	}

	if !strings.Contains(response.Error, "exit code 7") {
		t.Fatalf("expected exit code in error, got: %s", response.Error)
	}

	if !strings.Contains(response.Output, "boom") {
		t.Fatalf("expected command output to be preserved, got: %q", response.Output)
	}
}

func TestExecuteUsesCustomShellBinary(t *testing.T) {
	req := ExecuteRequest{
		Command:        "printf custom-shell",
		ExecuteTimeout: 5,
		Shell:          "/bin/sh",
	}

	response := Execute(req, "test-custom-shell")
	if response.Success {
		t.Fatalf("expected unsupported custom shell to be rejected: %+v", response)
	}

	if response.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected response code: %+v", response)
	}

	if !strings.Contains(response.Error, "unsupported shell") {
		t.Fatalf("unexpected error: %+v", response)
	}
}

func TestExecuteRejectsEmptyCommand(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "   ",
		ExecuteTimeout: 5,
		Shell:          "sh",
	}, "test-empty-command")

	if response.Success {
		t.Fatal("expected empty command to be rejected")
	}
	if response.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected response: %+v", response)
	}
	if !strings.Contains(response.Error, "command is required") {
		t.Fatalf("unexpected error: %+v", response)
	}
}

func TestExecuteRejectsNonPositiveTimeout(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "echo hi",
		ExecuteTimeout: 0,
		Shell:          "sh",
	}, "test-invalid-timeout")

	if response.Success {
		t.Fatal("expected non-positive timeout to be rejected")
	}
	if response.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected response: %+v", response)
	}
	if !strings.Contains(response.Error, "execute timeout must be greater than 0") {
		t.Fatalf("unexpected error: %+v", response)
	}
}

func TestContains(t *testing.T) {
	if !contains("prefix-scp-suffix", "scp") {
		t.Fatal("expected substring to be found")
	}

	if contains("prefix-suffix", "scp") {
		t.Fatal("did not expect missing substring to be found")
	}
}

func BenchmarkContains(b *testing.B) {
	input := strings.Repeat("abcdefghij", 128) + "sshpass"
	b.ReportAllocs()
	for b.Loop() {
		if !contains(input, "sshpass") {
			b.Fatal("expected substring")
		}
	}
}

func TestExecuteTimeoutReturnsQuickly(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Skipping timing-sensitive shell test on Windows")
	}

	start := time.Now()
	response := Execute(ExecuteRequest{
		Command:        "sleep 2",
		ExecuteTimeout: 1,
		Shell:          "sh",
	}, "test-timeout-fast")
	elapsed := time.Since(start)

	if response.Success {
		t.Fatal("expected timeout response")
	}

	if elapsed > 1500*time.Millisecond {
		t.Fatalf("timeout handling took too long: %v", elapsed)
	}
}
