package jetstream

import (
	"errors"
	"io"
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

func withDownloadFileCreator(tb testing.TB, fn func(string) (*os.File, error)) {
	tb.Helper()
	original := createDownloadFile
	createDownloadFile = fn
	tb.Cleanup(func() {
		createDownloadFile = original
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
	if err := client.DownloadToFile("demo-key", targetDir, "demo.txt"); err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	data, err := os.ReadFile(filepath.Join(targetDir, "demo.txt"))
	if err != nil {
		t.Fatalf("expected downloaded file: %v", err)
	}
	if string(data) != "hello world" {
		t.Fatalf("unexpected file contents: %q", string(data))
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

	err := client.DownloadToFile("demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected object store error")
	}
	if !strings.Contains(err.Error(), "failed to get object from store with key demo-key: bucket unavailable") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadToFilePropagatesCreateFileError(t *testing.T) {
	withDownloadFileCreator(t, func(name string) (*os.File, error) {
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

	err := client.DownloadToFile("demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected create file error")
	}
	if !strings.Contains(err.Error(), "failed to create file at") || !strings.Contains(err.Error(), "disk full") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadToFilePropagatesCopyError(t *testing.T) {
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

	err := client.DownloadToFile("demo-key", t.TempDir(), "demo.txt")
	if err == nil {
		t.Fatal("expected write error")
	}
	if !strings.Contains(err.Error(), "failed to write file: stream corrupted") {
		t.Fatalf("unexpected error: %v", err)
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
			err := client.DownloadToFile("demo-key", t.TempDir(), fileName)
			if err == nil {
				t.Fatal("expected unsafe file name to be rejected")
			}
			if !strings.Contains(err.Error(), "illegal file name") {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}
