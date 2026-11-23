package ssh

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"encoding/pem"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	gossh "golang.org/x/crypto/ssh"

	"nats-executor/local"
	"nats-executor/utils"
)

func TestRegressionUploadHandlerTempKeyLifecycle(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("TMPDIR", tmpDir)

	originalExec := executeSCPCommand
	var keyPath string
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		parts := strings.Split(req.Command, " ")
		for i := 0; i < len(parts)-1; i++ {
			if parts[i] == "-i" {
				keyPath = strings.Trim(parts[i+1], "'")
				break
			}
		}
		if keyPath == "" {
			t.Fatal("expected temporary key path in command")
		}
		info, err := os.Stat(keyPath)
		if err != nil {
			t.Fatalf("expected temp key file to exist during execution: %v", err)
		}
		if info.Mode().Perm() != 0o600 {
			t.Fatalf("unexpected temp key permissions: %v", info.Mode().Perm())
		}
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() { executeSCPCommand = originalExec }()

	payload := []byte(`{"args":[{"source_path":"/tmp/demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","private_key":"-----BEGIN RSA PRIVATE KEY-----\nkey-data\n-----END RSA PRIVATE KEY-----","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleUploadToRemoteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected upload response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !result.Success {
		t.Fatalf("unexpected response: %+v", result)
	}
	if _, err := os.Stat(keyPath); !os.IsNotExist(err) {
		t.Fatalf("expected temp key to be removed after handler returns, stat err=%v", err)
	}
}

func TestRegressionDownloadToRemoteComposedContract(t *testing.T) {
	origDownload := downloadFromObjectStore
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	defer func() {
		downloadFromObjectStore = origDownload
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	steps := make([]string, 0, 2)
	stagingDir := "/tmp/composed/stage-1"
	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		steps = append(steps, "download")
		if req.TargetPath != stagingDir || req.FileName != "demo.txt" {
			t.Fatalf("unexpected download request: %+v", req)
		}
		return nil
	}
	mkdirTempDir = func(dir, pattern string) (string, error) {
		if dir != "/tmp/composed" {
			t.Fatalf("unexpected staging base dir: %s", dir)
		}
		return stagingDir, nil
	}
	removeAllPath = func(path string) error { return nil }
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		steps = append(steps, "execute")
		if !strings.Contains(req.Command, filepath.Join(stagingDir, "demo.txt")) {
			t.Fatalf("expected composed command to include downloaded file path, got %s", req.Command)
		}
		if !strings.Contains(req.LogCommand, "sshpass -e") {
			t.Fatalf("expected sshpass -e in log command, got %s", req.LogCommand)
		}
		if strings.Contains(req.LogCommand, "secret") {
			t.Fatalf("password should not appear in log command, got %s", req.LogCommand)
		}
		if req.Env == nil || req.Env["SSHPASS"] != "secret" {
			t.Fatalf("expected SSHPASS env var to be set, got %v", req.Env)
		}
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","local_path":"/tmp/composed","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !result.Success || result.Code != "" {
		t.Fatalf("unexpected response: %+v", result)
	}
	if len(steps) != 2 || steps[0] != "download" || steps[1] != "execute" {
		t.Fatalf("unexpected step order: %v", steps)
	}
}

func TestDownloadEncryptedKeyNonInteractive(t *testing.T) {
	keygen, err := exec.LookPath("ssh-keygen")
	if err != nil {
		t.Skip("OpenSSH client is required for noninteractive identity validation")
	}
	pub, key, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := gossh.NewPublicKey(pub)
	if err != nil {
		t.Fatal(err)
	}
	const passphrase = "download-key-test-passphrase"
	block, err := gossh.MarshalPrivateKeyWithPassphrase(key, "", []byte(passphrase))
	if err != nil {
		t.Fatal(err)
	}
	encoded := string(pem.EncodeToMemory(block))
	originalDownload, originalExec := downloadFromObjectStore, executeSCPCommand
	defer func() { downloadFromObjectStore, executeSCPCommand = originalDownload, originalExec }()
	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	for _, tc := range []struct {
		name, supplied string
		success        bool
	}{
		{"valid", passphrase, true}, {"invalid", passphrase + "-wrong", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			t.Setenv("TMPDIR", root)
			args := DownloadFileRequest{FileName: "test.txt", TargetPath: "/tmp/destination", Port: 22, Host: "192.0.2.1", User: "user", PrivateKey: encoded, Passphrase: tc.supplied, ExecuteTimeout: 5}
			payload, err := json.Marshal(map[string]any{"args": []DownloadFileRequest{args}})
			if err != nil {
				t.Fatal(err)
			}
			called := false
			executeSCPCommand = func(instanceID string, req local.ExecuteRequest) local.ExecuteResponse {
				called = true
				if !tc.success {
					t.Fatal("invalid private key reached SCP")
				}
				if strings.Contains(req.Command+req.LogCommand, tc.supplied) || strings.Contains(req.Command+req.LogCommand, "PRIVATE KEY") || len(req.Env) != 0 {
					t.Fatal("authentication material exposed to child")
				}
				paths, err := filepath.Glob(filepath.Join(root, "ssh_key_*"))
				if err != nil || len(paths) != 1 {
					t.Fatal("expected one temporary identity")
				}
				if !strings.Contains(req.Command, shellQuote(paths[0])) {
					t.Fatal("SCP did not select the temporary identity")
				}
				info, err := os.Stat(paths[0])
				if err != nil || info.Mode().Perm() != 0600 {
					t.Fatal("unsafe identity permissions")
				}
				out, err := exec.Command(keygen, "-y", "-P", "", "-f", paths[0]).Output()
				if err != nil {
					t.Fatal("ssh-keygen could not read the identity without a passphrase")
				}
				got, _, _, _, err := gossh.ParseAuthorizedKey(out)
				if err != nil || !bytes.Equal(got.Marshal(), expected.Marshal()) {
					t.Fatal("temporary identity did not match original public key")
				}
				return local.ExecuteResponse{Success: true, InstanceId: instanceID}
			}
			raw, ok := handleDownloadToRemoteMessage(payload, "test-node", nil)
			var result local.ExecuteResponse
			if !ok || json.Unmarshal(raw, &result) != nil || result.Success != tc.success || called != tc.success {
				t.Fatal("unexpected download result")
			}
			if !tc.success && (result.Code != utils.ErrorCodeInvalidRequest || result.Error != "SSH private key or passphrase is invalid or unsupported") {
				t.Fatal("expected bounded authentication error")
			}
			entries, err := os.ReadDir(root)
			if err != nil || len(entries) != 0 {
				t.Fatal("temporary key or staging directory was retained")
			}
		})
	}
}
