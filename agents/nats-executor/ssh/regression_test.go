package ssh

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

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
		if !strings.Contains(req.LogCommand, "sshpass -p '***'") {
			t.Fatalf("expected redacted log command, got %s", req.LogCommand)
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
