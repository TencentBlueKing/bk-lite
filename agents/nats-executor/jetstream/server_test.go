package jetstream

import (
	"context"
	"errors"
	"io"
	"nats-executor/utils/downloaderr"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/nats-io/nats.go"
)

type stubObjectStore struct {
	get func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error)
}

func (s stubObjectStore) Get(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
	if s.get == nil {
		return nil, nil
	}
	return s.get(name, opts...)
}

type stubObjectResult struct {
	read  func(p []byte) (int, error)
	close func() error
}

func (s stubObjectResult) Read(p []byte) (int, error) {
	if s.read == nil {
		return 0, io.EOF
	}
	return s.read(p)
}

func (s stubObjectResult) Close() error {
	if s.close == nil {
		return nil
	}
	return s.close()
}

func (s stubObjectResult) Info() (*nats.ObjectInfo, error) { return &nats.ObjectInfo{}, nil }
func (s stubObjectResult) Error() error                    { return nil }

func withTempDownloadFileCreator(tb testing.TB, fn func(string, string) (*os.File, error)) {
	tb.Helper()
	original := createTempDownloadFile
	createTempDownloadFile = fn
	tb.Cleanup(func() {
		createTempDownloadFile = original
	})
}

func withDownloadRename(tb testing.TB, fn func(string, string) error) {
	tb.Helper()
	original := renameDownloadFile
	renameDownloadFile = fn
	tb.Cleanup(func() {
		renameDownloadFile = original
	})
}

func withDownloadRemove(tb testing.TB, fn func(string) error) {
	tb.Helper()
	original := removeDownloadFile
	removeDownloadFile = fn
	tb.Cleanup(func() {
		removeDownloadFile = original
	})
}

func TestDownloadToFileSucceeds(t *testing.T) {
	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				if name != "demo-key" {
					t.Fatalf("unexpected object key: %s", name)
				}
				reader := strings.NewReader("hello world")
				return stubObjectResult{
					read:  reader.Read,
					close: func() error { return nil },
				}, nil
			},
		},
	}

	targetDir := t.TempDir()
	if err := client.DownloadToFile(context.Background(), "demo-key", targetDir, "demo.txt"); err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	data, err := os.ReadFile(filepath.Join(targetDir, "demo.txt"))
	if err != nil {
		t.Fatalf("expected downloaded file: %v", err)
	}
	if string(data) != "hello world" {
		t.Fatalf("unexpected file contents: %q", string(data))
	}

	matches, err := filepath.Glob(filepath.Join(targetDir, "demo.txt.tmp-*"))
	if err != nil {
		t.Fatalf("failed to check temp files: %v", err)
	}
	if len(matches) != 0 {
		t.Fatalf("expected temp files to be removed, found %v", matches)
	}
}

func TestDownloadToFilePropagatesObjectStoreError(t *testing.T) {
	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				return nil, errors.New("bucket unavailable")
			},
		},
	}

	err := client.DownloadToFile(context.Background(), "demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected object store error")
	}
	if !strings.Contains(err.Error(), "failed to get object from store with key demo-key: bucket unavailable") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindDependency {
		t.Fatalf("expected dependency error kind, got %s", downloaderr.KindOf(err))
	}
}

func TestDownloadToFilePropagatesCreateTempFileError(t *testing.T) {
	withTempDownloadFileCreator(t, func(dir, pattern string) (*os.File, error) {
		return nil, errors.New("disk full")
	})

	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				reader := strings.NewReader("payload")
				return stubObjectResult{
					read:  reader.Read,
					close: func() error { return nil },
				}, nil
			},
		},
	}

	err := client.DownloadToFile(context.Background(), "demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected create temp file error")
	}
	if !strings.Contains(err.Error(), "failed to create temporary file") || !strings.Contains(err.Error(), "disk full") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindIO {
		t.Fatalf("expected io error kind, got %s", downloaderr.KindOf(err))
	}
}

func TestDownloadToFilePropagatesCopyErrorAndRemovesTempFile(t *testing.T) {
	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				return stubObjectResult{
					read: func(p []byte) (int, error) {
						return 0, errors.New("stream corrupted")
					},
					close: func() error { return nil },
				}, nil
			},
		},
	}

	targetDir := t.TempDir()
	err := client.DownloadToFile(context.Background(), "demo-key", targetDir, "demo.txt")
	if err == nil {
		t.Fatal("expected write error")
	}
	if !strings.Contains(err.Error(), "failed to write file: stream corrupted") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindDependency {
		t.Fatalf("expected dependency error kind, got %s", downloaderr.KindOf(err))
	}
	if _, statErr := os.Stat(filepath.Join(targetDir, "demo.txt")); !os.IsNotExist(statErr) {
		t.Fatalf("expected final file to be absent, stat err=%v", statErr)
	}
	matches, globErr := filepath.Glob(filepath.Join(targetDir, "demo.txt.tmp-*"))
	if globErr != nil {
		t.Fatalf("failed to check temp files: %v", globErr)
	}
	if len(matches) != 0 {
		t.Fatalf("expected temp files to be removed, found %v", matches)
	}
}

func TestDownloadToFileKeepsExistingFileWhenRenameFails(t *testing.T) {
	withDownloadRename(t, func(oldPath, newPath string) error {
		return errors.New("rename blocked")
	})

	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				reader := strings.NewReader("new payload")
				return stubObjectResult{
					read:  reader.Read,
					close: func() error { return nil },
				}, nil
			},
		},
	}

	targetDir := t.TempDir()
	finalPath := filepath.Join(targetDir, "demo.txt")
	if err := os.WriteFile(finalPath, []byte("existing payload"), 0o600); err != nil {
		t.Fatalf("failed to create existing file: %v", err)
	}

	err := client.DownloadToFile(context.Background(), "demo-key", targetDir, "demo.txt")
	if err == nil {
		t.Fatal("expected rename error")
	}
	if !strings.Contains(err.Error(), "failed to finalize download") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindIO {
		t.Fatalf("expected io error kind, got %s", downloaderr.KindOf(err))
	}
	data, readErr := os.ReadFile(finalPath)
	if readErr != nil {
		t.Fatalf("failed to read existing file: %v", readErr)
	}
	if string(data) != "existing payload" {
		t.Fatalf("expected existing file to remain untouched, got %q", string(data))
	}
}

func TestDownloadToFilePassesContextToObjectStore(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				if len(opts) == 0 {
					t.Fatal("expected context option")
				}
				return nil, ctx.Err()
			},
		},
	}

	err := client.DownloadToFile(ctx, "demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected context cancellation error")
	}
	if !strings.Contains(err.Error(), "context canceled") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindCanceled {
		t.Fatalf("expected canceled error kind, got %s", downloaderr.KindOf(err))
	}
}

func TestDownloadToFileRejectsUnsafeFileName(t *testing.T) {
	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				t.Fatal("object store should not be queried for unsafe file names")
				return nil, nil
			},
		},
	}

	tests := []string{"../evil.txt", "/tmp/evil.txt", "nested/evil.txt", `..\evil.txt`}
	for _, fileName := range tests {
		t.Run(fileName, func(t *testing.T) {
			err := client.DownloadToFile(context.Background(), "demo-key", t.TempDir(), fileName)
			if err == nil {
				t.Fatal("expected unsafe file name to be rejected")
			}
			if !strings.Contains(err.Error(), "illegal file name") {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

func TestDownloadToFileRemoveFailureDoesNotMaskPrimaryError(t *testing.T) {
	withDownloadRemove(t, func(string) error {
		return errors.New("cleanup failed")
	})

	client := &JetStreamClient{
		objectStore: stubObjectStore{
			get: func(name string, opts ...nats.GetObjectOpt) (nats.ObjectResult, error) {
				return stubObjectResult{
					read: func(p []byte) (int, error) {
						return 0, errors.New("stream corrupted")
					},
					close: func() error { return nil },
				}, nil
			},
		},
	}

	err := client.DownloadToFile(context.Background(), "demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected write error")
	}
	if !strings.Contains(err.Error(), "stream corrupted") {
		t.Fatalf("cleanup should not mask primary error, got %v", err)
	}
}
