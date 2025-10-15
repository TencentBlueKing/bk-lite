package ssh

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/melbahja/goph"
	"github.com/nats-io/nats.go"
	"golang.org/x/crypto/ssh"
	"log"
	"nats-executor/local"
	"nats-executor/utils"
	"time"
)

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	log.Printf("[SSH Execute] Instance: %s, Starting SSH connection to %s@%s:%d", instanceId, req.User, req.Host, req.Port)
	log.Printf("[SSH Execute] Instance: %s, Command: %s, Timeout: %ds", instanceId, req.Command, req.ExecuteTimeout)

	auth := goph.Password(req.Password)
	client, err := goph.NewConn(&goph.Config{
		User:     req.User,
		Addr:     req.Host,
		Port:     req.Port,
		Auth:     auth,
		Timeout:  30 * time.Second,
		Callback: ssh.InsecureIgnoreHostKey(), // 👈 跳过 known_hosts 验证
	})

	if err != nil {
		errMsg := fmt.Sprintf("Failed to create SSH client: %v", err)
		log.Printf("[SSH Execute] Instance: %s, Failed to create SSH client for %s@%s:%d - Error: %v", instanceId, req.User, req.Host, req.Port, err)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     errMsg,
			Error:      errMsg,
		}
	}

	log.Printf("[SSH Execute] Instance: %s, SSH connection established successfully", instanceId)
	defer func() {
		client.Close()
		log.Printf("[SSH Execute] Instance: %s, SSH connection closed", instanceId)
	}()

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	log.Printf("[SSH Execute] Instance: %s, Executing command...", instanceId)
	startTime := time.Now()
	out, err := client.RunContext(ctx, req.Command)
	duration := time.Since(startTime)

	if err != nil {
		var errMsg string
		if ctx.Err() == context.DeadlineExceeded {
			errMsg = fmt.Sprintf("Command timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
			log.Printf("[SSH Execute] Instance: %s, Command timed out after %v (timeout: %ds)", instanceId, duration, req.ExecuteTimeout)
		} else {
			errMsg = fmt.Sprintf("Command execution failed: %v", err)
			log.Printf("[SSH Execute] Instance: %s, Command execution failed after %v - Error: %v", instanceId, duration, err)
		}
		log.Printf("[SSH Execute] Instance: %s, Output: %s", instanceId, string(out))
		return ExecuteResponse{
			Output:     string(out),
			InstanceId: instanceId,
			Success:    false,
			Error:      errMsg,
		}
	}

	log.Printf("[SSH Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
	log.Printf("[SSH Execute] Instance: %s, Output length: %d bytes", instanceId, len(out))

	return ExecuteResponse{
		Output:     string(out),
		InstanceId: instanceId,
		Success:    true,
	}
}

func SubscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	log.Printf("[SSH Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		log.Printf("[SSH Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))

		// 解析 request 的标准结构
		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("[SSH Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("[SSH Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var sshExecuteRequest ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &sshExecuteRequest); err != nil {
			log.Printf("[SSH Subscribe] Instance: %s, Error unmarshalling first arg to ssh.ExecuteRequest: %v", *instanceId, err)
			return
		}

		log.Printf("[SSH Subscribe] Instance: %s, Parsed SSH request for %s@%s:%d", *instanceId, sshExecuteRequest.User, sshExecuteRequest.Host, sshExecuteRequest.Port)
		responseData := Execute(sshExecuteRequest, *instanceId)
		log.Printf("[SSH Subscribe] Instance: %s, SSH execution completed, success: %v", *instanceId, responseData.Success)

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("[SSH Subscribe] Instance: %s, Error responding to SSH request: %v", *instanceId, err)
		} else {
			log.Printf("[SSH Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})
}

func SubscribeDownloadToRemote(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.remote.%s", *instanceId)
	log.Printf("[Download Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		log.Printf("[Download Subscribe] Instance: %s, Received download request, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("[Download Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("[Download Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var downloadRequest DownloadFileRequest

		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			log.Printf("[Download Subscribe] Instance: %s, Error unmarshalling first arg to DownloadFileRequest: %v", *instanceId, err)
			return
		}

		log.Printf("[Download Subscribe] Instance: %s, Starting download from bucket %s, file %s to local path %s", *instanceId, downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		// 下载文件到本地
		localdownloadRequest := utils.DownloadFileRequest{
			BucketName:     downloadRequest.BucketName,
			FileKey:        downloadRequest.FileKey,
			FileName:       downloadRequest.FileName,
			TargetPath:     downloadRequest.TargetPath,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		log.Printf("[Download Subscribe] Instance: %s, Downloading file from S3: %s/%s", *instanceId, downloadRequest.BucketName, downloadRequest.FileKey)
		err := utils.DownloadFile(localdownloadRequest, nc)
		if err != nil {
			log.Printf("[Download Subscribe] Instance: %s, Error downloading file from S3: %v", *instanceId, err)
			return
		}
		log.Printf("[Download Subscribe] Instance: %s, File downloaded successfully to: %s/%s", *instanceId, localdownloadRequest.TargetPath, localdownloadRequest.FileName)

		// 使用sshpass处理带密码的scp传输
		scpCommand := fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -P %d -r %s/%s %s@%s:%s",
			downloadRequest.Password,
			downloadRequest.Port,
			localdownloadRequest.TargetPath,
			localdownloadRequest.FileName,
			downloadRequest.User,
			downloadRequest.Host,
			downloadRequest.TargetPath)

		localExecuteRequest := local.ExecuteRequest{
			Command:        scpCommand,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		log.Printf("[Download Subscribe] Instance: %s, Starting SCP transfer to remote host: %s@%s:%s", *instanceId, downloadRequest.User, downloadRequest.Host, downloadRequest.TargetPath)
		log.Printf("[Download Subscribe] Instance: %s, SCP command: %s", *instanceId, scpCommand)
		responseData := local.Execute(localExecuteRequest, *instanceId)

		if responseData.Success {
			log.Printf("[Download Subscribe] Instance: %s, File transfer to remote host completed successfully", *instanceId)
		} else {
			log.Printf("[Download Subscribe] Instance: %s, File transfer to remote host failed: %s", *instanceId, responseData.Output)
		}

		responseContent, err := json.Marshal(responseData)
		if err != nil {
			log.Printf("[Download Subscribe] Instance: %s, Error marshalling response: %v", *instanceId, err)
			errorResponse := local.ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to marshal response: %v", err),
			}
			responseContent, _ = json.Marshal(errorResponse)
		}

		if err := msg.Respond(responseContent); err != nil {
			log.Printf("[Download Subscribe] Instance: %s, Error responding to download request: %v", *instanceId, err)
		} else {
			log.Printf("[Download Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})
}

func SubscribeUploadToRemote(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("upload.remote.%s", *instanceId)
	log.Printf("[Upload Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		log.Printf("[Upload Subscribe] Instance: %s, Received upload request, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			log.Printf("[Upload Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			log.Printf("[Upload Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var uploadRequest UploadFileRequest

		if err := json.Unmarshal(incoming.Args[0], &uploadRequest); err != nil {
			log.Printf("[Upload Subscribe] Instance: %s, Error unmarshalling first arg to UploadFileRequest: %v", *instanceId, err)
			return
		}

		log.Printf("[Upload Subscribe] Instance: %s, Starting upload from local path %s to remote host %s@%s:%s", *instanceId, uploadRequest.SourcePath, uploadRequest.User, uploadRequest.Host, uploadRequest.TargetPath)

		// 使用sshpass处理带密码的scp传输
		scpCommand := fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -P %d -r %s %s@%s:%s",
			uploadRequest.Password,
			uploadRequest.Port,
			uploadRequest.SourcePath,
			uploadRequest.User,
			uploadRequest.Host,
			uploadRequest.TargetPath)

		localExecuteRequest := local.ExecuteRequest{
			Command:        scpCommand,
			ExecuteTimeout: uploadRequest.ExecuteTimeout,
		}

		log.Printf("[Upload Subscribe] Instance: %s, Executing SCP command to upload file", *instanceId)
		log.Printf("[Upload Subscribe] Instance: %s, SCP command: %s", *instanceId, scpCommand)
		responseData := local.Execute(localExecuteRequest, *instanceId)

		if responseData.Success {
			log.Printf("[Upload Subscribe] Instance: %s, File upload to remote host completed successfully", *instanceId)
		} else {
			log.Printf("[Upload Subscribe] Instance: %s, File upload to remote host failed: %s", *instanceId, responseData.Output)
		}

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			log.Printf("[Upload Subscribe] Instance: %s, Error responding to upload request: %v", *instanceId, err)
		} else {
			log.Printf("[Upload Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})
}
