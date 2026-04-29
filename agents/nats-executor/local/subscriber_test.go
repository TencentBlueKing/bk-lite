package local

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"nats-executor/utils"
	"nats-executor/utils/downloaderr"
)

type stubResponseMsg struct {
	respond func(payload []byte) error
}

func (s stubResponseMsg) Respond(payload []byte) error {
	if s.respond == nil {
		return nil
	}
	return s.respond(payload)
}

func TestExecuteResponseIncludesErrorCodeForTimeout(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "sleep 2",
		ExecuteTimeout: 1,
		Shell:          "sh",
	}, "instance-timeout")

	if response.Success {
		t.Fatal("expected timeout failure")
	}
	if !strings.Contains(response.Error, "timed out") {
		t.Fatalf("unexpected error: %+v", response)
	}
	if response.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected timeout code: %+v", response)
	}
}

func TestExecuteResponseIncludesErrorCodeForExecutionFailure(t *testing.T) {
	response := Execute(ExecuteRequest{
		Command:        "exit 9",
		ExecuteTimeout: 5,
		Shell:          "sh",
	}, "instance-failure")

	if response.Success {
		t.Fatal("expected execution failure")
	}
	if !strings.Contains(response.Error, "exit code 9") {
		t.Fatalf("unexpected error: %+v", response)
	}
	if response.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected execution code: %+v", response)
	}
}

func TestHandleLocalExecuteMessageRejectsMalformedJSON(t *testing.T) {
	response, ok := handleLocalExecuteMessage([]byte("not-json"), "instance-1")
	if !ok {
		t.Fatal("expected malformed payload to return explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleLocalExecuteMessageRejectsMissingArgs(t *testing.T) {
	payload := []byte(`{"args":[],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected empty args payload to return explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "missing request arguments") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleLocalExecuteMessageReturnsExecutionResponse(t *testing.T) {
	original := executeLocalCommand
	executeLocalCommand = func(req ExecuteRequest, instanceId string) ExecuteResponse {
		if req.Command != "echo hello" || req.ExecuteTimeout != 5 || instanceId != "instance-1" {
			t.Fatalf("unexpected execute args: %+v instance=%s", req, instanceId)
		}
		return ExecuteResponse{Output: "hello", InstanceId: instanceId, Success: true}
	}
	defer func() { executeLocalCommand = original }()

	payload := []byte(`{"args":[{"command":"echo hello","execute_timeout":5}],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected execution payload to produce response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if !result.Success || result.Output != "hello" || result.InstanceId != "instance-1" {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Error != "" {
		t.Fatalf("success response should not contain error: %+v", result)
	}
	if result.Code != "" {
		t.Fatalf("success response should not contain code: %+v", result)
	}
}

func TestHandleLocalExecuteMessageIntegrationExecutionFailure(t *testing.T) {
	payload := []byte(`{"args":[{"command":"exit 7","execute_timeout":5,"shell":"sh"}],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected failure response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected response: %+v", result)
	}
	if !strings.Contains(result.Error, "exit code 7") {
		t.Fatalf("unexpected error: %+v", result)
	}
}

func TestHandleLocalExecuteMessageIntegrationTimeout(t *testing.T) {
	payload := []byte(`{"args":[{"command":"sleep 2","execute_timeout":1,"shell":"sh"}],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected timeout response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestRespondLocalExecuteMessageSendsExecutionResponse(t *testing.T) {
	original := executeLocalCommand
	executeLocalCommand = func(req ExecuteRequest, instanceId string) ExecuteResponse {
		return ExecuteResponse{Output: "hello", InstanceId: instanceId, Success: true}
	}
	defer func() { executeLocalCommand = original }()

	payload := []byte(`{"args":[{"command":"echo hello","execute_timeout":5}],"kwargs":{}}`)
	var got ExecuteResponse
	msg := stubResponseMsg{respond: func(response []byte) error {
		return json.Unmarshal(response, &got)
	}}

	if ok := respondLocalExecuteMessage(msg, payload, "instance-1"); !ok {
		t.Fatal("expected response to be sent successfully")
	}
	if !got.Success || got.Output != "hello" || got.InstanceId != "instance-1" {
		t.Fatalf("unexpected response payload: %+v", got)
	}
}

func TestRespondLocalExecuteMessageReturnsFalseWhenRespondFails(t *testing.T) {
	original := executeLocalCommand
	executeLocalCommand = func(req ExecuteRequest, instanceId string) ExecuteResponse {
		return ExecuteResponse{Output: "hello", InstanceId: instanceId, Success: true}
	}
	defer func() { executeLocalCommand = original }()

	payload := []byte(`{"args":[{"command":"echo hello","execute_timeout":5}],"kwargs":{}}`)
	msg := stubResponseMsg{respond: func(response []byte) error {
		return errors.New("nats unavailable")
	}}

	if ok := respondLocalExecuteMessage(msg, payload, "instance-1"); ok {
		t.Fatal("expected respond failure to return false")
	}
}

func TestHandleDownloadToLocalMessageReturnsDownloadError(t *testing.T) {
	original := downloadToLocalFile
	downloadToLocalFile = func(req utils.DownloadFileRequest, _ downloadConn) error {
		if req.BucketName != "bucket" || req.FileKey != "file-key" {
			t.Fatalf("unexpected download request: %+v", req)
		}
		return errors.New("boom")
	}
	defer func() { downloadToLocalFile = original }()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"file-key","file_name":"demo.txt","target_path":"/tmp","execute_timeout":3}],"kwargs":{}}`)
	response, ok := handleDownloadToLocalMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success {
		t.Fatalf("expected failure response, got %+v", result)
	}
	if !strings.Contains(result.Output, "Failed to download file: boom") {
		t.Fatalf("unexpected output: %+v", result)
	}
	if !strings.Contains(result.Error, "Failed to download file: boom") {
		t.Fatalf("expected error field to be populated: %+v", result)
	}
	if result.Code != utils.ErrorCodeDependencyFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleDownloadToLocalMessageMapsTimeoutErrorCode(t *testing.T) {
	original := downloadToLocalFile
	downloadToLocalFile = func(req utils.DownloadFileRequest, _ downloadConn) error {
		return downloaderr.New(downloaderr.KindTimeout, context.DeadlineExceeded)
	}
	defer func() { downloadToLocalFile = original }()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"file-key","file_name":"demo.txt","target_path":"/tmp","execute_timeout":3}],"kwargs":{}}`)
	response, ok := handleDownloadToLocalMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleDownloadToLocalMessageMapsIOErrorCode(t *testing.T) {
	original := downloadToLocalFile
	downloadToLocalFile = func(req utils.DownloadFileRequest, _ downloadConn) error {
		return downloaderr.New(downloaderr.KindIO, errors.New("rename failed"))
	}
	defer func() { downloadToLocalFile = original }()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"file-key","file_name":"demo.txt","target_path":"/tmp","execute_timeout":3}],"kwargs":{}}`)
	response, ok := handleDownloadToLocalMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected response: %+v", result)
	}
}

func TestHandleDownloadToLocalMessageReturnsSuccessMessage(t *testing.T) {
	original := downloadToLocalFile
	downloadToLocalFile = func(req utils.DownloadFileRequest, _ downloadConn) error {
		return nil
	}
	defer func() { downloadToLocalFile = original }()

	payload := []byte(`{"args":[{"bucket_name":"bucket","file_key":"file-key","file_name":"demo.txt","target_path":"/tmp","execute_timeout":3}],"kwargs":{}}`)
	response, ok := handleDownloadToLocalMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected download handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if !result.Success || result.Output != "File successfully downloaded to /tmp/demo.txt" {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Error != "" {
		t.Fatalf("success response should not contain error: %+v", result)
	}
	if result.Code != "" {
		t.Fatalf("success response should not contain code: %+v", result)
	}
}

func TestHandleDownloadToLocalMessageRejectsInvalidArgPayload(t *testing.T) {
	payload := []byte(`{"args":[{"bucket_name":1}],"kwargs":{}}`)
	response, ok := handleDownloadToLocalMessage(payload, "instance-1", nil)
	if !ok {
		t.Fatal("expected invalid download payload to return explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleUnzipToLocalMessageReturnsParentDir(t *testing.T) {
	original := unzipLocalArchive
	unzipLocalArchive = func(req utils.UnzipRequest) (string, error) {
		if req.ZipPath != "/tmp/demo.zip" || req.DestDir != "/tmp/out" {
			t.Fatalf("unexpected unzip request: %+v", req)
		}
		return "parent-dir", nil
	}
	defer func() { unzipLocalArchive = original }()

	payload := []byte(`{"args":[{"zip_path":"/tmp/demo.zip","dest_dir":"/tmp/out"}],"kwargs":{}}`)
	response, ok := handleUnzipToLocalMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected unzip handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if !result.Success || result.Output != "parent-dir" {
		t.Fatalf("unexpected response: %+v", result)
	}
	if result.Error != "" {
		t.Fatalf("success response should not contain error: %+v", result)
	}
	if result.Code != "" {
		t.Fatalf("success response should not contain code: %+v", result)
	}
}

func TestHandleUnzipToLocalMessageReturnsErrorResponse(t *testing.T) {
	original := unzipLocalArchive
	unzipLocalArchive = func(req utils.UnzipRequest) (string, error) {
		return "", errors.New("bad zip")
	}
	defer func() { unzipLocalArchive = original }()

	payload := []byte(`{"args":[{"zip_path":"/tmp/demo.zip","dest_dir":"/tmp/out"}],"kwargs":{}}`)
	response, ok := handleUnzipToLocalMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected unzip handler to return response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || !strings.Contains(result.Output, "Failed to unzip file: bad zip") {
		t.Fatalf("unexpected response: %+v", result)
	}
	if !strings.Contains(result.Error, "Failed to unzip file: bad zip") {
		t.Fatalf("expected error field to be populated: %+v", result)
	}
	if result.Code != utils.ErrorCodeExecutionFailure {
		t.Fatalf("unexpected error code: %+v", result)
	}
}

func TestHandleHealthCheckMessageReturnsStablePayload(t *testing.T) {
	original := nowUTC
	nowUTC = func() time.Time {
		return time.Date(2026, 3, 23, 12, 0, 0, 0, time.UTC)
	}
	defer func() { nowUTC = original }()

	response := handleHealthCheckMessage("instance-1")
	var result HealthCheckResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if !result.Success || result.Status != "ok" || result.InstanceId != "instance-1" || result.Timestamp != "2026-03-23T12:00:00Z" {
		t.Fatalf("unexpected health response: %+v", result)
	}
}
