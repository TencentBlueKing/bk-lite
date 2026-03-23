package ssh

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	gossh "golang.org/x/crypto/ssh"
	"nats-executor/local"
	"nats-executor/utils"
)

func TestHandleSSHExecuteMessageRejectsMalformedJSON(t *testing.T) {
	response, ok := handleSSHExecuteMessage([]byte("bad-json"), "instance-1")
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
			return &stubSSHSession{run: func(cmd string) error { return nil }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	response, ok := handleSSHExecuteMessage(payload, "instance-1")
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

func TestHandleDownloadToRemoteMessageUsesDefaultLocalPath(t *testing.T) {
	origDownload := downloadFromObjectStore
	origBuild := buildSCPCommandFn
	origExec := executeSCPCommand

	var downloadedReq utils.DownloadFileRequest
	var executedReq local.ExecuteRequest

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		downloadedReq = req
		return nil
	}
	buildSCPCommandFn = func(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
		if sourcePath != "/tmp/demo.txt" {
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
	}()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"key","file_name":"demo.txt","target_path":"/remote/path","host":"10.0.0.1","port":22,"user":"root","password":"secret","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleDownloadToRemoteMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected response")
	}

	if downloadedReq.TargetPath != "/tmp" {
		t.Fatalf("expected default local path /tmp, got %+v", downloadedReq)
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

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
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

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error {
		return errors.New("store unavailable")
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
			return &stubSSHSession{run: func(cmd string) error { return errors.New("remote exec failed") }, stdout: &bytes.Buffer{}, stderr: &bytes.Buffer{}}, nil
		}}, nil
	}
	defer func() { sshDialFn = original }()

	payload := []byte(`{"args":[{"command":"uptime","execute_timeout":5,"host":"10.0.0.1","port":22,"user":"root","password":"x"}],"kwargs":{}}`)
	response, ok := handleSSHExecuteMessage(payload, "instance-1")
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

func TestHandleDownloadToRemoteMessageIntegrationPath(t *testing.T) {
	origDownload := downloadFromObjectStore
	origExec := executeSCPCommand

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		if !strings.Contains(req.Command, "/tmp/integration/demo.txt") {
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

	downloadFromObjectStore = func(req utils.DownloadFileRequest, _ sshConn) error { return nil }
	executeSCPCommand = func(instanceId string, req local.ExecuteRequest) local.ExecuteResponse {
		return local.ExecuteResponse{Success: false, Error: "scp failed", Code: utils.ErrorCodeExecutionFailure, InstanceId: instanceId}
	}
	defer func() {
		downloadFromObjectStore = origDownload
		executeSCPCommand = origExec
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
