package local

import (
	"runtime"
	"testing"
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
