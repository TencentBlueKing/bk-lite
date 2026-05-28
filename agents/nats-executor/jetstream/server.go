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

type objectStoreManager interface {
	ObjectStore(bucket string) (nats.ObjectStore, error)
}

var (
	createTempDownloadFile = func(dir, pattern string) (*os.File, error) {
		return os.CreateTemp(dir, pattern)
	}
	renameDownloadFile = os.Rename
	removeDownloadFile = os.Remove
	syncDownloadFile   = func(f *os.File) error { return f.Sync() }
	closeDownloadFile  = func(f *os.File) error { return f.Close() }
	jetStreamFromConn  = func(nc *nats.Conn) (objectStoreManager, error) { return nc.JetStream() }
)

type JetStreamClient struct {
	nc          *nats.Conn
	js          nats.JetStreamContext
	objectStore objectStoreGetter
}

func NewJetStreamClient(nc *nats.Conn, bucketName string) (*JetStreamClient, error) {
	js, err := jetStreamFromConn(nc)
	if err != nil {
		return nil, fmt.Errorf("failed to get JetStream context: %v", err)
	}

	return newJetStreamClientFromContext(nc, js, bucketName)
}

func newJetStreamClientFromContext(nc *nats.Conn, js objectStoreManager, bucketName string) (*JetStreamClient, error) {
	store, err := ensureObjectStore(js, bucketName)
	if err != nil {
		return nil, err
	}

	return &JetStreamClient{nc: nc, objectStore: store}, nil
}

func ensureObjectStore(js objectStoreManager, bucketName string) (nats.ObjectStore, error) {
	store, err := js.ObjectStore(bucketName)
	if err != nil {
		if err == nats.ErrBucketNotFound {
			return nil, fmt.Errorf("object store bucket %q not found: %w", bucketName, err)
		}
		return nil, fmt.Errorf("failed to access object store: %v", err)
	}
	return store, nil
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
			_ = closeDownloadFile(tempFile)
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

	if err := syncDownloadFile(tempFile); err != nil {
		cleanupTemp()
		return downloaderr.New(downloaderr.KindIO, fmt.Errorf("failed to sync temporary file %s: %w", tempPath, err))
	}

	if err := closeDownloadFile(tempFile); err != nil {
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
