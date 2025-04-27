package local

import (
	"context"
	"fmt"
	"github.com/nats-io/nats.go"
	"log"
	"nats-executor/jetstream"
	"os/exec"
	"time"
)

func Execute(req ExecuteRequest, instanceId string) ExecuteResponse {
	// Execute the command with timeout
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	log.Printf("Executing command: %s with timeout: %d seconds", req.Command, req.ExecuteTimeout)
	cmd := exec.CommandContext(ctx, "sh", "-c", req.Command)
	output, err := cmd.CombinedOutput()
	response := ExecuteResponse{
		Output:     string(output),
		InstanceId: instanceId,
		Success:    err == nil && ctx.Err() != context.DeadlineExceeded,
	}

	if ctx.Err() == context.DeadlineExceeded {
		log.Printf("Command timed out")
	} else if err != nil {
		log.Printf("Command execution error: %v", err)
	} else {
		log.Printf("Command output: %s", output)
	}

	return response

}

func DownloadFile(req DownloadFileRequest, nc *nats.Conn, instanceId string) ExecuteResponse {
	// 设置超时管理
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	log.Printf("Starting download with file_key: %s, target_path: %s, file_name: %s, timeout: %d seconds", req.FileKey, req.TargetPath, req.FileName, req.ExecuteTimeout)

	// 创建 JetStream 客户端
	client, err := jetstream.NewJetStreamClient(nc, req.BucketName)
	if err != nil {
		return ExecuteResponse{
			Success:    false,
			Output:     fmt.Sprintf("Failed to create JetStream client: %v", err),
			InstanceId: instanceId,
		}
	}

	// 执行下载操作
	err = client.DownloadToFile(req.FileKey, req.TargetPath, req.FileName)
	if err != nil {
		log.Printf("Download error: %v", err)
		return ExecuteResponse{
			Success:    false,
			Output:     fmt.Sprintf("Failed to download file: %v", err),
			InstanceId: instanceId,
		}
	}

	log.Println("Download completed successfully!")

	// 如果超时
	if ctx.Err() == context.DeadlineExceeded {
		log.Printf("Download operation timed out")
		return ExecuteResponse{
			Success:    false,
			Output:     "Download operation timed out",
			InstanceId: instanceId,
		}
	}

	// 成功完成
	return ExecuteResponse{
		Success:    true,
		Output:     fmt.Sprintf("File successfully downloaded to %s/%s", req.TargetPath, req.FileName),
		InstanceId: instanceId,
	}
}
