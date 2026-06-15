package local

// 支持的脚本类型常量
const (
	ShellTypeSh         = "sh"         // Unix Shell（默认）
	ShellTypeBash       = "bash"       // Bash Shell
	ShellTypeBat        = "bat"        // Windows 批处理（cmd.exe）
	ShellTypeCmd        = "cmd"        // Windows 命令提示符（同 bat）
	ShellTypePowerShell = "powershell" // Windows PowerShell
	ShellTypePwsh       = "pwsh"       // PowerShell Core（跨平台）
)

type ExecuteRequest struct {
	Command        string            `json:"command"`
	ExecuteTimeout int               `json:"execute_timeout"`
	Shell          string            `json:"shell,omitempty"` // 脚本类型，支持：sh, bash, bat, cmd, powershell, pwsh，默认 "sh"
	Env            map[string]string `json:"-"`
	LogCommand     string            `json:"-"`
	LogContext     string            `json:"-"`
	ExecutionID    string            `json:"execution_id,omitempty"`     // 执行 ID（写入流事件）
	StreamLogs     bool              `json:"stream_logs,omitempty"`      // 是否按行流式 publish stdout/stderr
	StreamLogTopic string            `json:"stream_log_topic,omitempty"` // 行事件发布主题
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Code       string `json:"code,omitempty"`
	Error      string `json:"error,omitempty"` // 添加错误字段，omitempty表示为空时不序列化
}

type HealthCheckResponse struct {
	Success    bool   `json:"success"`
	Status     string `json:"status"` // "ok"
	InstanceId string `json:"instance_id"`
	Timestamp  string `json:"timestamp"`
}
