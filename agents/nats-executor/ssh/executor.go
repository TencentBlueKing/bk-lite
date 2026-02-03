package ssh

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"nats-executor/local"
	"nats-executor/logger"
	"nats-executor/utils"
	"os"
	"path/filepath"
	"time"

	"github.com/nats-io/nats.go"
	"golang.org/x/crypto/ssh"
)

func buildSCPCommand(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool) (string, func(), error) {
	var cleanup func()
	var scpCommand string

	if privateKey != "" {
		tmpDir := os.TempDir()
		keyFile := filepath.Join(tmpDir, fmt.Sprintf("ssh_key_%d", time.Now().UnixNano()))

		if err := os.WriteFile(keyFile, []byte(privateKey), 0600); err != nil {
			return "", nil, fmt.Errorf("failed to write private key to temp file: %v", err)
		}

		cleanup = func() {
			os.Remove(keyFile)
			logger.Debugf("[SCP] Cleaned up temporary key file: %s", keyFile)
		}

		if isUpload {
			scpCommand = fmt.Sprintf("scp -i %s -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s %s@%s:%s",
				keyFile, port, sourcePath, user, host, targetPath)
		} else {
			scpCommand = fmt.Sprintf("scp -i %s -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s %s@%s:%s",
				keyFile, port, sourcePath, user, host, targetPath)
		}

		logger.Debugf("[SCP] Using private key authentication")
	} else if password != "" {
		cleanup = func() {}

		if isUpload {
			scpCommand = fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s %s@%s:%s",
				password, port, sourcePath, user, host, targetPath)
		} else {
			scpCommand = fmt.Sprintf("sshpass -p '%s' scp -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa,ssh-dss -o PubkeyAcceptedKeyTypes=+ssh-rsa,ssh-dss -P %d -r %s %s@%s:%s",
				password, port, sourcePath, user, host, targetPath)
		}

		logger.Debugf("[SCP] Using password authentication")
	} else {
		return "", nil, fmt.Errorf("no authentication method provided (password or private key required)")
	}

	return scpCommand, cleanup, nil
}

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	logger.Debugf("[SSH Execute] Instance: %s, Starting SSH connection to %s@%s:%d", instanceId, req.User, req.Host, req.Port)
	logger.Debugf("[SSH Execute] Instance: %s, Command: %s, Timeout: %ds", instanceId, req.Command, req.ExecuteTimeout)

	var authMethods []ssh.AuthMethod

	if req.PrivateKey != "" {
		var signer ssh.Signer
		var err error

		if req.Passphrase != "" {
			signer, err = ssh.ParsePrivateKeyWithPassphrase([]byte(req.PrivateKey), []byte(req.Passphrase))
		} else {
			signer, err = ssh.ParsePrivateKey([]byte(req.PrivateKey))
		}

		if err != nil {
			errMsg := fmt.Sprintf("Failed to parse private key: %v", err)
			logger.Errorf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
			return ExecuteResponse{
				InstanceId: instanceId,
				Success:    false,
				Output:     errMsg,
				Error:      errMsg,
			}
		}
		authMethods = append(authMethods, ssh.PublicKeys(signer))
		logger.Debugf("[SSH Execute] Instance: %s, Using public key authentication", instanceId)
	}

	if req.Password != "" {
		authMethods = append(authMethods, ssh.Password(req.Password))
		logger.Debugf("[SSH Execute] Instance: %s, Password authentication enabled", instanceId)
	}

	if len(authMethods) == 0 {
		errMsg := "No authentication method provided (password or private key required)"
		logger.Errorf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     errMsg,
			Error:      errMsg,
		}
	}

	sshConfig := &ssh.ClientConfig{
		User:            req.User,
		Auth:            authMethods,
		Timeout:         30 * time.Second,
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		HostKeyAlgorithms: []string{
			ssh.KeyAlgoRSA,
			ssh.KeyAlgoDSA,
			ssh.KeyAlgoECDSA256,
			ssh.KeyAlgoECDSA384,
			ssh.KeyAlgoECDSA521,
			ssh.KeyAlgoED25519,
			"ssh-rsa",
			"ssh-dss",
			"rsa-sha2-256",
			"rsa-sha2-512",
		},
	}

	addr := fmt.Sprintf("%s:%d", req.Host, req.Port)
	client, err := ssh.Dial("tcp", addr, sshConfig)
	if err != nil {
		errMsg := fmt.Sprintf("Failed to create SSH client: %v", err)
		logger.Errorf("[SSH Execute] Instance: %s, Failed to create SSH client for %s@%s:%d - Error: %v", instanceId, req.User, req.Host, req.Port, err)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     errMsg,
			Error:      errMsg,
		}
	}

	logger.Debugf("[SSH Execute] Instance: %s, SSH connection established successfully", instanceId)
	defer func() {
		client.Close()
		logger.Debugf("[SSH Execute] Instance: %s, SSH connection closed", instanceId)
	}()

	session, err := client.NewSession()
	if err != nil {
		errMsg := fmt.Sprintf("Failed to create SSH session: %v", err)
		logger.Errorf("[SSH Execute] Instance: %s, Failed to create SSH session - Error: %v", instanceId, err)
		return ExecuteResponse{
			InstanceId: instanceId,
			Success:    false,
			Output:     errMsg,
			Error:      errMsg,
		}
	}
	defer session.Close()

	var stdout, stderr bytes.Buffer
	session.Stdout = &stdout
	session.Stderr = &stderr

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	logger.Debugf("[SSH Execute] Instance: %s, Executing command...", instanceId)
	startTime := time.Now()

	errChan := make(chan error, 1)
	go func() {
		errChan <- session.Run(req.Command)
	}()

	select {
	case <-ctx.Done():
		duration := time.Since(startTime)
		errMsg := fmt.Sprintf("Command timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
		logger.Warnf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
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
			logger.Warnf("[SSH Execute] Instance: %s, Command execution failed after %v - Error: %v", instanceId, duration, err)
			logger.Debugf("[SSH Execute] Instance: %s, Output: %s", instanceId, output)
			return ExecuteResponse{
				Output:     output,
				InstanceId: instanceId,
				Success:    false,
				Error:      errMsg,
			}
		}

		logger.Debugf("[SSH Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		logger.Debugf("[SSH Execute] Instance: %s, Output length: %d bytes", instanceId, len(output))

		return ExecuteResponse{
			Output:     output,
			InstanceId: instanceId,
			Success:    true,
		}
	}
}

func SubscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	logger.Infof("[SSH Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[SSH Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[SSH Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[SSH Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var sshExecuteRequest ExecuteRequest
		if err := json.Unmarshal(incoming.Args[0], &sshExecuteRequest); err != nil {
			logger.Errorf("[SSH Subscribe] Instance: %s, Error unmarshalling first arg to ssh.ExecuteRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[SSH Subscribe] Instance: %s, Parsed SSH request for %s@%s:%d", *instanceId, sshExecuteRequest.User, sshExecuteRequest.Host, sshExecuteRequest.Port)
		responseData := Execute(sshExecuteRequest, *instanceId)
		logger.Debugf("[SSH Subscribe] Instance: %s, SSH execution completed, success: %v", *instanceId, responseData.Success)

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[SSH Subscribe] Instance: %s, Error responding to SSH request: %v", *instanceId, err)
		} else {
			logger.Debugf("[SSH Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})

	if err != nil {
		logger.Errorf("[SSH Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func SubscribeDownloadToRemote(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("download.remote.%s", *instanceId)
	logger.Infof("[Download Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Download Subscribe] Instance: %s, Received download request, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[Download Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var downloadRequest DownloadFileRequest

		if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error unmarshalling first arg to DownloadFileRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[Download Subscribe] Instance: %s, Starting download from bucket %s, file %s to local path %s", *instanceId, downloadRequest.BucketName, downloadRequest.FileKey, downloadRequest.TargetPath)

		localdownloadRequest := utils.DownloadFileRequest{
			BucketName:     downloadRequest.BucketName,
			FileKey:        downloadRequest.FileKey,
			FileName:       downloadRequest.FileName,
			TargetPath:     downloadRequest.TargetPath,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		logger.Debugf("[Download Subscribe] Instance: %s, Downloading file from S3: %s/%s", *instanceId, downloadRequest.BucketName, downloadRequest.FileKey)
		err := utils.DownloadFile(localdownloadRequest, nc)
		if err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error downloading file from S3: %v", *instanceId, err)
			return
		}
		logger.Debugf("[Download Subscribe] Instance: %s, File downloaded successfully to: %s/%s", *instanceId, localdownloadRequest.TargetPath, localdownloadRequest.FileName)

		sourcePath := fmt.Sprintf("%s/%s", localdownloadRequest.TargetPath, localdownloadRequest.FileName)
		scpCommand, cleanup, err := buildSCPCommand(
			downloadRequest.User,
			downloadRequest.Host,
			downloadRequest.Password,
			downloadRequest.PrivateKey,
			downloadRequest.Port,
			sourcePath,
			downloadRequest.TargetPath,
			true,
		)

		if cleanup != nil {
			defer cleanup()
		}

		if err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error building SCP command: %v", *instanceId, err)
			errorResponse := local.ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to build SCP command: %v", err),
			}
			responseContent, _ := json.Marshal(errorResponse)
			msg.Respond(responseContent)
			return
		}

		localExecuteRequest := local.ExecuteRequest{
			Command:        scpCommand,
			ExecuteTimeout: downloadRequest.ExecuteTimeout,
		}

		logger.Debugf("[Download Subscribe] Instance: %s, Starting SCP transfer to remote host: %s@%s:%s", *instanceId, downloadRequest.User, downloadRequest.Host, downloadRequest.TargetPath)
		logger.Debugf("[Download Subscribe] Instance: %s, SCP command: %s", *instanceId, scpCommand)
		responseData := local.Execute(localExecuteRequest, *instanceId)

		if responseData.Success {
			logger.Debugf("[Download Subscribe] Instance: %s, File transfer to remote host completed successfully", *instanceId)
		} else {
			logger.Warnf("[Download Subscribe] Instance: %s, File transfer to remote host failed", *instanceId)
			logger.Debugf("[Download Subscribe] Instance: %s, Failure output: %s", *instanceId, responseData.Output)
		}

		responseContent, err := json.Marshal(responseData)
		if err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error marshalling response: %v", *instanceId, err)
			errorResponse := local.ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to marshal response: %v", err),
			}
			responseContent, _ = json.Marshal(errorResponse)
		}

		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[Download Subscribe] Instance: %s, Error responding to download request: %v", *instanceId, err)
		} else {
			logger.Debugf("[Download Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})
}

func SubscribeUploadToRemote(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("upload.remote.%s", *instanceId)
	logger.Infof("[Upload Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Upload Subscribe] Instance: %s, Received upload request, size: %d bytes", *instanceId, len(msg.Data))

		var incoming struct {
			Args   []json.RawMessage      `json:"args"`
			Kwargs map[string]interface{} `json:"kwargs"`
		}

		if err := json.Unmarshal(msg.Data, &incoming); err != nil {
			logger.Errorf("[Upload Subscribe] Instance: %s, Error unmarshalling incoming message: %v", *instanceId, err)
			return
		}

		if len(incoming.Args) == 0 {
			logger.Warnf("[Upload Subscribe] Instance: %s, No arguments received in message", *instanceId)
			return
		}

		var uploadRequest UploadFileRequest

		if err := json.Unmarshal(incoming.Args[0], &uploadRequest); err != nil {
			logger.Errorf("[Upload Subscribe] Instance: %s, Error unmarshalling first arg to UploadFileRequest: %v", *instanceId, err)
			return
		}

		logger.Debugf("[Upload Subscribe] Instance: %s, Starting upload from local path %s to remote host %s@%s:%s", *instanceId, uploadRequest.SourcePath, uploadRequest.User, uploadRequest.Host, uploadRequest.TargetPath)

		scpCommand, cleanup, err := buildSCPCommand(
			uploadRequest.User,
			uploadRequest.Host,
			uploadRequest.Password,
			uploadRequest.PrivateKey,
			uploadRequest.Port,
			uploadRequest.SourcePath,
			uploadRequest.TargetPath,
			true,
		)

		if cleanup != nil {
			defer cleanup()
		}

		if err != nil {
			logger.Errorf("[Upload Subscribe] Instance: %s, Error building SCP command: %v", *instanceId, err)
			errorResponse := local.ExecuteResponse{
				InstanceId: *instanceId,
				Success:    false,
				Error:      fmt.Sprintf("Failed to build SCP command: %v", err),
			}
			responseContent, _ := json.Marshal(errorResponse)
			msg.Respond(responseContent)
			return
		}

		localExecuteRequest := local.ExecuteRequest{
			Command:        scpCommand,
			ExecuteTimeout: uploadRequest.ExecuteTimeout,
		}

		logger.Debugf("[Upload Subscribe] Instance: %s, Executing SCP command to upload file", *instanceId)
		logger.Debugf("[Upload Subscribe] Instance: %s, SCP command: %s", *instanceId, scpCommand)
		responseData := local.Execute(localExecuteRequest, *instanceId)

		if responseData.Success {
			logger.Debugf("[Upload Subscribe] Instance: %s, File upload to remote host completed successfully", *instanceId)
		} else {
			logger.Warnf("[Upload Subscribe] Instance: %s, File upload to remote host failed", *instanceId)
			logger.Debugf("[Upload Subscribe] Instance: %s, Failure output: %s", *instanceId, responseData.Output)
		}

		responseContent, _ := json.Marshal(responseData)
		if err := msg.Respond(responseContent); err != nil {
			logger.Errorf("[Upload Subscribe] Instance: %s, Error responding to upload request: %v", *instanceId, err)
		} else {
			logger.Debugf("[Upload Subscribe] Instance: %s, Response sent successfully, size: %d bytes", *instanceId, len(responseContent))
		}
	})

	if err != nil {
		logger.Errorf("[Upload Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
