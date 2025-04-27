package ssh

type ExecuteRequest struct {
	Command        string `json:"command"`
	ExecuteTimeout int    `json:"execute_timeout"`
	Host           string `json:"host"`
	User           string `json:"user"`
	Password       string `json:"password"`
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
}

type DownloadFileRequest struct {
	BucketName     string `json:"bucket_name"`
	FileName       string `json:"file_name"`
	FileKey        string `json:"file_key"`
	TargetPath     string `json:"target_path"`
	Host           string `json:"host"`
	User           string `json:"user"`
	Password       string `json:"password"`
	ExecuteTimeout int    `json:"execute_timeout"`
}
