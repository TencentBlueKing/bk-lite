package local

type ExecuteRequest struct {
	Command        string `json:"command"`
	ExecuteTimeout int    `json:"execute_timeout"`
}

type ExecuteResponse struct {
	Output     string `json:"result"`
	InstanceId string `json:"instance_id"`
	Success    bool   `json:"success"`
}

type DownloadFileRequest struct {
	BucketName     string `json:"bucket_name"`
	FileKey        string `json:"file_key"`
	FileName       string `json:"file_name"`
	TargetPath     string `json:"target_path"`
	ExecuteTimeout int    `json:"execute_timeout"`
}
