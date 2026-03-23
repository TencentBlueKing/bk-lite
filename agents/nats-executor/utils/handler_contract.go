package utils

import "encoding/json"

const (
	ErrorCodeInvalidRequest    = "invalid_request"
	ErrorCodeDependencyFailure = "dependency_failure"
	ErrorCodeExecutionFailure  = "execution_failure"
	ErrorCodeTimeout           = "timeout"
)

type HandlerResponse interface {
	responseEnvelope() any
}

type executeHandlerResponse struct {
	Output     string `json:"result,omitempty"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Code       string `json:"code,omitempty"`
	Error      string `json:"error,omitempty"`
}

func (r executeHandlerResponse) responseEnvelope() any { return r }

func MarshalHandlerResponse(resp HandlerResponse) []byte {
	data, _ := json.Marshal(resp.responseEnvelope())
	return data
}

func NewErrorExecuteResponse(instanceID, code, message string) []byte {
	return MarshalHandlerResponse(executeHandlerResponse{
		InstanceId: instanceID,
		Success:    false,
		Code:       code,
		Error:      message,
		Output:     message,
	})
}

func NewSuccessExecuteResponse(instanceID, output string) []byte {
	return MarshalHandlerResponse(executeHandlerResponse{
		InstanceId: instanceID,
		Success:    true,
		Output:     output,
	})
}
