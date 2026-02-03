package utils

import (
	"context"
	"fmt"
	"nats-executor/jetstream"
	"nats-executor/logger"
	"time"

	"github.com/nats-io/nats.go"
)

type DownloadFileRequest struct {
	BucketName     string `json:"bucket_name"`
	FileKey        string `json:"file_key"`
	FileName       string `json:"file_name"`
	TargetPath     string `json:"target_path"`
	ExecuteTimeout int    `json:"execute_timeout"`
}

func DownloadFile(req DownloadFileRequest, nc *nats.Conn) error {
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	logger.Debugf("[DownloadFile] Starting download with file_key: %s, target_path: %s, file_name: %s, timeout: %d seconds", req.FileKey, req.TargetPath, req.FileName, req.ExecuteTimeout)

	client, err := jetstream.NewJetStreamClient(nc, req.BucketName)
	if err != nil {
		return fmt.Errorf("failed to create JetStream client: %w", err)
	}

	if err := client.DownloadToFile(req.FileKey, req.TargetPath, req.FileName); err != nil {
		return fmt.Errorf("failed to download file: %w", err)
	}

	if ctx.Err() == context.DeadlineExceeded {
		return fmt.Errorf("download operation timed out")
	}

	logger.Debugf("[DownloadFile] Download completed successfully!")
	return nil
}
