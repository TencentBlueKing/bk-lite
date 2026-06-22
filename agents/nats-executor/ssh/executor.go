package ssh

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"nats-executor/local"
	"nats-executor/logger"
	"nats-executor/utils"
	"nats-executor/utils/downloaderr"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
)

var sshpassPasswordPattern = regexp.MustCompile(`sshpass -p '(?:[^']|'"'"')*'`)

type sshConn interface{}
type responseMsg interface {
	Respond([]byte) error
}
type inboundMsg interface {
	responseMsg
	Payload() []byte
}
type natsInboundMsg struct{ *nats.Msg }

func (m natsInboundMsg) Payload() []byte { return m.Data }

type eventPublisher interface {
	Publish(subject string, data []byte) error
}
type subscriber interface {
	Subscribe(subject string, cb nats.MsgHandler) (*nats.Subscription, error)
}

type streamEvent struct {
	ExecutionID string `json:"execution_id"`
	Stream      string `json:"stream"`
	Line        string `json:"line"`
	Timestamp   string `json:"timestamp"`
}

type streamLogWriter struct {
	publisher   eventPublisher
	topic       string
	executionID string
	stream      string
	buffer      bytes.Buffer
}

type sshClient interface {
	NewSession() (sshSession, error)
	Close() error
}

type sshSession interface {
	Run(cmd string) error
	Signal(sig ssh.Signal) error
	Close() error
	SetStdout(w io.Writer)
	SetStderr(w io.Writer)
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
	mkdirTempDir                    = os.MkdirTemp
	removeAllPath                   = os.RemoveAll
	tcpProbeFn                      = func(addr string, timeout time.Duration) error {
		conn, err := net.DialTimeout("tcp", addr, timeout)
		if err != nil {
			return err
		}
		return conn.Close()
	}
	sshDialFn = func(network, addr string, config *ssh.ClientConfig) (sshClient, error) {
		client, err := ssh.Dial(network, addr, config)
		if err != nil {
			return nil, err
		}
		return realSSHClient{client: client}, nil
	}
	subscribeSSHExecutorFn      = subscribeSSHExecutor
	subscribeDownloadToRemoteFn = subscribeDownloadToRemote
	subscribeUploadToRemoteFn   = subscribeUploadToRemote
)

const sshConnectTimeout = 30 * time.Second

const (
	sshStageTCPConnect    = "tcp_connect"
	sshStageSSHDial       = "ssh_dial"
	sshStageLegacyRetry   = "legacy_retry"
	sshStageSessionCreate = "session_create"
	sshStageCommandRun    = "command_run"

	sshCategoryNetwork       = "network"
	sshCategoryCompatibility = "compatibility"
	sshCategoryAuth          = "auth"
	sshCategoryDependency    = "dependency"
	sshCategoryRemoteTimeout = "remote_timeout"
	sshCategoryRemoteExit    = "remote_exit"
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
func (s realSSHSession) SetStdout(w io.Writer)       { s.session.Stdout = w }
func (s realSSHSession) SetStderr(w io.Writer)       { s.session.Stderr = w }

func newStreamLogWriter(publisher eventPublisher, topic, executionID, stream string) *streamLogWriter {
	return &streamLogWriter{publisher: publisher, topic: topic, executionID: executionID, stream: stream}
}

func (w *streamLogWriter) Write(p []byte) (int, error) {
	if len(p) == 0 {
		return 0, nil
	}
	_, _ = w.buffer.Write(p)

	var remaining bytes.Buffer
	for {
		line, err := w.buffer.ReadString('\n')
		if err == io.EOF {
			remaining.WriteString(line)
			break
		}
		if err != nil {
			return len(p), err
		}
		w.publish(strings.TrimRight(line, "\r\n"))
	}
	if remaining.Len() > 0 {
		w.buffer.Reset()
		_, _ = remaining.WriteTo(&w.buffer)
	}
	return len(p), nil
}

func (w *streamLogWriter) Flush() {
	if w.buffer.Len() == 0 {
		return
	}
	w.publish(strings.TrimRight(w.buffer.String(), "\r\n"))
	w.buffer.Reset()
}

func (w *streamLogWriter) publish(line string) {
	if w.publisher == nil || w.topic == "" || line == "" {
		return
	}
	payload, err := json.Marshal(streamEvent{
		ExecutionID: w.executionID,
		Stream:      w.stream,
		Line:        line,
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
	})
	if err != nil {
		logger.Warnf("[SSH Execute] stream marshal failed: %v", err)
		return
	}
	if err := w.publisher.Publish(w.topic, payload); err != nil {
		logger.Warnf("[SSH Execute] stream publish failed: %v", err)
	}
}

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

func buildHostKeyCallback() (ssh.HostKeyCallback, error) {
	knownHostsFile := configuredKnownHostsFile()
	if knownHostsFile == "" {
		return ssh.InsecureIgnoreHostKey(), nil
	}

	callback, err := knownhosts.New(knownHostsFile)
	if err != nil {
		return nil, fmt.Errorf("failed to load SSH known_hosts file %s: %w", knownHostsFile, err)
	}
	return callback, nil
}

func redactSensitiveCommand(command string) string {
	return sshpassPasswordPattern.ReplaceAllString(command, "sshpass -p '***'")
}

func handleSSHExecuteMessage(data []byte, instanceId string, natsConn *nats.Conn) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	var sshExecuteRequest ExecuteRequest
	if err := json.Unmarshal(incoming.Args[0], &sshExecuteRequest); err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, "invalid request payload"), true
	}

	responseData := executeWithConn(sshExecuteRequest, instanceId, natsConn)
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
	if errMsg := validateTransferTimeout(downloadRequest.ExecuteTimeout); errMsg != "" {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, errMsg), true
	}

	deadline := time.Now().Add(time.Duration(downloadRequest.ExecuteTimeout) * time.Second)
	if downloadRequest.FastFail {
		probeResp := tcpProbeResponse(instanceId, fmt.Sprintf("%s:%d", downloadRequest.Host, downloadRequest.Port), tcpProbeTimeout(remainingBudget(deadline)))
		if !probeResp.Success {
			responseContent, err := json.Marshal(probeResp)
			if err != nil {
				return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to marshal response: %v", err)), true
			}
			return responseContent, true
		}
	}

	stagingBasePath := downloadRequest.LocalPath
	if stagingBasePath == "" {
		stagingBasePath = os.TempDir()
	}
	stagingDir, err := mkdirTempDir(stagingBasePath, "nats-executor-*")
	if err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to prepare local staging path: %v", err)), true
	}
	defer func() {
		if err := removeAllPath(stagingDir); err != nil {
			logger.Warnf("[SCP Transfer] Instance: %s, failed to clean staging dir %s: %v", instanceId, stagingDir, err)
		}
	}()

	localdownloadRequest := utils.DownloadFileRequest{
		BucketName:     downloadRequest.BucketName,
		FileKey:        downloadRequest.FileKey,
		FileName:       downloadRequest.FileName,
		TargetPath:     stagingDir,
		ExecuteTimeout: remainingBudgetSeconds(deadline),
	}

	if err := downloadFromObjectStore(localdownloadRequest, nc); err != nil {
		code := utils.ErrorCodeDependencyFailure
		switch {
		case downloaderr.KindOf(err) == downloaderr.KindTimeout || errors.Is(err, context.DeadlineExceeded):
			code = utils.ErrorCodeTimeout
		case downloaderr.KindOf(err) == downloaderr.KindIO:
			code = utils.ErrorCodeExecutionFailure
		}
		return utils.NewErrorExecuteResponse(instanceId, code, fmt.Sprintf("Failed to download file: %v", err)), true
	}

	sourcePath := filepath.Join(localdownloadRequest.TargetPath, localdownloadRequest.FileName)
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
		ExecuteTimeout: remainingBudgetSeconds(deadline),
	}
	if downloadRequest.Password != "" {
		localExecuteRequest.Env = map[string]string{"SSHPASS": downloadRequest.Password}
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
	if errMsg := validateTransferTimeout(uploadRequest.ExecuteTimeout); errMsg != "" {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, errMsg), true
	}

	deadline := time.Now().Add(time.Duration(uploadRequest.ExecuteTimeout) * time.Second)

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
		ExecuteTimeout: remainingBudgetSeconds(deadline),
	}
	if uploadRequest.Password != "" {
		localExecuteRequest.Env = map[string]string{"SSHPASS": uploadRequest.Password}
	}

	responseData := executeSCPCommand(instanceId, localExecuteRequest)
	responseContent, _ := json.Marshal(responseData)
	return responseContent, true
}

func respondSSHExecuteMessage(msg responseMsg, data []byte, instanceId string, nc *nats.Conn) bool {
	responseContent, ok := handleSSHExecuteMessage(data, instanceId, nc)
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

func respondDownloadToRemoteSubscription(msg inboundMsg, instanceId string, nc sshConn) bool {
	responseContent, ok := handleDownloadToRemoteMessage(msg.Payload(), instanceId, nc)
	if !ok {
		logger.Errorf("[Download Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Download Subscribe] Instance: %s, Error responding to download request: %v", instanceId, err)
		return false
	}
	logger.Debugf("[Download Subscribe] Instance: %s, Response sent successfully, size: %d bytes", instanceId, len(responseContent))
	return true
}

func respondUploadToRemoteSubscription(msg inboundMsg, instanceId string) bool {
	responseContent, ok := handleUploadToRemoteMessage(msg.Payload(), instanceId)
	if !ok {
		logger.Errorf("[Upload Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Upload Subscribe] Instance: %s, Error responding to upload request: %v", instanceId, err)
		return false
	}
	logger.Debugf("[Upload Subscribe] Instance: %s, Response sent successfully, size: %d bytes", instanceId, len(responseContent))
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
			scpCommand = fmt.Sprintf("sshpass -e scp %s -P %d -r %s %s",
				sshOptions, port, shellQuote(sourcePath), shellQuoteRemoteTarget(user, host, targetPath))
		} else {
			scpCommand = fmt.Sprintf("sshpass -e scp %s -P %d -r %s %s",
				sshOptions, port, shellQuoteRemoteTarget(user, host, targetPath), shellQuote(sourcePath))
		}

		logger.Debugf("[SCP] Using password authentication with profile=%s", profile)
	} else {
		return "", nil, fmt.Errorf("no authentication method provided (password or private key required)")
	}

	return scpCommand, cleanup, nil
}

func executeSCPWithFallback(instanceId string, request local.ExecuteRequest) local.ExecuteResponse {
	deadline := time.Now().Add(time.Duration(request.ExecuteTimeout) * time.Second)
	request.ExecuteTimeout = remainingBudgetSeconds(deadline)
	if request.ExecuteTimeout <= 0 {
		return localTimeoutResponse(instanceId, fmt.Sprintf("SCP transfer timed out before execution (timeout budget exhausted): %s", request.LogContext))
	}
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
	legacyRequest.ExecuteTimeout = remainingBudgetSeconds(deadline)
	if legacyRequest.ExecuteTimeout <= 0 {
		return localTimeoutResponse(instanceId, fmt.Sprintf("SCP transfer timed out before legacy retry (timeout budget exhausted): %s", request.LogContext))
	}

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

func newSSHFailureResponse(instanceId, code, message, stage, category string) ExecuteResponse {
	return ExecuteResponse{
		InstanceId: instanceId,
		Success:    false,
		Output:     message,
		Code:       code,
		Error:      message,
		Stage:      stage,
		Category:   category,
	}
}

func timeoutStageResponse(instanceId, output, message, stage, category string) ExecuteResponse {
	return ExecuteResponse{
		Output:     output,
		InstanceId: instanceId,
		Success:    false,
		Code:       utils.ErrorCodeTimeout,
		Error:      message,
		Stage:      stage,
		Category:   category,
	}
}

func tcpProbeTimeout(timeout time.Duration) time.Duration {
	if timeout <= 0 {
		return 0
	}
	probe := timeout / 5
	if probe > 5*time.Second {
		probe = 5 * time.Second
	}
	if probe < time.Second {
		probe = time.Second
	}
	if probe > timeout {
		probe = timeout
	}
	return probe
}

func tcpProbeResponse(instanceId, addr string, timeout time.Duration) local.ExecuteResponse {
	if timeout <= 0 {
		message := "SCP 传输在 TCP 探测前超时"
		return local.ExecuteResponse{InstanceId: instanceId, Success: false, Code: utils.ErrorCodeTimeout, Error: message, Output: message}
	}
	if err := tcpProbeFn(addr, timeout); err != nil {
		if isLikelyTimeoutError(err) {
			message := fmt.Sprintf("远程主机端口连接超时: %s", addr)
			return local.ExecuteResponse{InstanceId: instanceId, Success: false, Code: utils.ErrorCodeTimeout, Error: message, Output: message}
		}
		message := fmt.Sprintf("远程主机端口不可达: %s, error=%v", addr, err)
		return local.ExecuteResponse{InstanceId: instanceId, Success: false, Code: utils.ErrorCodeDependencyFailure, Error: message, Output: message}
	}
	return local.ExecuteResponse{InstanceId: instanceId, Success: true}
}

func isLikelyAuthError(err error) bool {
	if err == nil {
		return false
	}
	lower := strings.ToLower(err.Error())
	return strings.Contains(lower, "permission denied") || strings.Contains(lower, "unable to authenticate") || strings.Contains(lower, "authenticate")
}

func isLikelyNetworkError(err error) bool {
	if err == nil {
		return false
	}
	if isLikelyTimeoutError(err) {
		return true
	}
	lower := strings.ToLower(err.Error())
	networkIndicators := []string{
		"connection refused",
		"no route to host",
		"network is unreachable",
		"host is down",
		"connection reset",
		"broken pipe",
		"lookup ",
	}
	for _, indicator := range networkIndicators {
		if strings.Contains(lower, indicator) {
			return true
		}
	}
	return false
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

func validateTransferTimeout(timeout int) string {
	if timeout <= 0 {
		return "execute timeout must be greater than 0"
	}
	return ""
}

func remainingBudget(deadline time.Time) time.Duration {
	remaining := time.Until(deadline)
	if remaining <= 0 {
		return 0
	}
	return remaining
}

func remainingBudgetSeconds(deadline time.Time) int {
	remaining := remainingBudget(deadline)
	if remaining <= 0 {
		return 0
	}
	seconds := int((remaining + time.Second - 1) / time.Second)
	if seconds < 1 {
		return 1
	}
	return seconds
}

func timeoutResponse(instanceId, output, message string) ExecuteResponse {
	return timeoutStageResponse(instanceId, output, message, "", sshCategoryRemoteTimeout)
}

func localTimeoutResponse(instanceId, message string) local.ExecuteResponse {
	return local.ExecuteResponse{
		Output:     message,
		InstanceId: instanceId,
		Success:    false,
		Code:       utils.ErrorCodeTimeout,
		Error:      message,
	}
}

func isLikelyTimeoutError(err error) bool {
	if err == nil {
		return false
	}
	lower := strings.ToLower(err.Error())
	return strings.Contains(lower, "timeout") || strings.Contains(lower, "deadline exceeded")
}

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	return executeWithConn(req, instanceId, nil)
}

func executeWithConn(req ExecuteRequest, instanceId string, nc *nats.Conn) ExecuteResponse {
	if validationErr := validateExecuteRequest(req); validationErr != "" {
		return invalidSSHExecuteResponse(instanceId, validationErr)
	}

	deadline := time.Now().Add(time.Duration(req.ExecuteTimeout) * time.Second)

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

	remaining := remainingBudget(deadline)
	if remaining <= 0 {
		return timeoutStageResponse(instanceId, "", fmt.Sprintf("SSH execution timed out before dialing (timeout: %ds)", req.ExecuteTimeout), sshStageSSHDial, sshCategoryRemoteTimeout)
	}

	addr := fmt.Sprintf("%s:%d", req.Host, req.Port)
	if req.ConnectionTest {
		probeTimeout := tcpProbeTimeout(remaining)
		if probeTimeout <= 0 {
			return timeoutStageResponse(instanceId, "", fmt.Sprintf("SSH execution timed out before TCP probe (timeout: %ds)", req.ExecuteTimeout), sshStageTCPConnect, sshCategoryRemoteTimeout)
		}
		if err := tcpProbeFn(addr, probeTimeout); err != nil {
			if isLikelyTimeoutError(err) {
				return timeoutStageResponse(instanceId, "", fmt.Sprintf("TCP connect timed out after %s", probeTimeout), sshStageTCPConnect, sshCategoryNetwork)
			}
			return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, fmt.Sprintf("TCP connect failed: %v", err), sshStageTCPConnect, sshCategoryNetwork)
		}
		remaining = remainingBudget(deadline)
		if remaining <= 0 {
			return timeoutStageResponse(instanceId, "", fmt.Sprintf("SSH execution timed out after TCP probe (timeout: %ds)", req.ExecuteTimeout), sshStageSSHDial, sshCategoryRemoteTimeout)
		}
	}

	hostKeyCallback, err := buildHostKeyCallback()
	if err != nil {
		errMsg := fmt.Sprintf("Failed to configure SSH host key verification: %v", err)
		logger.Errorf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
		return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageSSHDial, sshCategoryDependency)
	}

	sshConfig := &ssh.ClientConfig{
		User:              req.User,
		Auth:              authMethods,
		Timeout:           minDuration(sshConnectTimeout, remaining),
		HostKeyCallback:   hostKeyCallback,
		HostKeyAlgorithms: hostKeyAlgorithmsForProfile(profileModern),
	}

	client, err := sshDialFn("tcp", addr, sshConfig)
	if err != nil {
		if shouldRetryWithLegacy(err.Error()) {
			remaining = remainingBudget(deadline)
			if remaining <= 0 {
				errMsg := fmt.Sprintf("SSH dial timed out after %ds before legacy retry", req.ExecuteTimeout)
				logger.Warnf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
				return timeoutStageResponse(instanceId, "", errMsg, sshStageLegacyRetry, sshCategoryCompatibility)
			}
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
				Timeout:           minDuration(sshConnectTimeout, remaining),
				HostKeyCallback:   hostKeyCallback,
				HostKeyAlgorithms: hostKeyAlgorithmsForProfile(profileLegacy),
			}

			client, err = sshDialFn("tcp", addr, legacyConfig)
			if err == nil {
				logger.Warnf("[SSH Execute] Instance: %s, legacy profile dial succeeded for %s@%s:%d", instanceId, req.User, req.Host, req.Port)
			}
		}

		if err != nil {
			if remainingBudget(deadline) <= 0 || isLikelyTimeoutError(err) {
				errMsg := fmt.Sprintf("SSH dial timed out after %ds", req.ExecuteTimeout)
				logger.Warnf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
				return timeoutStageResponse(instanceId, "", errMsg, sshStageSSHDial, sshCategoryNetwork)
			}
			if isLikelyAuthError(err) {
				errMsg := fmt.Sprintf("SSH authentication failed: %v", err)
				return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageSSHDial, sshCategoryAuth)
			}
			if shouldRetryWithLegacy(err.Error()) {
				errMsg := fmt.Sprintf("SSH compatibility failed after legacy retry: %v", err)
				return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageLegacyRetry, sshCategoryCompatibility)
			}
			if isLikelyNetworkError(err) {
				errMsg := fmt.Sprintf("Failed to create SSH client: %v", err)
				return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageSSHDial, sshCategoryNetwork)
			}
			errMsg := fmt.Sprintf("Failed to create SSH client: %v", err)
			logger.Errorf("[SSH Execute] Instance: %s, Failed to create SSH client for %s@%s:%d - Error: %v", instanceId, req.User, req.Host, req.Port, err)
			return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageSSHDial, sshCategoryDependency)
		}
	}

	logger.Debugf("[SSH Execute] Instance: %s, SSH connection established successfully", instanceId)
	defer func() {
		client.Close()
		logger.Debugf("[SSH Execute] Instance: %s, SSH connection closed", instanceId)
	}()

	session, err := client.NewSession()
	if err != nil {
		if remainingBudget(deadline) <= 0 {
			errMsg := fmt.Sprintf("SSH session setup timed out after %ds", req.ExecuteTimeout)
			logger.Warnf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
			return timeoutStageResponse(instanceId, "", errMsg, sshStageSessionCreate, sshCategoryRemoteTimeout)
		}
		errMsg := fmt.Sprintf("Failed to create SSH session: %v", err)
		logger.Errorf("[SSH Execute] Instance: %s, Failed to create SSH session - Error: %v", instanceId, err)
		return newSSHFailureResponse(instanceId, utils.ErrorCodeDependencyFailure, errMsg, sshStageSessionCreate, sshCategoryDependency)
	}
	defer session.Close()

	outputCapture := utils.NewSharedOutputCapture(utils.CommandOutputLimitBytes)
	stdoutWriter := outputCapture.StdoutWriter()
	stderrWriter := outputCapture.StderrWriter()
	var stdoutStreamWriter *streamLogWriter
	var stderrStreamWriter *streamLogWriter
	if req.StreamLogs && req.StreamLogTopic != "" && nc != nil {
		stdoutStreamWriter = newStreamLogWriter(nc, req.StreamLogTopic, req.ExecutionID, "stdout")
		stderrStreamWriter = newStreamLogWriter(nc, req.StreamLogTopic, req.ExecutionID, "stderr")
		stdoutWriter = io.MultiWriter(outputCapture.StdoutWriter(), stdoutStreamWriter)
		stderrWriter = io.MultiWriter(outputCapture.StderrWriter(), stderrStreamWriter)
	}
	session.SetStdout(stdoutWriter)
	session.SetStderr(stderrWriter)

	ctx, cancel := context.WithDeadline(context.Background(), deadline)
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
		errMsg := fmt.Sprintf("SSH execution timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
		logger.Warnf("[SSH Execute] Instance: %s, %s", instanceId, errMsg)
		session.Signal(ssh.SIGKILL)
		if stdoutStreamWriter != nil {
			stdoutStreamWriter.Flush()
		}
		if stderrStreamWriter != nil {
			stderrStreamWriter.Flush()
		}
		snapshot := outputCapture.Snapshot()
		output := utils.FormatCapturedOutput(string(snapshot.Stdout), string(snapshot.Stderr), snapshot)
		if snapshot.Truncated {
			logger.Warnf("[SSH Execute] Instance: %s, Output exceeded shared capture limit and was truncated (stdout_dropped=%dB stderr_dropped=%dB total_written=%dB)", instanceId, snapshot.StdoutDropped, snapshot.StderrDropped, snapshot.TotalWritten)
		}
		return timeoutStageResponse(instanceId, output, errMsg, sshStageCommandRun, sshCategoryRemoteTimeout)
	case err := <-errChan:
		duration := time.Since(startTime)
		if stdoutStreamWriter != nil {
			stdoutStreamWriter.Flush()
		}
		if stderrStreamWriter != nil {
			stderrStreamWriter.Flush()
		}
		snapshot := outputCapture.Snapshot()
		output := utils.FormatCapturedOutput(string(snapshot.Stdout), string(snapshot.Stderr), snapshot)

		if err != nil {
			errMsg := fmt.Sprintf("Command execution failed: %v", err)
			logger.Warnf("[SSH Execute] Instance: %s, Command execution failed after %v - Error: %v", instanceId, duration, err)
			logger.Debugf("[SSH Execute] Instance: %s, Output: %s", instanceId, output)
			if snapshot.Truncated {
				logger.Warnf("[SSH Execute] Instance: %s, Output exceeded shared capture limit and was truncated (stdout_dropped=%dB stderr_dropped=%dB total_written=%dB)", instanceId, snapshot.StdoutDropped, snapshot.StderrDropped, snapshot.TotalWritten)
			}
			return ExecuteResponse{
				Output:     output,
				InstanceId: instanceId,
				Success:    false,
				Code:       utils.ErrorCodeExecutionFailure,
				Error:      errMsg,
				Stage:      sshStageCommandRun,
				Category:   sshCategoryRemoteExit,
			}
		}

		logger.Debugf("[SSH Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		logger.Debugf("[SSH Execute] Instance: %s, Output length: %d bytes", instanceId, len(output))
		if snapshot.Truncated {
			logger.Warnf("[SSH Execute] Instance: %s, Output exceeded shared capture limit and was truncated (stdout_dropped=%dB stderr_dropped=%dB total_written=%dB)", instanceId, snapshot.StdoutDropped, snapshot.StderrDropped, snapshot.TotalWritten)
		}

		return ExecuteResponse{
			Output:     output,
			InstanceId: instanceId,
			Success:    true,
		}
	}
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
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

func subscribeSSHExecutor(sub subscriber, nc *nats.Conn, instanceId *string) error {
	subject := fmt.Sprintf("ssh.execute.%s", *instanceId)
	logger.Infof("[SSH Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[SSH Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))
		respondSSHExecuteMessage(natsInboundMsg{msg}, msg.Data, *instanceId, nc)
	})
	return err
}

func SubscribeSSHExecutor(nc *nats.Conn, instanceId *string) {
	if err := subscribeSSHExecutorFn(nc, nc, instanceId); err != nil {
		logger.Errorf("[SSH Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func subscribeDownloadToRemote(sub subscriber, nc sshConn, instanceId *string) error {
	subject := fmt.Sprintf("download.remote.%s", *instanceId)
	logger.Infof("[Download Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Download Subscribe] Instance: %s, Received download request, size: %d bytes", *instanceId, len(msg.Data))
		respondDownloadToRemoteSubscription(natsInboundMsg{msg}, *instanceId, nc)
	})
	return err
}

func SubscribeDownloadToRemote(nc *nats.Conn, instanceId *string) {
	if err := subscribeDownloadToRemoteFn(nc, nc, instanceId); err != nil {
		logger.Errorf("[Download Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func subscribeUploadToRemote(sub subscriber, instanceId *string) error {
	subject := fmt.Sprintf("upload.remote.%s", *instanceId)
	logger.Infof("[Upload Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Upload Subscribe] Instance: %s, Received upload request, size: %d bytes", *instanceId, len(msg.Data))
		respondUploadToRemoteSubscription(natsInboundMsg{msg}, *instanceId)
	})
	return err
}

func SubscribeUploadToRemote(nc *nats.Conn, instanceId *string) {
	if err := subscribeUploadToRemoteFn(nc, instanceId); err != nil {
		logger.Errorf("[Upload Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
