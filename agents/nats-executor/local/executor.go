package local

import (
	"context"
	"encoding/json"
	"fmt"
	"nats-executor/logger"
	"nats-executor/utils"
	"os/exec"
	"time"

	"github.com/nats-io/nats.go"
)

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	logger.Debugf("[Local Execute] Instance: %s, Starting command execution", instanceId)
	logger.Debugf("[Local Execute] Instance: %s, Command: %s", instanceId, req.Command)
	logger.Debugf("[Local Execute] Instance: %s, Timeout: %ds", instanceId, req.ExecuteTimeout)

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	var cmd *exec.Cmd
	shell := req.Shell
	if shell == "" {
		shell = "sh"
	}

	switch shell {
	case "bat", "cmd":
		cmd = exec.CommandContext(ctx, "cmd", "/c", req.Command)
	case "powershell":
		cmd = exec.CommandContext(ctx, "powershell", "-Command", req.Command)
	case "pwsh":
		cmd = exec.CommandContext(ctx, "pwsh", "-Command", req.Command)
	case "bash":
		cmd = exec.CommandContext(ctx, "bash", "-c", req.Command)
	case "sh":
		cmd = exec.CommandContext(ctx, "sh", "-c", req.Command)
	default:
		cmd = exec.CommandContext(ctx, shell, "-c", req.Command)
	}

	startTime := time.Now()
	output, err := cmd.CombinedOutput()
	duration := time.Since(startTime)

	var exitCode int
	if exitError, ok := err.(*exec.ExitError); ok {
		exitCode = exitError.ExitCode()
	}

	response := ExecuteResponse{
		Output:     string(output),
		InstanceId: instanceId,
		Success:    err == nil && ctx.Err() != context.DeadlineExceeded,
	}

	if ctx.Err() == context.DeadlineExceeded {
		response.Error = fmt.Sprintf("Command timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
		logger.Warnf("[Local Execute] Instance: %s, Command timed out after %v", instanceId, duration)
		logger.Debugf("[Local Execute] Instance: %s, Partial output: %s", instanceId, string(output))
	} else if err != nil {
		response.Error = fmt.Sprintf("Command execution failed with exit code %d: %v", exitCode, err)
		logger.Warnf("[Local Execute] Instance: %s, Command execution failed after %v, exit code: %d", instanceId, duration, exitCode)
		logger.Debugf("[Local Execute] Instance: %s, Error: %v", instanceId, err)
		logger.Debugf("[Local Execute] Instance: %s, Full output: %s", instanceId, string(output))

		if contains(req.Command, "scp") || contains(req.Command, "sshpass") {
			logger.Debugf("[Local Execute] Instance: %s, SCP Command detected - analyzing failure...", instanceId)
			analyzeSCPFailure(instanceId, string(output), exitCode)
		}
	} else {
		logger.Debugf("[Local Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		logger.Debugf("[Local Execute] Instance: %s, Output length: %d bytes", instanceId, len(output))
		if len(output) > 0 {
			logger.Debugf("[Local Execute] Instance: %s, Output: %s", instanceId, string(output))
		}
	}

	return response
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr ||
		(len(s) > len(substr) &&
			(s[:len(substr)] == substr ||
				s[len(s)-len(substr):] == substr ||
				containsInMiddle(s, substr))))
}

func containsInMiddle(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func analyzeSCPFailure(instanceId, output string, exitCode int) {
	logger.Debugf("[SCP Analysis] Instance: %s, Analyzing SCP failure with exit code: %d", instanceId, exitCode)

	switch exitCode {
	case 1:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 1 - General error", instanceId)
		if contains(output, "Permission denied") {
			logger.Debugf("[SCP Analysis] Instance: %s, Issue: Permission denied - Check SSH credentials/key", instanceId)
		} else if contains(output, "Connection refused") {
			logger.Debugf("[SCP Analysis] Instance: %s, Issue: Connection refused - Check if SSH service is running", instanceId)
		} else if contains(output, "No such file or directory") {
			logger.Debugf("[SCP Analysis] Instance: %s, Issue: File/directory not found - Check source/target paths", instanceId)
		} else if contains(output, "Host key verification failed") {
			logger.Debugf("[SCP Analysis] Instance: %s, Issue: Host key verification failed - SSH host key problem", instanceId)
		}
	case 2:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 2 - Protocol error", instanceId)
	case 3:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 3 - Interrupted", instanceId)
	case 4:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 4 - Unexpected network error", instanceId)
	case 5:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 5 - sshpass authentication failure", instanceId)
		logger.Debugf("[SCP Analysis] Instance: %s, Issue: Wrong password or sshpass not available", instanceId)
	case 6:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code 6 - sshpass host key unknown", instanceId)
	default:
		logger.Debugf("[SCP Analysis] Instance: %s, Exit code %d - Unknown error", instanceId, exitCode)
	}

	if contains(output, "sshpass: command not found") {
		logger.Warnf("[SCP Analysis] Instance: %s, sshpass is not installed on the system", instanceId)
	}
	if contains(output, "ssh: connect to host") && contains(output, "Connection timed out") {
		logger.Debugf("[SCP Analysis] Instance: %s, Issue: Network connectivity problem or wrong hostname/port", instanceId)
	}
	if contains(output, "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED") {
		logger.Warnf("[SCP Analysis] Instance: %s, Remote host key has changed - security risk", instanceId)
	}
}

func SubscribeLocalExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("local.execute.%s", *instanceId)
	logger.Infof("[Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Local Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[Local Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[Local Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var localExecuteRequest ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &localExecuteRequest); err != nil {
			logger.Errorf("[Local Subscribe] Instance: %s, Error unmarshalling first arg to local.ExecuteRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[Local Subscribe] Instance: %s, Parsed command request", *instanceId)
		responseData := Execute(localExecuteRequest, *instanceId)
		logger.Debugf("[Local Subscribe] Instance: %s, Command execution completed, success: %v", *instanceId, responseData.Success)

		responseContent, err := json.Marshal(responseData)
		if err != nil {
			logger.Errorf("[Local Subscribe] Instance: %s, Error marshalling response: %v", *instanceId, err)
			errorResponse := ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to marshal response: %v", err),
			}
			responseContent, _ = json.Marshal(errorResponse)
		}

		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[Local Subscribe] Instance: %s, Error responding to request: %v", *instanceId, err)
		} else {
			logger.Debugf("[Local Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})

	if err != nil {
		logger.Errorf("[Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func SubscribeDownloadToLocal(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.local.%s", *instanceId)
	logger.Infof("[Download Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[Download Local Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[Download Local Subscribe] Instance: %s, No arguments received", *instanceId)
			return
		}

		var downloadRequest utils.DownloadFileRequest
		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			logger.Errorf("[Download Local Subscribe] Instance: %s, Error unmarshalling first arg to DownloadFileRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[Download Local Subscribe] Instance: %s, Starting download from bucket %s, file %s to local path %s", *instanceId, downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		var resp ExecuteResponse

		err := utils.DownloadFile(downloadRequest, nc)
		if err != nil {
			logger.Errorf("[Download Local Subscribe] Instance: %s, Download error: %v", *instanceId, err)
			resp = ExecuteResponse{
				Success:    false,
				Output:     fmt.Sprintf("Failed to download file: %v", err),
				InstanceId: *instanceId,
			}
		} else {
			logger.Debugf("[Download Local Subscribe] Instance: %s, Download completed successfully!", *instanceId)
			resp = ExecuteResponse{
				Success:    true,
				Output:     fmt.Sprintf("File successfully downloaded to %s/%s", downloadRequest.TargetPath, downloadRequest.FileName),
				InstanceId: *instanceId,
			}
		}

		responseContent, _ := json.Marshal(resp)
		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[Download Local Subscribe] Instance: %s, Error responding to download request: %v", *instanceId, err)
		}
	})

	if err != nil {
		logger.Errorf("[Download Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func SubscribeUnzipToLocal(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("unzip.local.%s", *instanceId)
	logger.Infof("[Unzip Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[Unzip Local Subscribe] Instance: %s, No arguments received", *instanceId)
			return
		}

		var unzipRequest utils.UnzipRequest
		if err := json.Unmarshal(incoming.Args[0], &unzipRequest); err != nil {
			logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error unmarshalling first arg to UnzipRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[Unzip Local Subscribe] Instance: %s, Starting unzip from file %s to local path %s", *instanceId, unzipRequest.ZipPath, unzipRequest.DestDir)

		parentDir, err := utils.UnzipToDir(unzipRequest)
		if err != nil {
			logger.Errorf("[Unzip Local Subscribe] Instance: %s, Unzip error: %v", *instanceId, err)
			resp := ExecuteResponse{
				Output:     fmt.Sprintf("Failed to unzip file: %v", err),
				InstanceId: *instanceId,
				Success:    false,
			}
			responseContent, _ := json.Marshal(resp)
			if err := msg.Respond(responseContent); err != nil {
				logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error responding to unzip request: %v", *instanceId, err)
			}
			return
		}

		logger.Debugf("[Unzip Local Subscribe] Instance: %s, Unzip completed successfully! Parent directory: %s", *instanceId, parentDir)
		resp := ExecuteResponse{
			Output:     parentDir,
			InstanceId: *instanceId,
			Success:    true,
		}
		responseContent, _ := json.Marshal(resp)
		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error responding to unzip request: %v", *instanceId, err)
		}
	})

	if err != nil {
		logger.Errorf("[Unzip Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func SubscribeHealthCheck(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("health.check.%s", *instanceId)
	logger.Infof("[Health Check Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Health Check] Received health check request from subject: %s", subject)
		response := HealthCheckResponse{
			Success:    true,
			Status:     "ok",
			InstanceId: *instanceId,
			Timestamp:  time.Now().UTC().Format(time.RFC3339),
		}
		responseContent, _ := json.Marshal(response)
		msg.Respond(responseContent)
		logger.Debugf("[Health Check] Responded with status: ok")
	})

	if err != nil {
		logger.Errorf("[Health Check Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
