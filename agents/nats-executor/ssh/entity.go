package ssh

type ExecuteRequest struct {
	Command        string `json:"command"`
	ExecuteTimeout int    `json:"execute_timeout"`
	Host           string `json:"host"`
	Port           uint   `json:"port"`
	User           string `json:"user"`
	Password       string `json:"password"`    // 密码认证（可选）
	PrivateKey     string `json:"private_key"` // PEM 格式私钥内容（可选）
	Passphrase     string `json:"passphrase"`  // 私钥密码短语（可选）
	ConnectionTest bool   `json:"connection_test,omitempty"`
	ExecutionID    string `json:"execution_id,omitempty"`
	StreamLogs     bool   `json:"stream_logs,omitempty"`
	StreamLogTopic string `json:"stream_log_topic,omitempty"`
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Code       string `json:"code,omitempty"`
	Error      string `json:"error,omitempty"` // 添加错误字段
	Stage      string `json:"stage,omitempty"`
	Category   string `json:"category,omitempty"`
}

type DownloadFileRequest struct {
	BucketName     string `json:"bucket_name"`
	FileName       string `json:"file_name"`
	FileKey        string `json:"file_key"`
	TargetPath     string `json:"target_path"`
	LocalPath      string `json:"local_path"`
	Host           string `json:"host"`
	Port           uint   `json:"port"`
	User           string `json:"user"`
	Password       string `json:"password"`    // 密码认证（可选）
	PrivateKey     string `json:"private_key"` // PEM 格式私钥内容（可选）
	Passphrase     string `json:"passphrase"`  // 私钥密码短语（可选）
	FastFail       bool   `json:"fast_fail,omitempty"`
	ExecuteTimeout int    `json:"execute_timeout"`
}

type UploadFileRequest struct {
	User           string `json:"user"`            // SSH 用户名
	Host           string `json:"host"`            // 目标主机地址
	Port           uint   `json:"port"`            // SSH 端口
	Password       string `json:"password"`        // SSH 密码（可选）
	PrivateKey     string `json:"private_key"`     // PEM 格式私钥内容（可选）
	Passphrase     string `json:"passphrase"`      // 私钥密码短语（可选）
	SourcePath     string `json:"source_path"`     // 本地文件路径
	TargetPath     string `json:"target_path"`     // 远程目标路径
	ExecuteTimeout int    `json:"execute_timeout"` // 执行超时时间（秒）
}
