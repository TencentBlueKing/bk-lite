package local

import (
	"encoding/json"
	"strings"
	"testing"

	"nats-executor/utils"
)

func TestRegressionLocalHandlerTimeoutContract(t *testing.T) {
	payload := []byte(`{"args":[{"command":"sleep 2","execute_timeout":1,"shell":"sh"}],"kwargs":{}}`)
	response, ok := handleLocalExecuteMessage(payload, "instance-1")
	if !ok {
		t.Fatal("expected timeout response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success {
		t.Fatalf("expected timeout failure, got %+v", result)
	}
	if result.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected code: %+v", result)
	}
	if !strings.Contains(result.Error, "timed out") {
		t.Fatalf("unexpected error: %+v", result)
	}
}

func TestRegressionLocalHandlerMalformedPayloadContract(t *testing.T) {
	response, ok := handleDownloadToLocalMessage([]byte(`{"args":[{"bucket_name":1}],"kwargs":{}}`), "instance-1", nil)
	if !ok {
		t.Fatal("expected explicit error response")
	}

	var result ExecuteResponse
	if err := json.Unmarshal(response, &result); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if result.Success || result.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("unexpected response: %+v", result)
	}
	if !strings.Contains(result.Error, "invalid request payload") {
		t.Fatalf("unexpected error: %+v", result)
	}
}
