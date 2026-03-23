package utils

import (
	"context"
	"fmt"
	"nats-executor/jetstream"
	"nats-executor/logger"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
)

type fileDownloader interface {
	DownloadToFile(fileKey, targetPath, fileName string) error
}

var newJetStreamClient = func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
	return jetstream.NewJetStreamClient(nc, bucketName)
}

type DownloadFileRequest struct {
	BucketName     string `json:"bucket_name"`
	FileKey        string `json:"file_key"`
	FileName       string `json:"file_name"`
	TargetPath     string `json:"target_path"`
	ExecuteTimeout int    `json:"execute_timeout"`
}

func DownloadFile(req DownloadFileRequest, nc *nats.Conn) error {
	if strings.TrimSpace(req.BucketName) == "" || strings.TrimSpace(req.FileKey) == "" || strings.TrimSpace(req.FileName) == "" || strings.TrimSpace(req.TargetPath) == "" {
		return fmt.Errorf("bucket_name, file_key, file_name, and target_path are required")
	}

	if req.ExecuteTimeout <= 0 {
		return fmt.Errorf("execute timeout must be greater than 0")
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(req.ExecuteTimeout)*time.Second)
	defer cancel()

	logger.Debugf("[DownloadFile] Starting download with file_key: %s, target_path: %s, file_name: %s, timeout: %d seconds", req.FileKey, req.TargetPath, req.FileName, req.ExecuteTimeout)

	client, err := newJetStreamClient(nc, req.BucketName)
	if err != nil {
		return fmt.Errorf("failed to create JetStream client: %w", err)
	}

	errCh := make(chan error, 1)
	go func() {
		errCh <- client.DownloadToFile(req.FileKey, req.TargetPath, req.FileName)
	}()

	select {
	case <-ctx.Done():
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("download operation timed out")
		}
		return fmt.Errorf("download operation canceled: %w", ctx.Err())
	case err := <-errCh:
		if err != nil {
			return fmt.Errorf("failed to download file: %w", err)
		}
	}

	logger.Debugf("[DownloadFile] Download completed successfully!")
	return nil
}
