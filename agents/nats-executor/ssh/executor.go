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
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"golang.org/x/crypto/ssh"
)

var sshpassPasswordPattern = regexp.MustCompile(`sshpass -p '(?:[^']|'"'"')*'`)

type sshConn interface{}
type responseMsg interface {
	Respond([]byte) error
}

type sshClient interface {
	NewSession() (sshSession, error)
	Close() error
}

type sshSession interface {
	Run(cmd string) error
	Signal(sig ssh.Signal) error
	Close() error
	SetStdout(w *bytes.Buffer)
	SetStderr(w *bytes.Buffer)
}

type realSSHClient struct{ client *ssh.Client }
type realSSHSession struct{ session *ssh.Session }

var (
	executeSSHCommand       = Execute
	downloadFromObjectStore = func(req utils.DownloadFileRequest, nc sshConn) error {
		natsConn, _ := nc.(*nats.Conn)
		return utils.DownloadFile(req, natsConn)
	}
	buildSCPCommandFn               = buildSCPCommand
	executeSCPCommand               = executeSCPWithFallback
	executeLocalSCPCommand          = local.Execute
	parsePrivateKeyFn               = ssh.ParsePrivateKey
	parsePrivateKeyWithPassphraseFn = ssh.ParsePrivateKeyWithPassphrase
	sshDialFn                       = func(network, addr string, config *ssh.ClientConfig) (sshClient, error) {
		client, err := ssh.Dial(network, addr, config)
		if err != nil {
			return nil, err
		}
		return realSSHClient{client: client}, nil
	}
)

func (c realSSHClient) NewSession() (sshSession, error) {
	session, err := c.client.NewSession()
	if err != nil {
		return nil, err
	}
	return realSSHSession{session: session}, nil
}

func (c realSSHClient) Close() error { return c.client.Close() }

func (s realSSHSession) Run(cmd string) error        { return s.session.Run(cmd) }
func (s realSSHSession) Signal(sig ssh.Signal) error { return s.session.Signal(sig) }
func (s realSSHSession) Close() error                { return s.session.Close() }
func (s realSSHSession) SetStdout(w *bytes.Buffer)   { s.session.Stdout = w }
func (s realSSHSession) SetStderr(w *bytes.Buffer)   { s.session.Stderr = w }

type incomingMessage struct {
	Args   []json.RawMessage `json:"args"`
	Kwargs map[string]any    `json:"kwargs"`
}

func decodeIncomingMessage(data []byte) (*incomingMessage, bool) {
	var incoming incomingMessage
	if err := json.Unmarshal(data, &incoming); err != nil {
		return nil, false
	}
	if len(incoming.Args) == 0 {
		return nil, false
	}
	return &incoming, true
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}

	return "'" + strings.ReplaceAll(value, "'", `'"'"'`) + "'"
}

func shellQuoteRemoteTarget(user, host, targetPath string) string {
	return shellQuote(fmt.Sprintf("%s@%s:%s", user, host, targetPath))
}

func redactSensitiveCommand(command string) string {
	return sshpassPasswordPattern.ReplaceAllString(command, "sshpass -p '***'")
}

func handleSSHExecuteMessage(data []byte, instanceId string) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	var sshExecuteRequest ExecuteRequest
	if err := json.Unmarshal(incoming.Args[0], &sshExecuteRequest); err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	responseData := executeSSHCommand(sshExecuteRequest, instanceId)
	responseContent, _ := json.Marshal(responseData)
	return responseContent, true
}

func handleDownloadToRemoteMessage(data []byte, instanceId string, nc sshConn) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	var downloadRequest DownloadFileRequest
	if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	localTargetPath := downloadRequest.LocalPath
	if localTargetPath == "" {
		localTargetPath = "/tmp"
	}

	localdownloadRequest := utils.DownloadFileRequest{
		BucketName:     downloadRequest.BucketName,
		FileKey:        downloadRequest.FileKey,
		FileName:       downloadRequest.FileName,
		TargetPath:     localTargetPath,
		ExecuteTimeout: downloadRequest.ExecuteTimeout,
	}

	if err := downloadFromObjectStore(localdownloadRequest, nc); err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeDependencyFailure, fmt.Sprintf("Failed to download file: %v", err)), true
	}

	sourcePath := fmt.Sprintf("%s/%s", localdownloadRequest.TargetPath, localdownloadRequest.FileName)
	scpCommand, cleanup, err := buildSCPCommandFn(
		downloadRequest.User,
		downloadRequest.Host,
		downloadRequest.Password,
		downloadRequest.PrivateKey,
		downloadRequest.Port,
		sourcePath,
		downloadRequest.TargetPath,
		true,
		profileModern,
	)
	if cleanup != nil {
		defer cleanup()
	}
	if err != nil {
		logger.Errorf("[SCP Transfer] Instance: %s, build_failed | download %s@%s:%d %s -> %s | error=%v", instanceId, downloadRequest.User, downloadRequest.Host, downloadRequest.Port, sourcePath, downloadRequest.TargetPath, err)
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to build SCP command: %v", err)), true
	}

	sourceMeta := describeTransferSource(sourcePath)
	logContext := buildTransferLogContext("download", downloadRequest.Host, downloadRequest.Port, downloadRequest.User, sourcePath, downloadRequest.TargetPath, transferAuthMethod(downloadRequest.Password, downloadRequest.PrivateKey), sourceMeta)
	logger.Debugf("[SCP] Instance: %s, prepared | %s | timeout=%ds | command=%s", instanceId, logContext, downloadRequest.ExecuteTimeout, redactSensitiveCommand(scpCommand))

	localExecuteRequest := local.ExecuteRequest{
		Command:        scpCommand,
		LogCommand:     redactSensitiveCommand(scpCommand),
		LogContext:     logContext,
		ExecuteTimeout: downloadRequest.ExecuteTimeout,
	}

	responseData := executeSCPCommand(instanceId, localExecuteRequest)
	responseContent, err := json.Marshal(responseData)
	if err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to marshal response: %v", err)), true
	}

	return responseContent, true
}

func handleUploadToRemoteMessage(data []byte, instanceId string) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	var uploadRequest UploadFileRequest
	if err := json.Unmarshal(incoming.Args[0], &uploadRequest); err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	scpCommand, cleanup, err := buildSCPCommandFn(
		uploadRequest.User,
		uploadRequest.Host,
		uploadRequest.Password,
		uploadRequest.PrivateKey,
		uploadRequest.Port,
		uploadRequest.SourcePath,
		uploadRequest.TargetPath,
		true,
		profileModern,
	)
	if cleanup != nil {
		defer cleanup()
	}
	if err != nil {
		logger.Errorf("[SCP Transfer] Instance: %s, build_failed | upload %s@%s:%d %s -> %s | error=%v", instanceId, uploadRequest.User, uploadRequest.Host, uploadRequest.Port, uploadRequest.SourcePath, uploadRequest.TargetPath, err)
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to build SCP command: %v", err)), true
	}

	sourceMeta := describeTransferSource(uploadRequest.SourcePath)
	logContext := buildTransferLogContext("upload", uploadRequest.Host, uploadRequest.Port, uploadRequest.User, uploadRequest.SourcePath, uploadRequest.TargetPath, transferAuthMethod(uploadRequest.Password, uploadRequest.PrivateKey), sourceMeta)
	logger.Debugf("[SCP] Instance: %s, prepared | %s | timeout=%ds | command=%s", instanceId, logContext, uploadRequest.ExecuteTimeout, redactSensitiveCommand(scpCommand))

	localExecuteRequest := local.ExecuteRequest{
		Command:        scpCommand,
		LogCommand:     redactSensitiveCommand(scpCommand),
		LogContext:     logContext,
		ExecuteTimeout: uploadRequest.ExecuteTimeout,
	}

	responseData := executeSCPCommand(instanceId, localExecuteRequest)
	responseContent, _ := json.Marshal(responseData)
	return responseContent, true
}

func respondSSHExecuteMessage(msg responseMsg, data []byte, instanceId string) bool {
	responseContent, ok := handleSSHExecuteMessage(data, instanceId)
	if !ok {
		logger.Errorf("[SSH Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[SSH Subscribe] Instance: %s, Error responding to SSH request: %v", instanceId, err)
		return false
	}
	logger.Debugf("[SSH Subscribe] Instance: %s, Response sent successfully, size: %d bytes", instanceId, len(responseContent))
	return true
}

func buildSCPCommand(user, host, password, privateKey string, port uint, sourcePath, targetPath string, isUpload bool, profile sshCompatibilityProfile) (string, func(), error) {
	var cleanup func()
	var scpCommand string
	sshOptions := scpOptionFlags(profile)

	if privateKey != "" {
		tmpDir := os.TempDir()
		tempFile, err := os.CreateTemp(tmpDir, "ssh_key_*")
		if err != nil {
			return "", nil, fmt.Errorf("failed to create temporary key file: %v", err)
		}
		keyFile := tempFile.Name()

		if _, err := tempFile.Write([]byte(privateKey)); err != nil {
			tempFile.Close()
			os.Remove(keyFile)
			return "", nil, fmt.Errorf("failed to write private key to temp file: %v", err)
		}
		if err := tempFile.Close(); err != nil {
			os.Remove(keyFile)
			return "", nil, fmt.Errorf("failed to close temporary key file: %v", err)
		}
		if err := os.Chmod(keyFile, 0600); err != nil {
			os.Remove(keyFile)
			return "", nil, fmt.Errorf("failed to set private key permissions: %v", err)
		}

		cleanup = func() {
			os.Remove(keyFile)
			logger.Debugf("[SCP] Cleaned up temporary key file: %s", keyFile)
		}

		if isUpload {
			scpCommand = fmt.Sprintf("scp -i %s %s -P %d -r %s %s",
				shellQuote(keyFile), sshOptions, port, shellQuote(sourcePath), shellQuoteRemoteTarget(user, host, targetPath))
		} else {
			scpCommand = fmt.Sprintf("scp -i %s %s -P %d -r %s %s",
				shellQuote(keyFile), sshOptions, port, shellQuoteRemoteTarget(user, host, targetPath), shellQuote(sourcePath))
		}

		logger.Debugf("[SCP] Using private key authentication with profile=%s", profile)
	} else if password != "" {
		cleanup = func() {}

		if isUpload {
			scpCommand = fmt.Sprintf("sshpass -p %s scp %s -P %d -r %s %s",
				shellQuote(password), sshOptions, port, shellQuote(sourcePath), shellQuoteRemoteTarget(user, host, targetPath))
		} else {
			scpCommand = fmt.Sprintf("sshpass -p %s scp %s -P %d -r %s %s",
				shellQuote(password), sshOptions, port, shellQuoteRemoteTarget(user, host, targetPath), shellQuote(sourcePath))
		}

		logger.Debugf("[SCP] Using password authentication with profile=%s", profile)
	} else {
		return "", nil, fmt.Errorf("no authentication method provided (password or private key required)")
	}

	return scpCommand, cleanup, nil
}

func executeSCPWithFallback(instanceId string, request local.ExecuteRequest) local.ExecuteResponse {
	logger.Debugf("[SCP] Instance: %s, attempt | profile=modern | %s", instanceId, request.LogContext)
	response := executeLocalSCPCommand(request, instanceId)
	if response.Success {
		return response
	}

	if !shouldRetryWithLegacy(response.Output + " " + response.Error) {
		return response
	}

	legacyCommand := addLegacySCPOptions(request.Command)
	if legacyCommand == request.Command {
		return response
	}

	logger.Warnf("[SCP] Instance: %s, retry | profile=modern -> legacy | %s | reason=%s", instanceId, request.LogContext, response.Error)
	legacyRequest := request
	legacyRequest.Command = legacyCommand
	legacyRequest.LogCommand = redactSensitiveCommand(legacyCommand)

	legacyResponse := executeLocalSCPCommand(legacyRequest, instanceId)
	if legacyResponse.Success {
		logger.Infof("[SCP] Instance: %s, success | profile=legacy | %s", instanceId, request.LogContext)
	} else {
		logger.Warnf("[SCP] Instance: %s, failure | profile=legacy | %s | error=%s | last=%q", instanceId, request.LogContext, legacyResponse.Error, truncateTransferOutput(legacyResponse.Output))
	}

	return legacyResponse
}

func buildTransferLogContext(direction, host string, port uint, user, sourcePath, targetPath, authMethod string, sourceMeta transferSourceMeta) string {
	return fmt.Sprintf(
		"%s %s@%s:%d %s -> %s [auth=%s kind=%s size=%s name=%s]",
		direction,
		user,
		host,
		port,
		sourcePath,
		targetPath,
		authMethod,
		sourceMeta.Kind,
		humanReadableSize(sourceMeta.SizeBytes),
		sourceMeta.BaseName,
	)
}

type transferSourceMeta struct {
	Kind      string
	SizeBytes int64
	BaseName  string
}

func describeTransferSource(sourcePath string) transferSourceMeta {
	meta := transferSourceMeta{
		Kind:      "unknown",
		SizeBytes: -1,
		BaseName:  filepath.Base(sourcePath),
	}

	info, err := os.Stat(sourcePath)
	if err != nil {
		meta.Kind = "missing_or_inaccessible"
		return meta
	}

	if info.IsDir() {
		meta.Kind = "dir"
		return meta
	}

	meta.Kind = "file"
	meta.SizeBytes = info.Size()
	return meta
}

func humanReadableSize(size int64) string {
	if size < 0 {
		return "unknown"
	}
	units := []string{"B", "KB", "MB", "GB", "TB"}
	value := float64(size)
	unit := units[0]
	for i := 1; i < len(units) && value >= 1024; i++ {
		value = value / 1024
		unit = units[i]
	}
	if unit == "B" {
		return fmt.Sprintf("%dB", size)
	}
	return fmt.Sprintf("%.1f%s", value, unit)
}

func transferAuthMethod(password, privateKey string) string {
	if privateKey != "" {
		return "private_key"
	}
	if password != "" {
		return "password"
	}
	return "unknown"
}

func truncateTransferOutput(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	value = strings.ReplaceAll(value, "\n", " | ")
	value = strings.ReplaceAll(value, "\r", " ")
	if len(value) <= 240 {
		return value
	}
	return value[:240] + "..."
}

func addLegacySCPOptions(command string) string {
	if !strings.Contains(command, "scp") {
		return command
	}

	if strings.Contains(command, "PubkeyAcceptedAlgorithms=+ssh-rsa") {
		return command
	}

	legacyOptions := " -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa"
	portFlagIndex := strings.Index(command, " -P ")
	if portFlagIndex == -1 {
		return command + legacyOptions
	}

	return command[:portFlagIndex] + legacyOptions + command[portFlagIndex:]
}

func invalidSSHExecuteResponse(instanceId, message string) ExecuteResponse {
	return ExecuteResponse{
		InstanceId: instanceId,
		Success:    false,
		Output:     message,
		Code:       utils.ErrorCodeInvalidRequest,
		Error:      message,
	}
}

func validateExecuteRequest(req ExecuteRequest) string {
	switch {
	case strings.TrimSpace(req.Command) == "":
		return "command is required"
	case strings.TrimSpace(req.Host) == "":
		return "host is required"
	case strings.TrimSpace(req.User) == "":
		return "user is required"
	case req.Port == 0:
		return "port must be greater than 0"
	case req.ExecuteTimeout <= 0:
		return "execute timeout must be greater than 0"
	default:
		return ""
	}
}

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	if validationErr := validateExecuteRequest(req); validationErr != "" {
		return invalidSSHExecuteResponse(instanceId, validationErr)
	}

	logger.Debugf("[SSH Execute] Instance: %s, Starting SSH connection to %s@%s:%d", instanceId, req.User, req.Host, req.Port)
	logger.Debugf("[SSH Execute] Instance: %s, Command: %s, Timeout: %ds", instanceId, req.Command, req.ExecuteTimeout)

	var authMethods []ssh.AuthMethod

	if req.PrivateKey != "" {
		var signer ssh.Signer
		var err error

		if req.Passphrase != "" {
			signer, err = parsePrivateKeyWithPassphraseFn([]byte(req.PrivateKey), []byte(req.Passphrase))
		} else {
			signer, err = parsePrivateKeyFn([]byte(req.PrivateKey))
		}

		if err != nil {
			errMsg := fmt.Sprintf("Failed to parse private key: %v", err)
			logger.Errorf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
			return ExecuteResponse{
				InstanceId: instanceId,
				Success:    false,
				Output:     errMsg,
				Code:       utils.ErrorCodeInvalidRequest,
				Error:      errMsg,
			}
		}
		authMethods = append(authMethods, buildPublicKeyAuthMethod(signer, profileModern))
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
			Code:       utils.ErrorCodeInvalidRequest,
			Error:      errMsg,
		}
	}

	sshConfig := &ssh.ClientConfig{
		User:              req.User,
		Auth:              authMethods,
		Timeout:           30 * time.Second,
		HostKeyCallback:   ssh.InsecureIgnoreHostKey(),
		HostKeyAlgorithms: hostKeyAlgorithmsForProfile(profileModern),
	}

	addr := fmt.Sprintf("%s:%d", req.Host, req.Port)
	client, err := sshDialFn("tcp", addr, sshConfig)
	if err != nil {
		if shouldRetryWithLegacy(err.Error()) {
			logger.Warnf("[SSH Execute] Instance: %s, modern profile dial failed, retrying legacy profile for %s@%s:%d - Error: %v", instanceId, req.User, req.Host, req.Port, err)

			legacyAuthMethods := make([]ssh.AuthMethod, 0, len(authMethods))
			if req.PrivateKey != "" {
				var legacySigner ssh.Signer
				if req.Passphrase != "" {
					legacySigner, err = parsePrivateKeyWithPassphraseFn([]byte(req.PrivateKey), []byte(req.Passphrase))
				} else {
					legacySigner, err = parsePrivateKeyFn([]byte(req.PrivateKey))
				}

				if err != nil {
					errMsg := fmt.Sprintf("Failed to parse private key for legacy retry: %v", err)
					logger.Errorf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
					return ExecuteResponse{InstanceId: instanceId, Success: false, Output: errMsg, Code: utils.ErrorCodeInvalidRequest, Error: errMsg}
				}

				legacyAuthMethods = append(legacyAuthMethods, buildPublicKeyAuthMethod(legacySigner, profileLegacy))
			}

			if req.Password != "" {
				legacyAuthMethods = append(legacyAuthMethods, ssh.Password(req.Password))
			}

			legacyConfig := &ssh.ClientConfig{
				User:              req.User,
				Auth:              legacyAuthMethods,
				Timeout:           30 * time.Second,
				HostKeyCallback:   ssh.InsecureIgnoreHostKey(),
				HostKeyAlgorithms: hostKeyAlgorithmsForProfile(profileLegacy),
			}

			client, err = sshDialFn("tcp", addr, legacyConfig)
			if err == nil {
				logger.Warnf("[SSH Execute] Instance: %s, legacy profile dial succeeded for %s@%s:%d", instanceId, req.User, req.Host, req.Port)
			}
		}

		if err != nil {
			errMsg := fmt.Sprintf("Failed to create SSH client: %v", err)
			logger.Errorf("[SSH Execute] Instance: %s, Failed to create SSH client for %s@%s:%d - Error: %v", instanceId, req.User, req.Host, req.Port, err)
			return ExecuteResponse{
				InstanceId: instanceId,
				Success:    false,
				Output:     errMsg,
				Code:       utils.ErrorCodeDependencyFailure,
				Error:      errMsg,
			}
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
			Code:       utils.ErrorCodeDependencyFailure,
			Error:      errMsg,
		}
	}
	defer session.Close()

	var stdout, stderr bytes.Buffer
	session.SetStdout(&stdout)
	session.SetStderr(&stderr)

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
			Code:       utils.ErrorCodeTimeout,
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
				Code:       utils.ErrorCodeExecutionFailure,
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

func buildPublicKeyAuthMethod(signer ssh.Signer, profile sshCompatibilityProfile) ssh.AuthMethod {
	if signer.PublicKey().Type() != ssh.KeyAlgoRSA {
		return ssh.PublicKeys(signer)
	}

	algorithmSigner, ok := signer.(ssh.AlgorithmSigner)
	if !ok {
		return ssh.PublicKeys(signer)
	}

	rsaSigner, err := ssh.NewSignerWithAlgorithms(algorithmSigner, rsaSignerAlgorithmsForProfile(profile))
	if err != nil {
		return ssh.PublicKeys(signer)
	}

	return ssh.PublicKeys(rsaSigner)
}

func SubscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	logger.Infof("[SSH Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := nc.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[SSH Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))
		respondSSHExecuteMessage(msg, msg.Data, *instanceId)
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

		responseContent, ok := handleDownloadToRemoteMessage(msg.Data, *instanceId, nc)
		if !ok {
			logger.Errorf("[Download Subscribe] Instance: %s, Error unmarshalling incoming message", *instanceId)
			return
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

		responseContent, ok := handleUploadToRemoteMessage(msg.Data, *instanceId)
		if !ok {
			logger.Errorf("[Upload Subscribe] Instance: %s, Error unmarshalling incoming message", *instanceId)
			return
		}
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
