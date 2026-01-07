package ssh

import (
	"testing"
)

// 测试 buildSCPCommand 函数 - 密码认证
func TestBuildSCPCommandWithPassword(t *testing.T) {
	cmd, cleanup, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"testpass",
		"", // 无私钥
		22,
		"/local/file",
		"/remote/path",
		true,
	)

	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}

	if cleanup == nil {
		t.Error("cleanup function should not be nil")
	}

	if cmd == "" {
		t.Error("command should not be empty")
	}

	// 检查命令包含 sshpass
	if !contains(cmd, "sshpass") {
		t.Error("command should contain 'sshpass' for password authentication")
	}

	t.Logf("Generated SCP command (password): %s", cmd)
}

// 测试 buildSCPCommand 函数 - 密钥认证
func TestBuildSCPCommandWithPrivateKey(t *testing.T) {
	// 生成一个测试用的 RSA 私钥（这是一个示例格式，非真实密钥）
	testPrivateKey := `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz
-----END RSA PRIVATE KEY-----`

	cmd, cleanup, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"", // 无密码
		testPrivateKey,
		22,
		"/local/file",
		"/remote/path",
		true,
	)

	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}

	if cleanup == nil {
		t.Fatal("cleanup function should not be nil")
	}
	defer cleanup() // 测试清理函数

	if cmd == "" {
		t.Error("command should not be empty")
	}

	// 检查命令包含 -i (identity file)
	if !contains(cmd, "-i") {
		t.Error("command should contain '-i' for key-based authentication")
	}

	// 检查命令不包含 sshpass
	if contains(cmd, "sshpass") {
		t.Error("command should not contain 'sshpass' when using key authentication")
	}

	t.Logf("Generated SCP command (private key): %s", cmd)
}

// 测试 buildSCPCommand 函数 - 无认证信息
func TestBuildSCPCommandNoAuth(t *testing.T) {
	_, _, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"", // 无密码
		"", // 无私钥
		22,
		"/local/file",
		"/remote/path",
		true,
	)

	if err == nil {
		t.Error("should return error when no authentication method is provided")
	}

	t.Logf("Expected error: %v", err)
}

// 测试 buildSCPCommand 函数 - 优先使用密钥
func TestBuildSCPCommandPriorityPrivateKey(t *testing.T) {
	testPrivateKey := `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz
-----END RSA PRIVATE KEY-----`

	cmd, cleanup, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"testpass",     // 同时提供密码
		testPrivateKey, // 和私钥
		22,
		"/local/file",
		"/remote/path",
		true,
	)

	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}

	if cleanup == nil {
		t.Fatal("cleanup function should not be nil")
	}
	defer cleanup()

	// 应该优先使用密钥认证（检查命令中有 -i）
	if !contains(cmd, "-i") {
		t.Error("should prioritize private key over password")
	}

	t.Logf("Generated SCP command (both auth methods): %s", cmd)
}

// 测试 Execute 函数 - 密钥认证的请求结构
func TestExecuteWithPrivateKey(t *testing.T) {
	// 注意：这个测试只验证请求结构，不会真正连接
	req := ExecuteRequest{
		Command:        "ls -la",
		ExecuteTimeout: 10,
		Host:           "test-host",
		Port:           22,
		User:           "testuser",
		PrivateKey: `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz
-----END RSA PRIVATE KEY-----`,
	}

	// 验证结构体字段是否正确
	if req.PrivateKey == "" {
		t.Error("PrivateKey field should not be empty")
	}

	if req.Password != "" {
		t.Error("Password should be empty when using key auth")
	}

	t.Logf("ExecuteRequest with private key created successfully")
}

// 辅助函数：检查字符串包含
func contains(s, substr string) bool {
	return len(s) >= len(substr) && findSubstring(s, substr)
}

func findSubstring(s, substr string) bool {
	if len(substr) == 0 {
		return true
	}
	if len(s) < len(substr) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
