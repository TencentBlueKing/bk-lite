package local

type ExecuteRequest struct {
	Command        string `json:"command"`
	ExecuteTimeout int    `json:"execute_timeout"`
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
	Error      string `json:"error,omitempty"` // 添加错误字段，omitempty表示为空时不序列化
}
