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

func TestSCPFailureAdviceClassifiesCommonFailureModes(t *testing.T) {
	testCases := []struct {
		name      string
		output    string
		exitCode  int
		timedOut  bool
		wantCause string
		wantNext  string
	}{
		{
			name:      "host key verification",
			output:    "Host key verification failed",
			exitCode:  1,
			wantCause: "host_key_problem",
			wantNext:  "check_target_host_key_or_known_hosts",
		},
		{
			name:      "auth failure",
			output:    "Permission denied, please try again.",
			exitCode:  5,
			wantCause: "auth_failure",
			wantNext:  "check_password_private_key_or_passphrase",
		},
		{
			name:      "network or dns",
			output:    "ssh: connect to host demo port 22: Connection timed out",
			exitCode:  1,
			wantCause: "network_or_dns",
			wantNext:  "check_host_reachability_port_and_firewall",
		},
		{
			name:      "path not found",
			output:    "scp: /tmp/demo.txt: No such file or directory",
			exitCode:  1,
			wantCause: "path_not_found",
			wantNext:  "check_source_and_target_path",
		},
		{
			name:      "missing sshpass",
			output:    "sshpass: command not found",
			exitCode:  127,
			wantCause: "missing_sshpass",
			wantNext:  "check_executor_dependencies",
		},
		{
			name:      "timed out without recognizable output",
			output:    "",
			exitCode:  0,
			timedOut:  true,
			wantCause: "transfer_timeout",
			wantNext:  "check_network_speed_target_response_and_interactive_prompts",
		},
		{
			name:      "unknown failure",
			output:    "unexpected stderr",
			exitCode:  9,
			wantCause: "unknown",
			wantNext:  "check_debug_stream_and_full_output",
		},
	}

	for _, tt := range testCases {
		t.Run(tt.name, func(t *testing.T) {
			cause, next := scpFailureAdvice(tt.output, tt.exitCode, tt.timedOut)
			if cause != tt.wantCause || next != tt.wantNext {
				t.Fatalf("scpFailureAdvice(%q, %d, %v) = (%q, %q), want (%q, %q)", tt.output, tt.exitCode, tt.timedOut, cause, next, tt.wantCause, tt.wantNext)
			}
		})
	}
}

func TestLocalExecuteStartFailureAndMalformedResponsePaths(t *testing.T) {
	if runtime.GOOS != "windows" {
		response := Execute(ExecuteRequest{
			Command:        "echo should-fail-to-start",
			ExecuteTimeout: 3,
			Shell:          ShellTypePwsh,
		}, "instance-start-failure")
		if response.Success || response.Code != utils.ErrorCodeExecutionFailure {
			t.Fatalf("unexpected response: %+v", response)
		}
		if !strings.Contains(response.Error, "failed to start command") {
			t.Fatalf("unexpected error: %+v", response)
		}
	}

	if ok := respondLocalExecuteMessage(stubResponseMsg{}, []byte("not-json"), "instance-1"); !ok {
		t.Fatal("expected malformed payload path to emit explicit error response")
	}
}
