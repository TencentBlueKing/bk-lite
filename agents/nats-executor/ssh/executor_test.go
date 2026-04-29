package ssh

import (
	"errors"
	"io"
	"nats-executor/local"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	gossh "golang.org/x/crypto/ssh"
	"nats-executor/utils"
)

type stubSSHClient struct {
	newSession func() (sshSession, error)
	close      func() error
}

func (c stubSSHClient) NewSession() (sshSession, error) {
	if c.newSession == nil {
		return nil, nil
	}
	return c.newSession()
}

func (c stubSSHClient) Close() error {
	if c.close == nil {
		return nil
	}
	return c.close()
}

type stubSSHSession struct {
	run    func(cmd string) error
	signal func(sig gossh.Signal) error
	close  func() error
	stdout io.Writer
	stderr io.Writer
}

func (s *stubSSHSession) Run(cmd string) error {
	if s.run == nil {
		return nil
	}
	return s.run(cmd)
}

func (s *stubSSHSession) Signal(sig gossh.Signal) error {
	if s.signal == nil {
		return nil
	}
	return s.signal(sig)
}

func (s *stubSSHSession) Close() error {
	if s.close == nil {
		return nil
	}
	return s.close()
}

func (s *stubSSHSession) SetStdout(w io.Writer) { s.stdout = w }
func (s *stubSSHSession) SetStderr(w io.Writer) { s.stderr = w }

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
		profileModern,
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

	if contains(cmd, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Error("modern profile command should not include legacy ssh-rsa options by default")
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
		profileModern,
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

	if contains(cmd, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Error("modern profile command should not include legacy ssh-rsa options by default")
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
		profileModern,
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
		profileModern,
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

	if req.Command != "ls -la" {
		t.Error("Command should be set correctly")
	}

	if req.ExecuteTimeout != 10 {
		t.Error("ExecuteTimeout should be set correctly")
	}

	if req.Host != "test-host" || req.Port != 22 || req.User != "testuser" {
		t.Error("host/port/user should be set correctly")
	}

	t.Logf("ExecuteRequest with private key created successfully")
}

func TestBuildSCPCommandWithLegacyProfile(t *testing.T) {
	cmd, cleanup, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"testpass",
		"",
		22,
		"/local/file",
		"/remote/path",
		true,
		profileLegacy,
	)

	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}
	defer cleanup()

	if !contains(cmd, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Error("legacy profile should include PubkeyAcceptedAlgorithms=+ssh-rsa")
	}

	if !contains(cmd, "HostKeyAlgorithms=+ssh-rsa") {
		t.Error("legacy profile should include HostKeyAlgorithms=+ssh-rsa")
	}
}

func TestAddLegacySCPOptions(t *testing.T) {
	command := "scp -o StrictHostKeyChecking=no -P 22 -r /tmp/a user@host:/tmp/b"
	updated := addLegacySCPOptions(command)

	if !contains(updated, "HostKeyAlgorithms=+ssh-rsa") {
		t.Error("legacy host key option should be added")
	}

	if !contains(updated, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Error("legacy pubkey option should be added")
	}
}

func TestAddLegacySCPOptionsWithoutPortFlag(t *testing.T) {
	command := "scp -o StrictHostKeyChecking=no -r /tmp/a user@host:/tmp/b"
	updated := addLegacySCPOptions(command)

	if !strings.HasSuffix(updated, " -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Fatalf("expected legacy options appended to end, got: %s", updated)
	}
}

func TestAddLegacySCPOptionsSkipsNonScpCommand(t *testing.T) {
	command := "ssh user@host"
	if updated := addLegacySCPOptions(command); updated != command {
		t.Fatalf("non-scp command should be unchanged: %s", updated)
	}
}

func TestBuildSCPCommandEscapesIntoTemporaryKeyFile(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("TMPDIR", tmpDir)

	testPrivateKey := "-----BEGIN RSA PRIVATE KEY-----\nkey-data\n-----END RSA PRIVATE KEY-----"
	cmd, cleanup, err := buildSCPCommand("testuser", "127.0.0.1", "", testPrivateKey, 2222, "/src", "/dst", true, profileModern)
	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}
	if cleanup == nil {
		t.Fatal("expected cleanup function")
	}

	parts := strings.Split(cmd, " ")
	keyPath := ""
	for i := 0; i < len(parts)-1; i++ {
		if parts[i] == "-i" {
			keyPath = strings.Trim(parts[i+1], "'")
			break
		}
	}
	if keyPath == "" {
		t.Fatalf("failed to extract temp key path from command: %s", cmd)
	}

	data, err := os.ReadFile(keyPath)
	if err != nil {
		t.Fatalf("expected temp key file to exist: %v", err)
	}
	if string(data) != testPrivateKey {
		t.Fatalf("unexpected temp key contents: %q", string(data))
	}

	cleanup()
	if _, err := os.Stat(keyPath); !os.IsNotExist(err) {
		t.Fatalf("expected cleanup to remove temp key file, stat err=%v", err)
	}
}

func TestBuildSCPCommandPasswordPreservesLiteralValue(t *testing.T) {
	password := "pa'ss $(rm -rf /)"
	cmd, cleanup, err := buildSCPCommand("testuser", "192.168.1.100", password, "", 22, "/local/file", "/remote/path", true, profileModern)
	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}
	defer cleanup()

	expectedEscaped := "sshpass -p 'pa'\"'\"'ss $(rm -rf /)'"
	if !strings.Contains(cmd, expectedEscaped) {
		t.Fatalf("password should be shell-escaped, got: %s", cmd)
	}

	if strings.Contains(cmd, "sshpass -p 'pa'ss") {
		t.Fatalf("password should not appear with broken quoting: %s", cmd)
	}
}

func TestBuildSCPCommandQuotesPathsWithSpaces(t *testing.T) {
	cmd, cleanup, err := buildSCPCommand(
		"testuser",
		"192.168.1.100",
		"testpass",
		"",
		22,
		"/tmp/local file.txt",
		"/remote path/target file.txt",
		true,
		profileModern,
	)
	if err != nil {
		t.Fatalf("buildSCPCommand failed: %v", err)
	}
	defer cleanup()

	if !strings.Contains(cmd, " '/tmp/local file.txt' ") {
		t.Fatalf("source path should be shell-quoted, got: %s", cmd)
	}

	if !strings.Contains(cmd, "'testuser@192.168.1.100:/remote path/target file.txt'") {
		t.Fatalf("remote target should be shell-quoted, got: %s", cmd)
	}
}

func TestRedactSensitiveCommand(t *testing.T) {
	command := "sshpass -p 'secret-value' scp -o StrictHostKeyChecking=no -P 22 -r '/tmp/a' 'user@host:/tmp/b'"
	redacted := redactSensitiveCommand(command)

	if strings.Contains(redacted, "secret-value") {
		t.Fatalf("redacted command should not expose password: %s", redacted)
	}

	if !strings.Contains(redacted, "sshpass -p '***'") {
		t.Fatalf("redacted command should mask sshpass password: %s", redacted)
	}
}

func TestShouldRetryWithLegacy(t *testing.T) {
	tests := map[string]bool{
		"Unable to negotiate with 10.0.0.1: no matching host key type found": true,
		"invalid signature algorithm":                                        true,
		"permission denied":                                                  false,
	}

	for input, expected := range tests {
		if got := shouldRetryWithLegacy(input); got != expected {
			t.Fatalf("shouldRetryWithLegacy(%q) = %v, want %v", input, got, expected)
		}
	}
}

func TestCompatibilityProfiles(t *testing.T) {
	modernFlags := scpOptionFlags(profileModern)
	legacyFlags := scpOptionFlags(profileLegacy)

	if strings.Contains(modernFlags, "ssh-rsa") {
		t.Fatalf("modern flags should not include legacy algorithms: %s", modernFlags)
	}
	if !strings.Contains(legacyFlags, "ssh-rsa") {
		t.Fatalf("legacy flags should include ssh-rsa compatibility: %s", legacyFlags)
	}

	modernAlgos := rsaSignerAlgorithmsForProfile(profileModern)
	legacyAlgos := rsaSignerAlgorithmsForProfile(profileLegacy)
	if len(legacyAlgos) <= len(modernAlgos) {
		t.Fatalf("legacy profile should allow at least one extra RSA algorithm")
	}
}

func TestShellQuote(t *testing.T) {
	if got := shellQuote(""); got != "''" {
		t.Fatalf("empty string should be shell quoted safely, got: %s", got)
	}

	input := "path with 'quotes' and spaces"
	want := `'path with '"'"'quotes'"'"' and spaces'`
	if got := shellQuote(input); got != want {
		t.Fatalf("unexpected shellQuote result:\nwant: %s\n got: %s", want, got)
	}
}

func TestShellQuoteRemoteTarget(t *testing.T) {
	got := shellQuoteRemoteTarget("user", "host", "/tmp/dir with space/file.txt")
	want := `'user@host:/tmp/dir with space/file.txt'`
	if got != want {
		t.Fatalf("unexpected remote target quote:\nwant: %s\n got: %s", want, got)
	}
}

func TestRedactSensitiveCommandLeavesOtherCommandsUntouched(t *testing.T) {
	command := "scp -o StrictHostKeyChecking=no -P 22 -r '/tmp/a' 'user@host:/tmp/b'"
	if redacted := redactSensitiveCommand(command); redacted != command {
		t.Fatalf("non-sshpass command should remain unchanged: %s", redacted)
	}
}

func TestExecuteReturnsInvalidRequestCodeWhenNoAuthProvided(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected failure when auth is missing")
	}
	if response.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteRejectsInvalidRequestFieldsBeforeDial(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		t.Fatal("sshDialFn should not be called for invalid requests")
		return nil, nil
	}
	defer func() { sshDialFn = originalDial }()

	tests := []struct {
		name string
		req  ExecuteRequest
		want string
	}{
		{
			name: "missing command",
			req:  ExecuteRequest{ExecuteTimeout: 5, Host: "10.0.0.1", Port: 22, User: "root", Password: "secret"},
			want: "command is required",
		},
		{
			name: "missing host",
			req:  ExecuteRequest{Command: "uptime", ExecuteTimeout: 5, Port: 22, User: "root", Password: "secret"},
			want: "host is required",
		},
		{
			name: "missing user",
			req:  ExecuteRequest{Command: "uptime", ExecuteTimeout: 5, Host: "10.0.0.1", Port: 22, Password: "secret"},
			want: "user is required",
		},
		{
			name: "invalid port",
			req:  ExecuteRequest{Command: "uptime", ExecuteTimeout: 5, Host: "10.0.0.1", Port: 0, User: "root", Password: "secret"},
			want: "port must be greater than 0",
		},
		{
			name: "invalid timeout",
			req:  ExecuteRequest{Command: "uptime", ExecuteTimeout: 0, Host: "10.0.0.1", Port: 22, User: "root", Password: "secret"},
			want: "execute timeout must be greater than 0",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			response := Execute(tt.req, "instance-1")
			if response.Success {
				t.Fatalf("expected invalid request failure: %+v", response)
			}
			if response.Code != utils.ErrorCodeInvalidRequest {
				t.Fatalf("unexpected code: %+v", response)
			}
			if !strings.Contains(response.Error, tt.want) {
				t.Fatalf("unexpected error: %+v", response)
			}
		})
	}
}

func TestExecuteReturnsInvalidRequestCodeWhenPrivateKeyParseFails(t *testing.T) {
	originalParse := parsePrivateKeyFn
	parsePrivateKeyFn = func(pemBytes []byte) (gossh.Signer, error) {
		return nil, errors.New("invalid key")
	}
	defer func() { parsePrivateKeyFn = originalParse }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		PrivateKey:     "bad-key",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected parse failure")
	}
	if response.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteReturnsDependencyFailureCodeWhenDialFails(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return nil, errors.New("dial failed")
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected dial failure")
	}
	if response.Code != utils.ErrorCodeDependencyFailure {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteReturnsTimeoutCodeWhenDialTimeoutOccurs(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		if config.Timeout > sshConnectTimeout {
			t.Fatalf("expected dial timeout to be capped by connect timeout, got %v", config.Timeout)
		}
		time.Sleep(1100 * time.Millisecond)
		return nil, errors.New("i/o timeout")
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 1,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected dial timeout")
	}
	if response.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteReturnsDependencyFailureCodeWhenSessionCreationFails(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return nil, errors.New("session failed")
		}}, nil
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected session failure")
	}
	if response.Code != utils.ErrorCodeDependencyFailure {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteReturnsExecutionFailureCodeWhenRemoteCommandFails(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &stubSSHSession{run: func(cmd string) error {
				return errors.New("remote exit 1")
			}}, nil
		}}, nil
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected remote command failure")
	}
	if response.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestExecuteReturnsTimeoutCodeWhenRemoteCommandBlocks(t *testing.T) {
	originalDial := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &stubSSHSession{run: func(cmd string) error {
				time.Sleep(1500 * time.Millisecond)
				return nil
			}}, nil
		}}, nil
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 1,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected timeout")
	}
	if response.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected code: %+v", response)
	}
}

func TestBuildSCPCommandCreatesUniqueTempKeyFilesConcurrently(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("TMPDIR", tmpDir)

	const workers = 8
	paths := make(chan string, workers)
	var wg sync.WaitGroup

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cmd, cleanup, err := buildSCPCommand("testuser", "127.0.0.1", "", "-----BEGIN RSA PRIVATE KEY-----\nkey-data\n-----END RSA PRIVATE KEY-----", 22, "/src", "/dst", true, profileModern)
			if err != nil {
				t.Errorf("buildSCPCommand failed: %v", err)
				return
			}
			defer cleanup()

			parts := strings.Split(cmd, " ")
			for i := 0; i < len(parts)-1; i++ {
				if parts[i] == "-i" {
					paths <- strings.Trim(parts[i+1], "'")
					return
				}
			}
			t.Error("missing key path in command")
		}()
	}

	wg.Wait()
	close(paths)

	seen := map[string]struct{}{}
	for path := range paths {
		if _, ok := seen[path]; ok {
			t.Fatalf("duplicate temp key path generated: %s", path)
		}
		seen[path] = struct{}{}
		if filepath.Dir(path) != tmpDir {
			t.Fatalf("expected temp file under TMPDIR, got %s", path)
		}
	}

	if len(seen) != workers {
		t.Fatalf("expected %d unique paths, got %d", workers, len(seen))
	}
}

func TestExecuteClosesSessionAndClientOnRunFailure(t *testing.T) {
	originalDial := sshDialFn
	var clientClosed, sessionClosed bool
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{
			newSession: func() (sshSession, error) {
				return &stubSSHSession{
					run: func(cmd string) error { return errors.New("remote exit 1") },
					close: func() error {
						sessionClosed = true
						return nil
					},
				}, nil
			},
			close: func() error {
				clientClosed = true
				return nil
			},
		}, nil
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 5,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected remote command failure")
	}
	if !sessionClosed || !clientClosed {
		t.Fatalf("expected session and client to close, sessionClosed=%v clientClosed=%v", sessionClosed, clientClosed)
	}
}

func TestExecuteSignalsAndClosesResourcesOnTimeout(t *testing.T) {
	originalDial := sshDialFn
	var clientClosed, sessionClosed, signaled bool
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{
			newSession: func() (sshSession, error) {
				return &stubSSHSession{
					run: func(cmd string) error {
						time.Sleep(1500 * time.Millisecond)
						return nil
					},
					signal: func(sig gossh.Signal) error {
						signaled = true
						return nil
					},
					close: func() error {
						sessionClosed = true
						return nil
					},
				}, nil
			},
			close: func() error {
				clientClosed = true
				return nil
			},
		}, nil
	}
	defer func() { sshDialFn = originalDial }()

	response := Execute(ExecuteRequest{
		Command:        "uptime",
		ExecuteTimeout: 1,
		Host:           "10.0.0.1",
		Port:           22,
		User:           "root",
		Password:       "secret",
	}, "instance-1")

	if response.Success {
		t.Fatal("expected timeout")
	}
	if !signaled || !sessionClosed || !clientClosed {
		t.Fatalf("expected signal and cleanup, signaled=%v sessionClosed=%v clientClosed=%v", signaled, sessionClosed, clientClosed)
	}
}

func TestExecuteSCPWithFallbackReturnsInitialSuccessWithoutRetry(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 5,
	})

	if !response.Success {
		t.Fatalf("expected success, got %+v", response)
	}
	if callCount != 1 {
		t.Fatalf("expected one execution attempt, got %d", callCount)
	}
}

func TestExecuteSCPWithFallbackRetriesWithLegacyOptions(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	commands := make([]string, 0, 2)
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		commands = append(commands, req.Command)
		if callCount == 1 {
			return local.ExecuteResponse{
				Success:    false,
				Output:     "no matching host key type found",
				Error:      "no matching host key type found",
				InstanceId: instanceId,
			}
		}
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 5,
	})

	if !response.Success {
		t.Fatalf("expected legacy retry to succeed, got %+v", response)
	}
	if callCount != 2 {
		t.Fatalf("expected two execution attempts, got %d", callCount)
	}
	if strings.Contains(commands[0], "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		t.Fatalf("did not expect legacy options on first attempt: %s", commands[0])
	}
	if !strings.Contains(commands[1], "PubkeyAcceptedAlgorithms=+ssh-rsa") || !strings.Contains(commands[1], "HostKeyAlgorithms=+ssh-rsa") {
		t.Fatalf("expected legacy options on retry, got: %s", commands[1])
	}
}

func TestExecuteSCPWithFallbackUsesRemainingBudgetForRetry(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	budgets := make([]int, 0, 2)
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		budgets = append(budgets, req.ExecuteTimeout)
		if callCount == 1 {
			time.Sleep(1100 * time.Millisecond)
			return local.ExecuteResponse{
				Success:    false,
				Output:     "no matching host key type found",
				Error:      "no matching host key type found",
				InstanceId: instanceId,
			}
		}
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 2,
	})

	if !response.Success {
		t.Fatalf("expected retry to succeed, got %+v", response)
	}
	if len(budgets) != 2 {
		t.Fatalf("expected two attempts, got %d", len(budgets))
	}
	if budgets[1] >= budgets[0] {
		t.Fatalf("expected retry budget to shrink, got first=%d second=%d", budgets[0], budgets[1])
	}
}

func TestExecuteSCPWithFallbackFailsWhenBudgetExhaustedBeforeRetry(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		time.Sleep(1100 * time.Millisecond)
		return local.ExecuteResponse{
			Success:    false,
			Output:     "no matching host key type found",
			Error:      "no matching host key type found",
			InstanceId: instanceId,
		}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 1,
	})

	if response.Success {
		t.Fatalf("expected failure when budget is exhausted, got %+v", response)
	}
	if response.Code != utils.ErrorCodeTimeout {
		t.Fatalf("expected timeout code, got %+v", response)
	}
	if callCount != 1 {
		t.Fatalf("expected no retry after budget exhaustion, got %d calls", callCount)
	}
}

func TestExecuteSCPWithFallbackDoesNotRetryOnUnrelatedFailure(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		return local.ExecuteResponse{
			Success:    false,
			Output:     "permission denied",
			Error:      "permission denied",
			InstanceId: instanceId,
		}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 5,
	})

	if response.Success {
		t.Fatalf("expected failure without retry, got %+v", response)
	}
	if callCount != 1 {
		t.Fatalf("expected one execution attempt, got %d", callCount)
	}
}

func TestExecuteSCPWithFallbackReturnsLegacyFailure(t *testing.T) {
	original := executeLocalSCPCommand
	callCount := 0
	executeLocalSCPCommand = func(req local.ExecuteRequest, instanceId string) local.ExecuteResponse {
		callCount++
		if callCount == 1 {
			return local.ExecuteResponse{
				Success:    false,
				Output:     "unable to negotiate",
				Error:      "unable to negotiate",
				InstanceId: instanceId,
			}
		}
		return local.ExecuteResponse{
			Success:    false,
			Output:     "legacy retry failed",
			Error:      "legacy retry failed",
			InstanceId: instanceId,
		}
	}
	defer func() { executeLocalSCPCommand = original }()

	response := executeSCPWithFallback("instance-1", local.ExecuteRequest{
		Command:        "scp -o StrictHostKeyChecking=no -P 22 -r /src user@host:/dst",
		ExecuteTimeout: 5,
	})

	if response.Success {
		t.Fatalf("expected legacy retry to fail, got %+v", response)
	}
	if response.Error != "legacy retry failed" {
		t.Fatalf("unexpected fallback response: %+v", response)
	}
	if callCount != 2 {
		t.Fatalf("expected two execution attempts, got %d", callCount)
	}
}

func BenchmarkAddLegacySCPOptions(b *testing.B) {
	command := "scp -o StrictHostKeyChecking=no -P 22 -r /very/long/path user@example.com:/tmp/target"
	b.ReportAllocs()
	for b.Loop() {
		updated := addLegacySCPOptions(command)
		if !strings.Contains(updated, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
			b.Fatal("expected legacy options in command")
		}
	}
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
