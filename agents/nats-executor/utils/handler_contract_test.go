package utils

import (
	"encoding/json"
	"testing"
)

type contractResponse struct {
	Result     string `json:"result,omitempty"`
	InstanceID string `json:"instance_id"`
	Success    bool   `json:"success"`
	Code       string `json:"code,omitempty"`
	Error      string `json:"error,omitempty"`
}

func decodeContractResponse(t *testing.T, payload []byte) contractResponse {
	t.Helper()

	var resp contractResponse
	if err := json.Unmarshal(payload, &resp); err != nil {
		t.Fatalf("failed to decode response payload: %v", err)
	}
	return resp
}

func TestNewErrorExecuteResponseReturnsStableContract(t *testing.T) {
	resp := decodeContractResponse(t, NewErrorExecuteResponse("instance-1", ErrorCodeTimeout, "timed out"))

	if resp.InstanceID != "instance-1" {
		t.Fatalf("unexpected instance id: %+v", resp)
	}
	if resp.Success {
		t.Fatalf("error response should not be successful: %+v", resp)
	}
	if resp.Code != ErrorCodeTimeout {
		t.Fatalf("unexpected error code: %+v", resp)
	}
	if resp.Error != "timed out" || resp.Result != "timed out" {
		t.Fatalf("error response should mirror message into error/result: %+v", resp)
	}
}

func TestNewSuccessExecuteResponseOmitsErrorFields(t *testing.T) {
	resp := decodeContractResponse(t, NewSuccessExecuteResponse("instance-1", "done"))

	if resp.InstanceID != "instance-1" {
		t.Fatalf("unexpected instance id: %+v", resp)
	}
	if !resp.Success {
		t.Fatalf("success response should be successful: %+v", resp)
	}
	if resp.Result != "done" {
		t.Fatalf("unexpected result: %+v", resp)
	}
	if resp.Code != "" || resp.Error != "" {
		t.Fatalf("success response should omit error fields: %+v", resp)
	}
}
