package utils

import (
	"context"
	"errors"
	"fmt"
	"nats-executor/jetstream"
	"nats-executor/logger"
	"nats-executor/utils/downloaderr"
	"path/filepath"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
)

type fileDownloader interface {
	DownloadToFile(ctx context.Context, fileKey, targetPath, fileName string) error
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
	if err := validateDownloadFileName(req.FileName); err != nil {
		return err
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

	if err := client.DownloadToFile(ctx, req.FileKey, req.TargetPath, req.FileName); err != nil {
		switch downloaderr.KindOf(err) {
		case downloaderr.KindTimeout:
			return downloaderr.New(downloaderr.KindTimeout, fmt.Errorf("download operation timed out: %w", err))
		case downloaderr.KindCanceled:
			return downloaderr.New(downloaderr.KindCanceled, fmt.Errorf("download operation canceled: %w", err))
		case downloaderr.KindIO:
			return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to finalize downloaded file: %w", err))
		case downloaderr.KindDependency:
			return downloaderr.New(downloaderr.KindDependency, fmt.Errorf("failed to download file: %w", err))
		default:
			if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, nats.ErrTimeout) {
				return downloaderr.New(downloaderr.KindTimeout, fmt.Errorf("download operation timed out: %w", err))
			}
			if errors.Is(err, context.Canceled) {
				return downloaderr.New(downloaderr.KindCanceled, fmt.Errorf("download operation canceled: %w", err))
			}
			return downloaderr.New(downloaderr.KindDependency, fmt.Errorf("failed to download file: %w", err))
		}
	}

	logger.Debugf("[DownloadFile] Download completed successfully!")
	return nil
}

func validateDownloadFileName(fileName string) error {
	trimmed := strings.TrimSpace(fileName)
	if trimmed == "." || trimmed == ".." || filepath.IsAbs(trimmed) || strings.ContainsAny(trimmed, `/\`) {
		return fmt.Errorf("file_name must not contain path separators or be absolute")
	}
	return nil
}
