package utils

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"nats-executor/utils/downloaderr"

	"github.com/nats-io/nats.go"
)

type stubDownloader struct {
	download func(ctx context.Context, fileKey, targetPath, fileName string) error
}

func (s stubDownloader) DownloadToFile(ctx context.Context, fileKey, targetPath, fileName string) error {
	if s.download == nil {
		return nil
	}
	return s.download(ctx, fileKey, targetPath, fileName)
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

func TestDownloadFileRejectsUnsafeFileName(t *testing.T) {
	tests := []string{"../evil.txt", "/tmp/evil.txt", "nested/evil.txt", `..\evil.txt`}

	for _, fileName := range tests {
		t.Run(fileName, func(t *testing.T) {
			called := false
			withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
				called = true
				return stubDownloader{}, nil
			})

			err := DownloadFile(DownloadFileRequest{
				BucketName:     "bucket",
				FileKey:        "key",
				FileName:       fileName,
				TargetPath:     "/tmp",
				ExecuteTimeout: 1,
			}, nil)
			if err == nil {
				t.Fatal("expected unsafe file_name to be rejected")
			}
			if !strings.Contains(err.Error(), "file_name must not contain path separators or be absolute") {
				t.Fatalf("unexpected error: %v", err)
			}
			if called {
				t.Fatal("downloader should not be constructed for unsafe file names")
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

func TestDownloadFilePropagatesDependencyError(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
			if bucketName != "bucket" || fileKey != "key" || targetPath != "/tmp" || fileName != "file.txt" {
				t.Fatalf("unexpected download args: bucket=%s key=%s target=%s file=%s", bucketName, fileKey, targetPath, fileName)
			}
			return downloaderr.New(downloaderr.KindDependency, errors.New("download failed"))
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

	if !strings.Contains(err.Error(), "failed to download file") || !strings.Contains(err.Error(), "download failed") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindDependency {
		t.Fatalf("expected dependency error kind, got %s", downloaderr.KindOf(err))
	}
}

func TestDownloadFileTimesOutWhenDownloaderObservesContext(t *testing.T) {
	var observedContextDone atomic.Bool
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
			<-ctx.Done()
			observedContextDone.Store(true)
			return downloaderr.New(downloaderr.KindTimeout, ctx.Err())
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
	if downloaderr.KindOf(err) != downloaderr.KindTimeout {
		t.Fatalf("expected timeout error kind, got %s", downloaderr.KindOf(err))
	}
	if elapsed > 1200*time.Millisecond {
		t.Fatalf("timeout should return promptly, took %v", elapsed)
	}
	if !observedContextDone.Load() {
		t.Fatal("expected downloader to observe context cancellation")
	}
}

func TestDownloadFilePropagatesIOErrorKind(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
			return downloaderr.New(downloaderr.KindIO, errors.New("rename failed"))
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
		t.Fatal("expected io error")
	}
	if !strings.Contains(err.Error(), "failed to finalize downloaded file") {
		t.Fatalf("unexpected error: %v", err)
	}
	if downloaderr.KindOf(err) != downloaderr.KindIO {
		t.Fatalf("expected io error kind, got %s", downloaderr.KindOf(err))
	}
}

func TestDownloadFilePropagatesCanceledErrorKind(t *testing.T) {
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
			return downloaderr.New(downloaderr.KindCanceled, context.Canceled)
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
		t.Fatal("expected canceled error")
	}
	if downloaderr.KindOf(err) != downloaderr.KindCanceled {
		t.Fatalf("expected canceled error kind, got %s", downloaderr.KindOf(err))
	}
	if !strings.Contains(err.Error(), "download operation canceled") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDownloadFileMapsPlainCanceledAndTimeoutErrors(t *testing.T) {
	testCases := []struct {
		name     string
		err      error
		wantKind downloaderr.Kind
		wantText string
	}{
		{name: "timeout", err: context.DeadlineExceeded, wantKind: downloaderr.KindTimeout, wantText: "download operation timed out"},
		{name: "canceled", err: context.Canceled, wantKind: downloaderr.KindCanceled, wantText: "download operation canceled"},
	}

	for _, tt := range testCases {
		t.Run(tt.name, func(t *testing.T) {
			withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
				return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
					return tt.err
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
				t.Fatal("expected mapped error")
			}
			if downloaderr.KindOf(err) != tt.wantKind {
				t.Fatalf("expected %s, got %s", tt.wantKind, downloaderr.KindOf(err))
			}
			if !strings.Contains(err.Error(), tt.wantText) {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

func TestDownloadFileSuccessAndUnknownErrorFallback(t *testing.T) {
	t.Run("success path", func(t *testing.T) {
		called := false
		withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
			return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
				called = true
				return nil
			}}, nil
		})

		if err := DownloadFile(DownloadFileRequest{
			BucketName:     "bucket",
			FileKey:        "key",
			FileName:       "file.txt",
			TargetPath:     "/tmp",
			ExecuteTimeout: 1,
		}, nil); err != nil {
			t.Fatalf("expected no error, got %v", err)
		}
		if !called {
			t.Fatal("expected downloader to be called")
		}
	})

	t.Run("plain error falls back to dependency kind", func(t *testing.T) {
		withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
			return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
				return errors.New("plain failure")
			}}, nil
		})

		err := DownloadFile(DownloadFileRequest{
			BucketName:     "bucket",
			FileKey:        "key",
			FileName:       "file.txt",
			TargetPath:     "/tmp",
			ExecuteTimeout: 1,
		}, nil)
		if err == nil || downloaderr.KindOf(err) != downloaderr.KindDependency || !strings.Contains(err.Error(), "failed to download file") {
			t.Fatalf("unexpected error: %v", err)
		}
	})
}

func TestDownloadFileSucceeds(t *testing.T) {
	called := false
	withStubDownloader(t, func(nc *nats.Conn, bucketName string) (fileDownloader, error) {
		if bucketName != "bucket" {
			t.Fatalf("unexpected bucket name: %s", bucketName)
		}
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
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
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
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
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
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
		return stubDownloader{download: func(ctx context.Context, fileKey, targetPath, fileName string) error {
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
