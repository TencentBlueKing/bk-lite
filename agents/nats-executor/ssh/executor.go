package ssh

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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

	// 配置 SSH 客户端，支持旧版和新版加密算法
	sshConfig := &ssh.ClientConfig{
		User:            req.User,
		Auth:            []ssh.AuthMethod{ssh.Password(req.Password)},
		Timeout:         30 * time.Second,
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		// 支持多种主机密钥算法，包括旧版的 ssh-rsa 和 ssh-dss
		HostKeyAlgorithms: []string{
			ssh.KeyAlgoRSA,      // 现代 RSA
			ssh.KeyAlgoDSA,      // DSA
			ssh.KeyAlgoECDSA256, // ECDSA 256
			ssh.KeyAlgoECDSA384, // ECDSA 384
			ssh.KeyAlgoECDSA521, // ECDSA 521
			ssh.KeyAlgoED25519,  // ED25519
			"ssh-rsa",           // 旧版 RSA（兼容老服务器）
			"ssh-dss",           // 旧版 DSS（兼容老服务器）
			"rsa-sha2-256",      // RSA SHA2-256
			"rsa-sha2-512",      // RSA SHA2-512
		},
	}

	// 连接 SSH 服务器
	addr := fmt.Sprintf("%s:%d", req.Host, req.Port)
	client, err := ssh.Dial("tcp", addr, sshConfig)
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

	// 创建 SSH 会话
	session, err := client.NewSession()
	if err != nil {
		errMsg := fmt.Sprintf("Failed to create SSH session: %v", err)
		log.Printf("[SSH Execute] Instance: %s, Failed to create SSH session - Error: %v", instanceId, err)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     errMsg,
			Error:      errMsg,
		}
	}
	defer session.Close()

	// 设置输出缓冲区
	var stdout, stderr bytes.Buffer
	session.Stdout = &stdout
	session.Stderr = &stderr

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	log.Printf("[SSH Execute] Instance: %s, Executing command...", instanceId)
	startTime := time.Now()

	// 在 goroutine 中执行命令以支持超时
	errChan := make(chan error, 1)
	go func() {
		errChan <- session.Run(req.Command)
	}()

	select {
	case <-ctx.Done():
		duration := time.Since(startTime)
		errMsg := fmt.Sprintf("Command timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
		log.Printf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
		session.Signal(ssh.SIGKILL)
		return ExecuteResponse{
			Output:     stdout.String() + stderr.String(),
			InstanceId: instanceId,
			Success:    false,
			Error:      errMsg,
		}
	case err := <-errChan:
		duration := time.Since(startTime)
		output := stdout.String()
		if stderr.Len() > 0 {
			output += stderr.String()
		}

		if err != nil {
			errMsg := fmt.Sprintf("Command execution failed: %v", err)
			log.Printf("[SSH Execute] Instance: %s, Command execution failed after %v - Error: %v", instanceId, duration, err)
			log.Printf("[SSH Execute] Instance: %s, Output: %s", instanceId, output)
			return ExecuteResponse{
				Output:     output,
				InstanceId: instanceId,
				Success:    false,
				Error:      errMsg,
			}
		}

		log.Printf("[SSH Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		log.Printf("[SSH Execute] Instance: %s, Output length: %d bytes", instanceId, len(output))

		return ExecuteResponse{
			Output:     output,
			InstanceId: instanceId,
			Success:    true,
		}
	}
}

func SubscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	log.Printf("[SSH Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
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

	if err != nil {
		log.Printf("[SSH Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
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

		// 使用 sshpass 处理带密码的 scp 传输，添加对旧版 SSH 服务器的支持
		scpCommand := fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s/%s %s@%s:%s",
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

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
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

		// 使用 sshpass 处理带密码的 scp 传输，添加对旧版 SSH 服务器的支持
		scpCommand := fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s %s@%s:%s",
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

	if err != nil {
		log.Printf("[Upload Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
