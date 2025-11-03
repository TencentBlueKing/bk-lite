package local

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/nats-io/nats.go"
	"log"
	"nats-executor/utils"
	"os/exec"
	"time"
)

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	log.Printf("[Local Execute] Instance: %s, Starting command execution", instanceId)
	log.Printf("[Local Execute] Instance: %s, Command: %s", instanceId, req.Command)
	log.Printf("[Local Execute] Instance: %s, Timeout: %ds", instanceId, req.ExecuteTimeout)

	// Execute the command with timeout
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "sh", "-c", req.Command)

	// 记录命令开始执行时间
	startTime := time.Now()
	output, err := cmd.CombinedOutput()
	duration := time.Since(startTime)

	// 获取退出代码
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
		log.Printf("[Local Execute] Instance: %s, Command timed out after %v (timeout: %ds)", instanceId, duration, req.ExecuteTimeout)
		log.Printf("[Local Execute] Instance: %s, Partial output: %s", instanceId, string(output))
	} else if err != nil {
		response.Error = fmt.Sprintf("Command execution failed with exit code %d: %v", exitCode, err)
		log.Printf("[Local Execute] Instance: %s, Command execution failed after %v", instanceId, duration)
		log.Printf("[Local Execute] Instance: %s, Exit code: %d", instanceId, exitCode)
		log.Printf("[Local Execute] Instance: %s, Error: %v", instanceId, err)
		log.Printf("[Local Execute] Instance: %s, Full output: %s", instanceId, string(output))

		// 特别针对SCP命令的错误分析
		if contains(req.Command, "scp") || contains(req.Command, "sshpass") {
			log.Printf("[Local Execute] Instance: %s, SCP Command detected - analyzing failure...", instanceId)
			analyzeSCPFailure(instanceId, string(output), exitCode)
		}
	} else {
		log.Printf("[Local Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		log.Printf("[Local Execute] Instance: %s, Output length: %d bytes", instanceId, len(output))
		if len(output) > 0 {
			log.Printf("[Local Execute] Instance: %s, Output: %s", instanceId, string(output))
		}
	}

	return response
}

// 辅助函数：检查字符串是否包含子字符串
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

// SCP失败分析函数
func analyzeSCPFailure(instanceId, output string, exitCode int) {
	log.Printf("[SCP Analysis] Instance: %s, Analyzing SCP failure with exit code: %d", instanceId, exitCode)

	switch exitCode {
	case 1:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 1 - General error", instanceId)
		if contains(output, "Permission denied") {
			log.Printf("[SCP Analysis] Instance: %s, Issue: Permission denied - Check SSH credentials/key", instanceId)
		} else if contains(output, "Connection refused") {
			log.Printf("[SCP Analysis] Instance: %s, Issue: Connection refused - Check if SSH service is running", instanceId)
		} else if contains(output, "No such file or directory") {
			log.Printf("[SCP Analysis] Instance: %s, Issue: File/directory not found - Check source/target paths", instanceId)
		} else if contains(output, "Host key verification failed") {
			log.Printf("[SCP Analysis] Instance: %s, Issue: Host key verification failed - SSH host key problem", instanceId)
		}
	case 2:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 2 - Protocol error", instanceId)
	case 3:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 3 - Interrupted", instanceId)
	case 4:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 4 - Unexpected network error", instanceId)
	case 5:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 5 - sshpass authentication failure", instanceId)
		log.Printf("[SCP Analysis] Instance: %s, Issue: Wrong password or sshpass not available", instanceId)
	case 6:
		log.Printf("[SCP Analysis] Instance: %s, Exit code 6 - sshpass host key unknown", instanceId)
	default:
		log.Printf("[SCP Analysis] Instance: %s, Exit code %d - Unknown error", instanceId, exitCode)
	}

	// 检查常见的错误模式
	if contains(output, "sshpass: command not found") {
		log.Printf("[SCP Analysis] Instance: %s, CRITICAL: sshpass is not installed on the system", instanceId)
	}
	if contains(output, "ssh: connect to host") && contains(output, "Connection timed out") {
		log.Printf("[SCP Analysis] Instance: %s, Issue: Network connectivity problem or wrong hostname/port", instanceId)
	}
	if contains(output, "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED") {
		log.Printf("[SCP Analysis] Instance: %s, Issue: Remote host key has changed - security risk", instanceId)
	}
}

func SubscribeLocalExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("local.execute.%s", *instanceId)
	log.Printf("[Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		log.Printf("[Local Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))

		// 定义一个临时结构来接收请求方格式
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("[Local Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("[Local Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var localExecuteRequest ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &localExecuteRequest); err != nil {
			log.Printf("[Local Subscribe] Instance: %s, Error unmarshalling first arg to local.ExecuteRequest: %v", *instanceId, err)
			return
		}

		log.Printf("[Local Subscribe] Instance: %s, Parsed command request", *instanceId)
		responseData := Execute(localExecuteRequest, *instanceId)
		log.Printf("[Local Subscribe] Instance: %s, Command execution completed, success: %v", *instanceId, responseData.Success)

		responseContent, err := json.Marshal(responseData)
		if err != nil {
			log.Printf("[Local Subscribe] Instance: %s, Error marshalling response: %v", *instanceId, err)
			// 发送一个错误响应
			errorResponse := ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to marshal response: %v", err),
			}
			responseContent, _ = json.Marshal(errorResponse)
		}

		if err := msg.Respond(responseContent); err != nil {
			log.Printf("[Local Subscribe] Instance: %s, Error responding to request: %v", *instanceId, err)
		} else {
			log.Printf("[Local Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})

	if err != nil {
		log.Printf("[Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func SubscribeDownloadToLocal(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.local.%s", *instanceId)
	//log.Printf("Subscribing to subject: %s", subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}

		var downloadRequest utils.DownloadFileRequest
		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			log.Printf("Error unmarshalling first arg to DownloadFileRequest: %v", err)
			return
		}

		//log.Printf("Starting download from bucket %s, file %s to local path %s", downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		var resp ExecuteResponse

		err := utils.DownloadFile(downloadRequest, nc)
		if err != nil {
			log.Printf("Download error: %v", err)
			resp = ExecuteResponse{
				Success:    false,
				Output:     fmt.Sprintf("Failed to download file: %v", err),
				InstanceId: *instanceId,
			}

		} else {
			log.Println("Download completed successfully!")
			resp = ExecuteResponse{
				Success:    true,
				Output:     fmt.Sprintf("File successfully downloaded to %s/%s", downloadRequest.TargetPath, downloadRequest.FileName),
				InstanceId: *instanceId,
			}
		}

		responseContent, _ := json.Marshal(resp)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error responding to download request: %v", err)
		}
	})
}

func SubscribeUnzipToLocal(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("unzip.local.%s", *instanceId)
	//log.Printf("Subscribing to subject: %s", subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("Error unmarshalling incoming message: %v", err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("No arguments received")
			return
		}

		var unzipRequest utils.UnzipRequest
		if err := json.Unmarshal(incoming.Args[0], &unzipRequest); err != nil {
			log.Printf("Error unmarshalling first arg to UnzipRequest: %v", err)
			return
		}

		log.Printf("Starting unzip from file %s to local path %s", unzipRequest.ZipPath, unzipRequest.DestDir)

		// 修复调用 UnzipToDir 的参数问题
		parentDir, err := utils.UnzipToDir(unzipRequest)
		if err != nil {
			log.Printf("Unzip error: %v", err)
			resp := ExecuteResponse{
				Output:     fmt.Sprintf("Failed to unzip file: %v", err),
				InstanceId: *instanceId,
				Success:    false,
			}
			responseContent, _ := json.Marshal(resp)
			if err := msg.Respond(responseContent); err != nil {
				log.Printf("Error responding to unzip request: %v", err)
			}
			return
		}

		log.Printf("Unzip completed successfully! Parent directory: %s", parentDir)
		resp := ExecuteResponse{
			Output:     parentDir,
			InstanceId: *instanceId,
			Success:    true,
		}
		responseContent, _ := json.Marshal(resp)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("Error responding to unzip request: %v", err)
		}
	})

	if err != nil {
		log.Printf("[Unzip Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
