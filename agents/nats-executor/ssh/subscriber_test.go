package ssh

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	gossh "golang.org/x/crypto/ssh"
	"nats-executor/local"
	"nats-executor/utils"
	"nats-executor/utils/downloaderr"
)

type stubResponseMsg struct {
	respond func(payload []byte) error
}

type subscriberStubSSHSession struct {
	run    func(cmd string) error
	signal func(sig gossh.Signal) error
	close  func() error
	stdout io.Writer
	stderr io.Writer
}

func (s *subscriberStubSSHSession) Run(cmd string) error {
	if s.run == nil {
		return nil
	}
	return s.run(cmd)
}

func (s *subscriberStubSSHSession) Signal(sig gossh.Signal) error {
	if s.signal == nil {
		return nil
	}
	return s.signal(sig)
}

func (s *subscriberStubSSHSession) Close() error {
	if s.close == nil {
		return nil
	}
	return s.close()
}

func (s *subscriberStubSSHSession) SetStdout(w io.Writer) { s.stdout = w }
func (s *subscriberStubSSHSession) SetStderr(w io.Writer) { s.stderr = w }

func (s stubResponseMsg) Respond(payload []byte) error {
	if s.respond == nil {
		return nil
	}
	return s.respond(payload)
}

func TestHandleSSHExecuteMessageRejectsMalformedJSON(t *testing.T) {
	response, ok := handleSSHExecuteMessage([]byte("bad-json"), "instance-1", nil)
	if !ok {
		t.Fatal("expected malformed payload to return explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleSSHExecuteMessageReturnsExecutionResponse(t *testing.T) {
	original := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &subscriberStubSSHSession{run: func(cmd string) error { return nil }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	response, ok := handleSSHExecuteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected execute response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !result.Success {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Error != "" {
		t.Fatalf("success response should not contain error: %+v", result)
	}
	if result.Code != "" {
		t.Fatalf("success response should not contain code: %+v", result)
	}
}

func TestRespondSSHExecuteMessageSendsExecutionResponse(t *testing.T) {
	original := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &subscriberStubSSHSession{run: func(cmd string) error { return nil }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	var got ExecuteResponse
	msg := stubResponseMsg{respond: func(response []byte) error {
		return json.Unmarshal(response, &got)
	}}

	if ok := respondSSHExecuteMessage(msg, payload, "instance-1", nil); !ok {
		t.Fatal("expected SSH response to be sent successfully")
	}
	if !got.Success || got.InstanceId != "instance-1" {
		t.Fatalf("unexpected response payload: %+v", got)
	}
}

func TestRespondSSHExecuteMessageReturnsFalseWhenRespondFails(t *testing.T) {
	original := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &subscriberStubSSHSession{run: func(cmd string) error { return nil }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	msg := stubResponseMsg{respond: func(response []byte) error {
		return errors.New("nats unavailable")
	}}

	if ok := respondSSHExecuteMessage(msg, payload, "instance-1", nil); ok {
		t.Fatal("expected respond failure to return false")
	}
}

func TestHandleDownloadToRemoteMessageUsesDefaultLocalPath(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath

	var downloadedReq utils.DownloadFileRequest
	var executedReq local.ExecuteRequest
	var stagingDir string

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		downloadedReq = req
		return nil
	}
	mkdirTempDir = func(dir, pattern string) (string, error) {
		if dir != os.TempDir() {
			t.Fatalf("expected default staging base %s, got %s", os.TempDir(), dir)
		}
		path := filepath.Join(dir, "nats-executor-test-default")
		stagingDir = path
		return path, nil
	}
	removeAllPath = func(path string) error {
		if path != stagingDir {
			t.Fatalf("unexpected cleanup path: %s", path)
		}
		return nil
	}
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		if sourcePath != filepath.Join(stagingDir, "demo.txt") {
			t.Fatalf("expected default local path source, got %s", sourcePath)
		}
		if targetPath != "/remote/path" || !isUpload {
			t.Fatalf("unexpected scp build args: source=%s target=%s upload=%v", sourcePath, targetPath, isUpload)
		}
		return "scp command", func() {}, nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		executedReq = req
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected response")
	}

	if downloadedReq.TargetPath != stagingDir {
		t.Fatalf("expected staging path %s, got %+v", stagingDir, downloadedReq)
	}
	if executedReq.Command != "scp command" || executedReq.LogCommand == "" {
		t.Fatalf("expected SCP execution request with redacted log command, got %+v", executedReq)
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !result.Success {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Error != "" {
		t.Fatalf("success response should not contain error: %+v", result)
	}
	if result.Code != "" {
		t.Fatalf("success response should not contain code: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageReturnsBuildErrorResponse(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/staging-build"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error {
		if path != stagingDir {
			t.Fatalf("unexpected cleanup path: %s", path)
		}
		return nil
	}
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		return "", nil, errors.New("bad scp")
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		t.Fatal("should not execute scp when build fails")
		return local.ExecuteResponse{}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected build error response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "Failed to build SCP command: bad scp") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageRejectsInvalidPayload(t *testing.T) {
	payload := []byte(`{"args":[{"bucket_name":1}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected invalid payload to return explicit error response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageReturnsDownloadFailureResponse(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/staging-download-fail"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		return errors.New("store unavailable")
	}
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error {
		if path != stagingDir {
			t.Fatalf("unexpected cleanup path: %s", path)
		}
		return nil
	}
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		t.Fatal("should not build scp command when download fails")
		return "", nil, nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		t.Fatal("should not execute scp when download fails")
		return local.ExecuteResponse{}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download failure response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "Failed to download file: store unavailable") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeDependencyFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageMapsTimeoutDownloadFailureResponse(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/staging-timeout"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		return downloaderr.New(downloaderr.KindTimeout, context.DeadlineExceeded)
	}
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error { return nil }
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		t.Fatal("should not build scp command when download fails")
		return "", nil, nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		t.Fatal("should not execute scp when download fails")
		return local.ExecuteResponse{}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download failure response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageMapsIOFailureResponse(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/staging-io"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		return downloaderr.New(downloaderr.KindIO, errors.New("rename failed"))
	}
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error { return nil }
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		t.Fatal("should not build scp command when download fails")
		return "", nil, nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		t.Fatal("should not execute scp when download fails")
		return local.ExecuteResponse{}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download failure response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleUploadToRemoteMessageReturnsBuildErrorResponse(t *testing.T) {
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand

	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		return "", nil, errors.New("cannot build")
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		t.Fatal("should not execute when command build fails")
		return local.ExecuteResponse{}
	}
	defer func() {
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
	}()

	payload := []byte(`{"args":[{"source_path":"/tmp/demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleUploadToRemoteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected build failure response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "Failed to build SCP command: cannot build") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleUploadToRemoteMessageRejectsMalformedJSON(t *testing.T) {
	response, ok := handleUploadToRemoteMessage([]byte(`{"args":[`), "instance-1")
	if !ok {
		t.Fatal("expected malformed upload payload to return explicit error response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleUploadToRemoteMessageReturnsExecutionResponse(t *testing.T) {
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand

	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		if sourcePath != "/tmp/demo.txt" || targetPath != "/remote/path" || !isUpload {
			t.Fatalf("unexpected upload args: source=%s target=%s upload=%v", sourcePath, targetPath, isUpload)
		}
		return "upload scp", func() {}, nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		if req.Command != "upload scp" {
			t.Fatalf("unexpected execute request: %+v", req)
		}
		return local.ExecuteResponse{Success: false, Error: "scp failed", InstanceId: instanceId}
	}
	defer func() {
		buildSCPCommandFn = origBuild
		executeSCPCommand = origExec
	}()

	payload := []byte(`{"args":[{"source_path":"/tmp/demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleUploadToRemoteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected upload response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || result.Error != "scp failed" {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestSSHExecuteResponseIncludesExecutionFailureCode(t *testing.T) {
	original := sshDialFn
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		return stubSSHClient{newSession: func() (sshSession, error) {
			return &subscriberStubSSHSession{run: func(cmd string) error { return errors.New("remote exec failed") }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	response, ok := handleSSHExecuteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected execute response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestExecuteRetriesWithLegacyProfileAfterModernNegotiationFailure(t *testing.T) {
	originalDial := sshDialFn
	attempts := 0
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		attempts++
		switch attempts {
		case 1:
			if got := config.HostKeyAlgorithms; len(got) == 0 || got[0] != gossh.KeyAlgoED25519 {
				t.Fatalf("expected modern host key algorithms first, got %v", got)
			}
			return nil, errors.New("no matching host key type found")
		case 2:
			if got := config.HostKeyAlgorithms; len(got) == 0 || got[0] != gossh.KeyAlgoRSA {
				t.Fatalf("expected legacy host key algorithms on retry, got %v", got)
			}
			return stubSSHClient{newSession: func() (sshSession, error) {
				return &stubSSHSession{run: func(cmd string) error { return nil }}, nil
			}}, nil
		default:
			t.Fatalf("unexpected extra dial attempt: %d", attempts)
			return nil, nil
		}
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

	if !response.Success {
		t.Fatalf("expected legacy retry to succeed, got %+v", response)
	}
	if attempts != 2 {
		t.Fatalf("expected two dial attempts, got %d", attempts)
	}
}

func TestExecuteReturnsDependencyFailureWhenLegacyRetryAlsoFails(t *testing.T) {
	originalDial := sshDialFn
	attempts := 0
	sshDialFn = func(network, addr string, config *gossh.ClientConfig) (sshClient, error) {
		attempts++
		if attempts == 1 {
			return nil, errors.New("unable to negotiate")
		}
		if attempts == 2 {
			if got := config.HostKeyAlgorithms; len(got) == 0 || got[0] != gossh.KeyAlgoRSA {
				t.Fatalf("expected legacy host key algorithms on retry, got %v", got)
			}
			return nil, errors.New("legacy retry failed")
		}
		t.Fatalf("unexpected extra dial attempt: %d", attempts)
		return nil, nil
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
		t.Fatal("expected legacy retry failure")
	}
	if response.Code != utils.ErrorCodeDependencyFailure {
		t.Fatalf("unexpected response: %+v", response)
	}
	if attempts != 2 {
		t.Fatalf("expected two dial attempts, got %d", attempts)
	}
}

func TestHandleDownloadToRemoteMessageIntegrationPath(t *testing.T) {
	origDownload := downloadFromObjectStore
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/integration/stage-123"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	mkdirTempDir = func(dir, pattern string) (string, error) {
		if dir != "/tmp/integration" {
			t.Fatalf("expected local path base dir, got %s", dir)
		}
		return stagingDir, nil
	}
	removeAllPath = func(path string) error {
		if path != stagingDir {
			t.Fatalf("unexpected cleanup path: %s", path)
		}
		return nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		if !strings.Contains(req.Command, filepath.Join(stagingDir, "demo.txt")) {
			t.Fatalf("expected composed command to include downloaded file path, got %s", req.Command)
		}
		if req.LogCommand == "" {
			t.Fatal("expected redacted log command")
		}
		return local.ExecuteResponse{Success: true, Output: "done", InstanceId: instanceId}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","local_path":"/tmp/integration","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected integration response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if !result.Success || result.Code != "" {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageIntegrationFailureFromExecutor(t *testing.T) {
	origDownload := downloadFromObjectStore
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/integration/stage-456"

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error { return nil }
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		return local.ExecuteResponse{Success: false, Error: "scp failed", Code: utils.ErrorCodeExecutionFailure, InstanceId: instanceId}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","local_path":"/tmp/integration","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected response")
	}

	var result local.ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeExecutionFailure || result.Error != "scp failed" {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleDownloadToRemoteMessageCleansStagingDirAfterExecutorFailure(t *testing.T) {
	origDownload := downloadFromObjectStore
	origExec := executeSCPCommand
	origMkdirTemp := mkdirTempDir
	origRemoveAll := removeAllPath
	stagingDir := "/tmp/staging-cleanup"
	cleaned := false

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	mkdirTempDir = func(dir, pattern string) (string, error) { return stagingDir, nil }
	removeAllPath = func(path string) error {
		if path == stagingDir {
			cleaned = true
		}
		return nil
	}
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		return local.ExecuteResponse{Success: false, Error: "scp failed", Code: utils.ErrorCodeExecutionFailure, InstanceId: instanceId}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		executeSCPCommand = origExec
		mkdirTempDir = origMkdirTemp
		removeAllPath = origRemoveAll
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","local_path":"/tmp/integration","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	_, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected response")
	}
	if !cleaned {
		t.Fatal("expected staging dir cleanup")
	}
}
