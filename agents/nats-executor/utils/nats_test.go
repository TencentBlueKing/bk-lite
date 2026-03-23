package utils

import (
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
)

type stubDownloader struct {
	download func(fileKey, targetPath, fileName string) error
}

func (s stubDownloader) DownloadToFile(fileKey, targetPath, fileName string) error {
	if s.download == nil {
		return nil
	}
	return s.download(fileKey, targetPath, fileName)
}

func withStubDownloader(tb testing.TB, factory func(nc *nats.Conn, bucketName string) (fileDownloader, error)) {
	tb.Helper()
	original := newJetStreamClient
	newJetStreamClient = factory
	tb.Cleanup(func() {
		newJetStreamClient = original
	})
}

func TestDownloadFileRejectsInvalidTimeout(t *testing.T) {
	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 0,
	}, nil)

	if err == nil {
		t.Fatal("expected invalid timeout error")
	}

	if !strings.Contains(err.Error(), "execute timeout must be greater than 0") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadFileRejectsMissingRequiredFields(t *testing.T) {
	tests := []struct {
		name string
		req  DownloadFileRequest
	}{
		{name: "missing bucket", req: DownloadFileRequest{FileKey: "key", FileName: "file.txt", TargetPath: "/tmp", ExecuteTimeout: 1}},
		{name: "missing file key", req: DownloadFileRequest{BucketName: "bucket", FileName: "file.txt", TargetPath: "/tmp", ExecuteTimeout: 1}},
		{name: "missing file name", req: DownloadFileRequest{BucketName: "bucket", FileKey: "key", TargetPath: "/tmp", ExecuteTimeout: 1}},
		{name: "missing target path", req: DownloadFileRequest{BucketName: "bucket", FileKey: "key", FileName: "file.txt", ExecuteTimeout: 1}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			called := false
			withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
				called = true
				return stubDownloader{}, nil
			})

			err := DownloadFile(tt.req, nil)
			if err == nil {
				t.Fatal("expected validation error")
			}
			if !strings.Contains(err.Error(), "required") {
				t.Fatalf("unexpected error: %v", err)
			}
			if called {
				t.Fatal("downloader should not be constructed for invalid input")
			}
		})
	}
}

func TestDownloadFilePropagatesClientCreationError(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return nil, errors.New("boom")
	})

	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 1,
	}, nil)

	if err == nil {
		t.Fatal("expected client creation error")
	}

	if !strings.Contains(err.Error(), "failed to create JetStream client: boom") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadFilePropagatesDownloadError(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			if bucketName != "bucket" || fileKey != "key" || targetPath != "/tmp" || fileName != "file.txt" {
				t.Fatalf("unexpected download args: bucket=%s key=%s target=%s file=%s", bucketName, fileKey, targetPath, fileName)
			}
			return errors.New("download failed")
		}}, nil
	})

	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 1,
	}, nil)

	if err == nil {
		t.Fatal("expected download error")
	}

	if !strings.Contains(err.Error(), "failed to download file: download failed") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadFileTimesOutWhenDownloaderBlocks(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			time.Sleep(1500 * time.Millisecond)
			return nil
		}}, nil
	})

	start := time.Now()
	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 1,
	}, nil)
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("expected timeout error")
	}

	if !strings.Contains(err.Error(), "download operation timed out") {
		t.Fatalf("unexpected error: %v", err)
	}

	if elapsed > 1200*time.Millisecond {
		t.Fatalf("timeout should return promptly, took %v", elapsed)
	}
}

func TestDownloadFileSucceeds(t *testing.T) {
	called := false
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		if bucketName != "bucket" {
			t.Fatalf("unexpected bucket name: %s", bucketName)
		}
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			called = true
			if fileKey != "key" || targetPath != "/tmp" || fileName != "file.txt" {
				t.Fatalf("unexpected download args: key=%s target=%s file=%s", fileKey, targetPath, fileName)
			}
			return nil
		}}, nil
	})

	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 1,
	}, nil)

	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if !called {
		t.Fatal("expected downloader to be called")
	}
}

func TestDownloadFileSupportsConcurrentRequests(t *testing.T) {
	var clientCreations atomic.Int32
	var downloadCalls atomic.Int32
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		clientCreations.Add(1)
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			downloadCalls.Add(1)
			return nil
		}}, nil
	})

	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			err := DownloadFile(DownloadFileRequest{
				BucketName:     "bucket",
				FileKey:        "key",
				FileName:       "file.txt",
				TargetPath:     "/tmp",
				ExecuteTimeout: 1,
			}, nil)
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		}()
	}
	wg.Wait()

	if clientCreations.Load() != 8 {
		t.Fatalf("expected 8 client creations, got %d", clientCreations.Load())
	}
	if downloadCalls.Load() != 8 {
		t.Fatalf("expected 8 download calls, got %d", downloadCalls.Load())
	}
}

func TestDownloadFileSupportsLargeTimeoutWithoutWaiting(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			return nil
		}}, nil
	})

	start := time.Now()
	err := DownloadFile(DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 30,
	}, nil)
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if elapsed := time.Since(start); elapsed > 200*time.Millisecond {
		t.Fatalf("successful download should not wait on timeout duration, took %v", elapsed)
	}
}

func BenchmarkDownloadFile(b *testing.B) {
	withStubDownloader(b, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(fileKey, targetPath, fileName string) error {
			return nil
		}}, nil
	})

	req := DownloadFileRequest{
		BucketName:     "bucket",
		FileKey:        "key",
		FileName:       "file.txt",
		TargetPath:     "/tmp",
		ExecuteTimeout: 1,
	}

	b.ReportAllocs()
	for b.Loop() {
		if err := DownloadFile(req, nil); err != nil {
			b.Fatalf("unexpected download error: %v", err)
		}
	}
}
