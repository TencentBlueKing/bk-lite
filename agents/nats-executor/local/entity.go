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
	Command        string `json:"command"`
	ExecuteTimeout int    `json:"execute_timeout"`
	Shell          string `json:"shell,omitempty"` // 脚本类型，支持：sh, bash, bat, cmd, powershell, pwsh，默认 "sh"
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Error      string `json:"error,omitempty"` // 添加错误字段，omitempty表示为空时不序列化
}

type HealthCheckResponse struct {
	Success    bool   `json:"success"`
	Status     string `json:"status"` // "ok"
	InstanceId string `json:"instance_id"`
	Timestamp  string `json:"timestamp"`
}
