package jetstream

import (
	"context"
	"errors"
	"fmt"
	"io"
	"nats-executor/logger"
	"nats-executor/utils/downloaderr"
	"os"
	"path/filepath"
	"strings"

	"github.com/nats-io/nats.go"
)

type objectStoreGetter interface {
	Get(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error)
}

var (
	createTempDownloadFile = func(dir, pattern string) (*os.File, error) {
		return os.CreateTemp(dir, pattern)
	}
	renameDownloadFile = os.Rename
	removeDownloadFile = os.Remove
)

type JetStreamClient struct {
	nc          *nats.Conn
	js          nats.JetStreamContext
	objectStore objectStoreGetter
}

func NewJetStreamClient(nc *nats.Conn, bucketName string) (*JetStreamClient, error) {
	js, err := nc.JetStream()
	if err != nil {
		return nil, fmt.Errorf("failed to get JetStream context: %v", err)
	}

	store, err := js.ObjectStore(bucketName)
	if err != nil {
		if err == nats.ErrBucketNotFound {
			store, err = js.CreateObjectStore(&nats.ObjectStoreConfig{
				Bucket:      bucketName,
				Description: "File distribution bucket",
			})
		}
		if err != nil {
			return nil, fmt.Errorf("failed to create or access object store: %v", err)
		}
	}

	return &JetStreamClient{nc: nc, js: js, objectStore: store}, nil
}

func (jsc *JetStreamClient) DownloadToFile(ctx context.Context, fileKey, targetPath, fileName string) error {
	if err := validateTargetFileName(fileName); err != nil {
		return err
	}
	if ctx == nil {
		ctx = context.Background()
	}

	obj, err := jsc.objectStore.Get(fileKey, nats.Context(ctx))
	if err != nil {
		kind := downloaderr.KindDependency
		if errors.Is(err, context.Canceled) {
			kind = downloaderr.KindCanceled
		} else if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, nats.ErrTimeout) {
			kind = downloaderr.KindTimeout
		}
		return downloaderr.New(kind, fmt.Errorf("failed to get object from store with key %s: %w", fileKey, err))
	}
	defer obj.Close()

	fullPath := filepath.Join(targetPath, fileName)
	tempFile, err := createTempDownloadFile(targetPath, fileName+".tmp-*")
	if err != nil {
		return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to create temporary file in %s: %w", targetPath, err))
	}
	tempPath := tempFile.Name()
	tempClosed := false
	cleanupTemp := func() {
		if !tempClosed {
			_ = tempFile.Close()
			tempClosed = true
		}
		_ = removeDownloadFile(tempPath)
	}

	written, err := io.Copy(tempFile, obj)
	if err != nil {
		cleanupTemp()
		kind := downloaderr.KindDependency
		if errors.Is(err, context.Canceled) {
			kind = downloaderr.KindCanceled
		} else if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, nats.ErrTimeout) {
			kind = downloaderr.KindTimeout
		}
		return downloaderr.New(kind, fmt.Errorf("failed to write file: %w", err))
	}

	if err := tempFile.Sync(); err != nil {
		cleanupTemp()
		return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to sync temporary file %s: %w", tempPath, err))
	}

	if err := tempFile.Close(); err != nil {
		tempClosed = true
		_ = removeDownloadFile(tempPath)
		return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to close temporary file %s: %w", tempPath, err))
	}
	tempClosed = true

	if err := renameDownloadFile(tempPath, fullPath); err != nil {
		_ = removeDownloadFile(tempPath)
		return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to finalize download to %s: %w", fullPath, err))
	}

	logger.Debugf("[JetStream] File successfully downloaded to %s (%d bytes)", fullPath, written)
	return nil
}

func validateTargetFileName(fileName string) error {
	trimmed := strings.TrimSpace(fileName)
	if trimmed == "." || trimmed == ".." || filepath.IsAbs(trimmed) || strings.ContainsAny(trimmed, `/\`) {
		return fmt.Errorf("illegal file name: %s", fileName)
	}
	return nil
}
