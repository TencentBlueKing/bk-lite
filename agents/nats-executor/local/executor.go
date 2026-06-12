package local

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"nats-executor/logger"
	"nats-executor/utils"
	"nats-executor/utils/downloaderr"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/nats-io/nats.go"
	"golang.org/x/text/encoding/simplifiedchinese"
)

type downloadConn interface{}
type responseMsg interface {
	Respond([]byte) error
}
type inboundMsg interface {
	responseMsg
	Payload() []byte
}
type natsInboundMsg struct{ *nats.Msg }

func (m natsInboundMsg) Payload() []byte { return m.Data }

type subscriber interface {
	Subscribe(subject string, cb nats.MsgHandler) (*nats.Subscription, error)
}

var (
	executeLocalCommand = Execute
	downloadToLocalFile = func(req utils.DownloadFileRequest, nc downloadConn) error {
		natsConn, _ := nc.(*nats.Conn)
		return utils.DownloadFile(req, natsConn)
	}
	unzipLocalArchive          = utils.UnzipToDir
	nowUTC                     = func() time.Time { return time.Now().UTC() }
	subscribeLocalExecutorFn   = subscribeLocalExecutor
	subscribeDownloadToLocalFn = subscribeDownloadToLocal
	subscribeUnzipToLocalFn    = subscribeUnzipToLocal
	subscribeHealthCheckFn     = subscribeHealthCheck
)

// --- 流式行输出（job_mgmt 脚本执行实时日志） ---
// localStreamPublisher 在 SubscribeLocalExecutor 时被设为本进程的 NATS 连接；
// Execute 在 req.StreamLogs 为真时用它按行 publish stdout/stderr。设值一次（启动订阅时），
// 之后只读，无并发写。
var localStreamPublisher eventPublisher

type eventPublisher interface {
	Publish(subject string, data []byte) error
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
		logger.Warnf("[Local Execute] stream marshal failed: %v", err)
		return
	}
	if err := w.publisher.Publish(w.topic, payload); err != nil {
		logger.Warnf("[Local Execute] stream publish failed: %v", err)
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

func invalidRequestResponse(instanceId, message string) ([]byte, bool) {
	return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeInvalidRequest, message), true
}

func handleLocalExecuteMessage(data []byte, instanceId string) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		var probe struct {
			Args []json.RawMessage `json:"args"`
		}
		if err := json.Unmarshal(data, &probe); err != nil {
			return invalidRequestResponse(instanceId, "invalid request payload")
		}
		return invalidRequestResponse(instanceId, "missing request arguments")
	}

	var localExecuteRequest ExecuteRequest
	if err := json.Unmarshal(incoming.Args[0], &localExecuteRequest); err != nil {
		return invalidRequestResponse(instanceId, "invalid request payload")
	}

	responseData := executeLocalCommand(localExecuteRequest, instanceId)
	responseContent, err := json.Marshal(responseData)
	if err != nil {
		return utils.NewErrorExecuteResponse(instanceId, utils.ErrorCodeExecutionFailure, fmt.Sprintf("Failed to marshal response: %v", err)), true
	}

	return responseContent, true
}

func handleDownloadToLocalMessage(data []byte, instanceId string, nc downloadConn) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return invalidRequestResponse(instanceId, "invalid request payload")
	}

	var downloadRequest utils.DownloadFileRequest
	if err := json.Unmarshal(incoming.Args[0], &downloadRequest); err != nil {
		return invalidRequestResponse(instanceId, "invalid request payload")
	}

	var resp ExecuteResponse
	err := downloadToLocalFile(downloadRequest, nc)
	if err != nil {
		message := fmt.Sprintf("Failed to download file: %v", err)
		code := utils.ErrorCodeDependencyFailure
		switch {
		case downloaderr.KindOf(err) == downloaderr.KindTimeout || errors.Is(err, context.DeadlineExceeded):
			code = utils.ErrorCodeTimeout
		case downloaderr.KindOf(err) == downloaderr.KindIO:
			code = utils.ErrorCodeExecutionFailure
		}
		resp = ExecuteResponse{
			Success:    false,
			Output:     message,
			InstanceId: instanceId,
			Code:       code,
			Error:      message,
		}
	} else {
		resp = ExecuteResponse{
			Success:    true,
			Output:     fmt.Sprintf("File successfully downloaded to %s/%s", downloadRequest.TargetPath, downloadRequest.FileName),
			InstanceId: instanceId,
		}
	}

	responseContent, _ := json.Marshal(resp)
	return responseContent, true
}

func handleUnzipToLocalMessage(data []byte, instanceId string) ([]byte, bool) {
	incoming, ok := decodeIncomingMessage(data)
	if !ok {
		return invalidRequestResponse(instanceId, "invalid request payload")
	}

	var unzipRequest utils.UnzipRequest
	if err := json.Unmarshal(incoming.Args[0], &unzipRequest); err != nil {
		return invalidRequestResponse(instanceId, "invalid request payload")
	}

	parentDir, err := unzipLocalArchive(unzipRequest)
	if err != nil {
		message := fmt.Sprintf("Failed to unzip file: %v", err)
		resp := ExecuteResponse{
			Output:     message,
			InstanceId: instanceId,
			Success:    false,
			Code:       utils.ErrorCodeExecutionFailure,
			Error:      message,
		}
		responseContent, _ := json.Marshal(resp)
		return responseContent, true
	}

	resp := ExecuteResponse{
		Output:     parentDir,
		InstanceId: instanceId,
		Success:    true,
	}
	responseContent, _ := json.Marshal(resp)
	return responseContent, true
}

func handleHealthCheckMessage(instanceId string) []byte {
	response := HealthCheckResponse{
		Success:    true,
		Status:     "ok",
		InstanceId: instanceId,
		Timestamp:  nowUTC().Format(time.RFC3339),
	}
	responseContent, _ := json.Marshal(response)
	return responseContent
}

func respondLocalExecuteMessage(msg responseMsg, data []byte, instanceId string) bool {
	responseContent, ok := handleLocalExecuteMessage(data, instanceId)
	if !ok {
		logger.Errorf("[Local Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}

	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Local Subscribe] Instance: %s, Error responding to request: %v", instanceId, err)
		return false
	}

	logger.Debugf("[Local Subscribe] Instance: %s, Response sent successfully, size: %d bytes", instanceId, len(responseContent))
	return true
}

func respondDownloadToLocalSubscription(msg inboundMsg, instanceId string, nc downloadConn) bool {
	responseContent, ok := handleDownloadToLocalMessage(msg.Payload(), instanceId, nc)
	if !ok {
		logger.Errorf("[Download Local Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Download Local Subscribe] Instance: %s, Error responding to download request: %v", instanceId, err)
		return false
	}
	return true
}

func respondUnzipToLocalSubscription(msg inboundMsg, instanceId string) bool {
	responseContent, ok := handleUnzipToLocalMessage(msg.Payload(), instanceId)
	if !ok {
		logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error unmarshalling incoming message", instanceId)
		return false
	}
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Unzip Local Subscribe] Instance: %s, Error responding to unzip request: %v", instanceId, err)
		return false
	}
	return true
}

func respondHealthCheckSubscription(msg inboundMsg, instanceId, subject string) bool {
	logger.Debugf("[Health Check] Received health check request from subject: %s", subject)
	responseContent := handleHealthCheckMessage(instanceId)
	if err := msg.Respond(responseContent); err != nil {
		logger.Errorf("[Health Check Subscribe] Instance: %s, Error responding to health check: %v", instanceId, err)
		return false
	}
	logger.Debugf("[Health Check] Responded with status: ok")
	return true
}

func normalizeShell(shell string) string {
	if strings.TrimSpace(shell) == "" {
		return ShellTypeSh
	}

	return strings.ToLower(strings.TrimSpace(shell))
}

func isSupportedShell(shell string) bool {
	switch shell {
	case ShellTypeSh, ShellTypeBash, ShellTypeBat, ShellTypeCmd, ShellTypePowerShell, ShellTypePwsh:
		return true
	default:
		return false
	}
}

func invalidExecuteResponse(instanceId, message string) ExecuteResponse {
	return ExecuteResponse{
		Output:     message,
		InstanceId: instanceId,
		Success:    false,
		Code:       utils.ErrorCodeInvalidRequest,
		Error:      message,
	}
}

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	if strings.TrimSpace(req.Command) == "" {
		return invalidExecuteResponse(instanceId, "command is required")
	}
	if req.ExecuteTimeout <= 0 {
		return invalidExecuteResponse(instanceId, "execute timeout must be greater than 0")
	}

	shell := normalizeShell(req.Shell)
	if !isSupportedShell(shell) {
		return invalidExecuteResponse(instanceId, fmt.Sprintf("unsupported shell: %s", strings.TrimSpace(req.Shell)))
	}

	commandForLog := req.Command
	if req.LogCommand != "" {
		commandForLog = req.LogCommand
	}
	logContext := strings.TrimSpace(req.LogContext)
	isSCPCommand := contains(req.Command, "scp") || contains(req.Command, "sshpass")

	logger.Debugf("[Local Execute] Instance: %s, Starting command execution", instanceId)
	logger.Debugf("[Local Execute] Instance: %s, Command: %s", instanceId, commandForLog)
	logger.Debugf("[Local Execute] Instance: %s, Timeout: %ds", instanceId, req.ExecuteTimeout)
	if isSCPCommand {
		logger.Infof("[SCP] Instance: %s, start | %s | timeout=%ds", instanceId, formatSCPLogContext(logContext), req.ExecuteTimeout)
		logger.Debugf("[SCP] Instance: %s, command=%s", instanceId, commandForLog)
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	var cmd *exec.Cmd
	switch shell {
	case "bat", "cmd":
		cmd = exec.CommandContext(ctx, "cmd", "/c", wrapCmdCommand(req.Command))
	case "powershell":
		cmd = exec.CommandContext(ctx, "powershell", "-Command", wrapPowerShellCommand(req.Command))
	case "pwsh":
		cmd = exec.CommandContext(ctx, "pwsh", "-Command", wrapPowerShellCommand(req.Command))
	case "bash":
		cmd = exec.CommandContext(ctx, "bash", "-c", req.Command)
	case "sh":
		cmd = exec.CommandContext(ctx, "sh", "-c", req.Command)
	default:
		cmd = exec.CommandContext(ctx, shell, "-c", req.Command)
	}

	if len(req.Env) > 0 {
		cmd.Env = os.Environ()
		for k, v := range req.Env {
			cmd.Env = append(cmd.Env, k+"="+v)
		}
	}

	startTime := time.Now()
	outputCapture := utils.NewSharedOutputCapture(utils.CommandOutputLimitBytes)
	stdoutWriter := outputCapture.StdoutWriter()
	stderrWriter := outputCapture.StderrWriter()
	var stdoutStreamWriter *scpStreamLogWriter
	var stderrStreamWriter *scpStreamLogWriter
	if isSCPCommand {
		stdoutStreamWriter = newSCPStreamLogWriter(instanceId, "stdout", shell, formatSCPLogContext(logContext))
		stderrStreamWriter = newSCPStreamLogWriter(instanceId, "stderr", shell, formatSCPLogContext(logContext))
		stdoutWriter = io.MultiWriter(outputCapture.StdoutWriter(), stdoutStreamWriter)
		stderrWriter = io.MultiWriter(outputCapture.StderrWriter(), stderrStreamWriter)
	}
	// 流式：按行 publish stdout/stderr 到 NATS 主题（与 outputCapture 并存，最终全量结果不变）
	var stdoutNatsWriter *streamLogWriter
	var stderrNatsWriter *streamLogWriter
	if req.StreamLogs && req.StreamLogTopic != "" && localStreamPublisher != nil {
		logger.Infof("[Local Execute] Instance: %s, 流式输出已启用 topic=%s execution_id=%s", instanceId, req.StreamLogTopic, req.ExecutionID)
		stdoutNatsWriter = newStreamLogWriter(localStreamPublisher, req.StreamLogTopic, req.ExecutionID, "stdout")
		stderrNatsWriter = newStreamLogWriter(localStreamPublisher, req.StreamLogTopic, req.ExecutionID, "stderr")
		stdoutWriter = io.MultiWriter(stdoutWriter, stdoutNatsWriter)
		stderrWriter = io.MultiWriter(stderrWriter, stderrNatsWriter)
	}
	cmd.Stdout = stdoutWriter
	cmd.Stderr = stderrWriter

	if err := cmd.Start(); err != nil {
		message := fmt.Sprintf("failed to start command: %v", err)
		logger.Errorf("[Local Execute] Instance: %s, %s", instanceId, message)
		if isSCPCommand {
			logger.Warnf("[SCP] Instance: %s, failure | stage=start | cause=executor_start_failed | next=check_executor_runtime | %s | error=%v", instanceId, formatSCPLogContext(logContext), err)
			logger.Debugf("[SCP] Instance: %s, command=%s", instanceId, commandForLog)
		}
		return ExecuteResponse{
			Output:     message,
			InstanceId: instanceId,
			Success:    false,
			Code:       utils.ErrorCodeExecutionFailure,
			Error:      message,
		}
	}

	type waitResult struct {
		err error
	}
	waitCh := make(chan waitResult, 1)
	go func() {
		waitCh <- waitResult{err: cmd.Wait()}
	}()

	var err error
	if isSCPCommand {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case result := <-waitCh:
				err = result.err
				goto commandFinished
			case <-ticker.C:
				elapsed := time.Since(startTime).Round(time.Second)
				snapshot := outputCapture.Snapshot()
				bytesSoFar := snapshot.TotalWritten
				currentOutput := formatCapturedExecuteOutput(snapshot, shell)
				excerpt := outputExcerpt(currentOutput)
				logger.Infof("[SCP] Instance: %s, running | %s | elapsed=%s | output=%dB | last=%q", instanceId, formatSCPLogContext(logContext), elapsed, bytesSoFar, excerpt)
			case <-ctx.Done():
				result := <-waitCh
				err = result.err
				goto commandFinished
			}
		}
	} else {
		result := <-waitCh
		err = result.err
	}

commandFinished:
	if stdoutStreamWriter != nil {
		stdoutStreamWriter.Flush()
	}
	if stderrStreamWriter != nil {
		stderrStreamWriter.Flush()
	}
	if stdoutNatsWriter != nil {
		stdoutNatsWriter.Flush()
	}
	if stderrNatsWriter != nil {
		stderrNatsWriter.Flush()
	}

	duration := time.Since(startTime)
	snapshot := outputCapture.Snapshot()
	decodedOutput := formatCapturedExecuteOutput(snapshot, shell)

	var exitCode int
	if exitError, ok := err.(*exec.ExitError); ok {
		exitCode = exitError.ExitCode()
	}

	response := ExecuteResponse{
		Output:     decodedOutput,
		InstanceId: instanceId,
		Success:    err == nil && ctx.Err() != context.DeadlineExceeded,
	}

	if ctx.Err() == context.DeadlineExceeded {
		response.Code = utils.ErrorCodeTimeout
		response.Error = fmt.Sprintf("Command timed out after %v (timeout: %ds)", duration, req.ExecuteTimeout)
		logger.Warnf("[Local Execute] Instance: %s, Command timed out after %v", instanceId, duration)
		logger.Debugf("[Local Execute] Instance: %s, Partial output: %s", instanceId, decodedOutput)
		if isSCPCommand {
			excerpt := outputExcerpt(decodedOutput)
			cause, next := scpFailureAdvice(decodedOutput, exitCode, true)
			logger.Warnf("[SCP] Instance: %s, timeout | cause=%s | next=%s | %s | elapsed=%s/%ds | last=%q", instanceId, cause, next, formatSCPLogContext(logContext), duration.Round(time.Second), req.ExecuteTimeout, excerpt)
		}
	} else if err != nil {
		response.Code = utils.ErrorCodeExecutionFailure
		response.Error = fmt.Sprintf("Command execution failed with exit code %d: %v", exitCode, err)
		logger.Warnf("[Local Execute] Instance: %s, Command execution failed after %v, exit code: %d", instanceId, duration, exitCode)
		logger.Debugf("[Local Execute] Instance: %s, Error: %v", instanceId, err)
		logger.Debugf("[Local Execute] Instance: %s, Full output: %s", instanceId, decodedOutput)

		if isSCPCommand {
			excerpt := outputExcerpt(decodedOutput)
			cause, next := scpFailureAdvice(decodedOutput, exitCode, false)
			logger.Warnf("[SCP] Instance: %s, failure | cause=%s | next=%s | exit=%d | %s | duration=%s | last=%q", instanceId, cause, next, exitCode, formatSCPLogContext(logContext), duration.Round(time.Second), excerpt)
			logger.Debugf("[SCP] Instance: %s, raw_error=%v", instanceId, err)
		}
	} else {
		logger.Debugf("[Local Execute] Instance: %s, Command executed successfully in %v", instanceId, duration)
		logger.Debugf("[Local Execute] Instance: %s, Output length: %d bytes", instanceId, len(decodedOutput))
		if snapshot.Truncated {
			logger.Warnf("[Local Execute] Instance: %s, Output exceeded shared capture limit and was truncated (stdout_dropped=%dB stderr_dropped=%dB total_written=%dB)", instanceId, snapshot.StdoutDropped, snapshot.StderrDropped, snapshot.TotalWritten)
		}
		if len(decodedOutput) > 0 {
			logger.Debugf("[Local Execute] Instance: %s, Output: %s", instanceId, decodedOutput)
		}
		if isSCPCommand {
			logger.Infof("[SCP] Instance: %s, success | %s | duration=%s | output=%dB", instanceId, formatSCPLogContext(logContext), duration.Round(time.Second), len(decodedOutput))
		}
	}

	return response
}

func sampleBytes(output []byte, limit int) []byte {
	if len(output) <= limit {
		return output
	}

	return output[:limit]
}

func truncateForLog(value string, limit int) string {
	if len(value) <= limit {
		return value
	}

	return value[:limit] + "..."
}

type scpStreamLogWriter struct {
	instanceId string
	streamName string
	shell      string
	logContext string
	buffer     bytes.Buffer
}

func newSCPStreamLogWriter(instanceId, streamName, shell, logContext string) *scpStreamLogWriter {
	return &scpStreamLogWriter{
		instanceId: instanceId,
		streamName: streamName,
		shell:      shell,
		logContext: logContext,
	}
}

func (w *scpStreamLogWriter) Write(p []byte) (int, error) {
	written, err := w.buffer.Write(p)
	if err != nil {
		return written, err
	}

	reader := bufio.NewReader(bytes.NewReader(w.buffer.Bytes()))
	var remaining bytes.Buffer
	for {
		line, readErr := reader.ReadString('\n')
		if readErr != nil {
			remaining.WriteString(line)
			if readErr == io.EOF {
				break
			}
			return written, readErr
		}
		w.logLine(line)
	}

	w.buffer.Reset()
	remaining.WriteTo(&w.buffer)
	return len(p), nil
}

func (w *scpStreamLogWriter) Flush() {
	if w.buffer.Len() == 0 {
		return
	}
	w.logLine(w.buffer.String())
	w.buffer.Reset()
}

func (w *scpStreamLogWriter) logLine(line string) {
	decoded := decodeExecuteOutput([]byte(line), w.shell)
	message := strings.TrimSpace(decoded)
	if message == "" {
		return
	}
	logger.Debugf("[SCP] Instance: %s, stream=%s | %s | %q", w.instanceId, w.streamName, w.logContext, truncateForLog(message, 400))
}

func outputExcerpt(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}

	trimmed = strings.ReplaceAll(trimmed, "\n", " | ")
	trimmed = strings.ReplaceAll(trimmed, "\r", " ")
	return truncateForLog(trimmed, 240)
}

func formatCapturedExecuteOutput(snapshot utils.OutputSnapshot, shell string) string {
	stdout := decodeExecuteOutput(snapshot.Stdout, shell)
	stderr := decodeExecuteOutput(snapshot.Stderr, shell)
	return utils.FormatCapturedOutput(stdout, stderr, snapshot)
}

func formatSCPLogContext(logContext string) string {
	if strings.TrimSpace(logContext) == "" {
		return "transfer=unknown"
	}

	return logContext
}

func decodeExecuteOutput(output []byte, shell string) string {
	decoded, _ := decodeExecuteOutputWithStrategy(output, shell)
	return decoded
}

func decodeExecuteOutputWithStrategy(output []byte, shell string) (string, string) {
	return decodeExecuteOutputWithStrategyForOS(output, shell, runtime.GOOS)
}

func decodeExecuteOutputWithStrategyForOS(output []byte, shell string, goos string) (string, string) {
	if decoded, ok := decodeUTF16LEOutput(output); ok {
		return decoded, "utf16le"
	}

	if utf8.Valid(output) {
		return string(output), "utf8"
	}

	if goos == "windows" && (shell == ShellTypeBat || shell == ShellTypeCmd || shell == ShellTypePowerShell || shell == ShellTypePwsh) {
		if decoded, err := simplifiedchinese.GBK.NewDecoder().Bytes(output); err == nil {
			return string(decoded), "gbk"
		}
	}

	return string(output), "raw"
}

func wrapPowerShellCommand(command string) string {
	return wrapPowerShellCommandForOS(command, runtime.GOOS)
}

func wrapPowerShellCommandForOS(command, goos string) string {
	if goos != "windows" {
		return command
	}

	return "$utf8NoBom = New-Object System.Text.UTF8Encoding($false); " +
		"[Console]::InputEncoding = $utf8NoBom; " +
		"[Console]::OutputEncoding = $utf8NoBom; " +
		"$OutputEncoding = $utf8NoBom; " +
		"if (Get-Command chcp.com -ErrorAction SilentlyContinue) { chcp.com 65001 > $null }; " +
		command
}

func wrapCmdCommand(command string) string {
	return wrapCmdCommandForOS(command, runtime.GOOS)
}

func wrapCmdCommandForOS(command, goos string) string {
	if goos != "windows" {
		return command
	}

	return "chcp 65001 >nul && " + command
}

func decodeUTF16LEOutput(output []byte) (string, bool) {
	if len(output) < 2 {
		return "", false
	}

	fromBOM := false
	if output[0] == 0xff && output[1] == 0xfe {
		fromBOM = true
		output = output[2:]
	}

	if len(output) < 2 || len(output)%2 != 0 {
		return "", false
	}

	if !fromBOM && !looksLikeUTF16LE(output) {
		return "", false
	}

	words := make([]uint16, 0, len(output)/2)
	for i := 0; i < len(output); i += 2 {
		words = append(words, uint16(output[i])|uint16(output[i+1])<<8)
	}

	return string(utf16.Decode(words)), true
}

func looksLikeUTF16LE(output []byte) bool {
	if !bytes.Contains(output, []byte{0x00}) {
		return false
	}

	zeroCount := 0
	for i := 1; i < len(output); i += 2 {
		if output[i] == 0x00 {
			zeroCount++
		}
	}

	return zeroCount >= len(output)/4
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
	logger.Debugf("[SCP] Instance: %s, analyze_failure | exit_code=%d | cause=%s | output=%q", instanceId, exitCode, classifySCPFailure(output, exitCode), outputExcerpt(output))

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

func scpFailureAdvice(output string, exitCode int, timedOut bool) (string, string) {
	cause := classifySCPFailure(output, exitCode)
	if timedOut && cause == "unknown" {
		cause = "transfer_timeout"
	}

	switch cause {
	case "host_key_problem":
		return cause, "check_target_host_key_or_known_hosts"
	case "auth_failure":
		return cause, "check_password_private_key_or_passphrase"
	case "network_or_dns":
		return cause, "check_host_reachability_port_and_firewall"
	case "path_not_found":
		return cause, "check_source_and_target_path"
	case "missing_sshpass":
		return cause, "check_executor_dependencies"
	case "transfer_timeout":
		return cause, "check_network_speed_target_response_and_interactive_prompts"
	default:
		return "unknown", "check_debug_stream_and_full_output"
	}
}

func classifySCPFailure(output string, exitCode int) string {
	lowerOutput := strings.ToLower(output)

	switch {
	case strings.Contains(lowerOutput, "are you sure you want to continue connecting"),
		strings.Contains(lowerOutput, "host key verification failed"),
		strings.Contains(lowerOutput, "remote host identification has changed"),
		exitCode == 6:
		return "host_key_problem"
	case strings.Contains(lowerOutput, "permission denied"),
		strings.Contains(lowerOutput, "authentication failed"),
		exitCode == 5:
		return "auth_failure"
	case strings.Contains(lowerOutput, "connection timed out"),
		strings.Contains(lowerOutput, "i/o timeout"),
		strings.Contains(lowerOutput, "no route to host"),
		strings.Contains(lowerOutput, "connection refused"),
		strings.Contains(lowerOutput, "connection reset"),
		strings.Contains(lowerOutput, "could not resolve hostname"):
		return "network_or_dns"
	case strings.Contains(lowerOutput, "no such file or directory"):
		return "path_not_found"
	case strings.Contains(lowerOutput, "sshpass: command not found"):
		return "missing_sshpass"
	default:
		return "unknown"
	}
}

func subscribeLocalExecutor(sub subscriber, instanceId *string) error {
	subject := fmt.Sprintf("local.execute.%s", *instanceId)
	logger.Infof("[Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		logger.Debugf("[Local Subscribe] Instance: %s, Received message, size: %d bytes", *instanceId, len(msg.Data))
		respondLocalExecuteMessage(natsInboundMsg{msg}, msg.Data, *instanceId)
	})
	return err
}

func SubscribeLocalExecutor(nc *nats.Conn, instanceId *string) {
	// 记录本进程 NATS 连接，供 Execute 在 StreamLogs 时按行 publish。
	// 守卫 nil，避免把 nil *nats.Conn 装进非 nil 接口造成误判/空指针。
	if nc != nil {
		localStreamPublisher = nc
	}
	if err := subscribeLocalExecutorFn(nc, instanceId); err != nil {
		logger.Errorf("[Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func subscribeDownloadToLocal(sub subscriber, nc downloadConn, instanceId *string) error {
	subject := fmt.Sprintf("download.local.%s", *instanceId)
	logger.Infof("[Download Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		respondDownloadToLocalSubscription(natsInboundMsg{msg}, *instanceId, nc)
	})
	return err
}

func SubscribeDownloadToLocal(nc *nats.Conn, instanceId *string) {
	if err := subscribeDownloadToLocalFn(nc, nc, instanceId); err != nil {
		logger.Errorf("[Download Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func subscribeUnzipToLocal(sub subscriber, instanceId *string) error {
	subject := fmt.Sprintf("unzip.local.%s", *instanceId)
	logger.Infof("[Unzip Local Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		respondUnzipToLocalSubscription(natsInboundMsg{msg}, *instanceId)
	})
	return err
}

func SubscribeUnzipToLocal(nc *nats.Conn, instanceId *string) {
	if err := subscribeUnzipToLocalFn(nc, instanceId); err != nil {
		logger.Errorf("[Unzip Local Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}

func subscribeHealthCheck(sub subscriber, instanceId *string) error {
	subject := fmt.Sprintf("health.check.%s", *instanceId)
	logger.Infof("[Health Check Subscribe] Instance: %s, Subscribing to subject: %s", *instanceId, subject)

	_, err := sub.Subscribe(subject, func(msg *nats.Msg) {
		respondHealthCheckSubscription(natsInboundMsg{msg}, *instanceId, subject)
	})
	return err
}

func SubscribeHealthCheck(nc *nats.Conn, instanceId *string) {
	if err := subscribeHealthCheckFn(nc, instanceId); err != nil {
		logger.Errorf("[Health Check Subscribe] Instance: %s, Failed to subscribe: %v", *instanceId, err)
	}
}
