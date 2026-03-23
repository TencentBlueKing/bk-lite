package utils

import (
	"archive/zip"
	"bytes"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func TestUnzipToDir(t *testing.T) {
	// 准备测试目录
	zipFilePath := filepath.Join(t.TempDir(), "test.zip")
	destDir := filepath.Join(t.TempDir(), "unzipped")

	// 创建一个临时 zip 文件用于测试
	f, err := os.Create(zipFilePath)
	if err != nil {
		t.Fatalf("failed to create test zip file: %v", err)
	}
	defer f.Close()

	// 创建 zip writer
	zipWriter := zip.NewWriter(f)

	// 添加一个文件
	w, err := zipWriter.Create("testdir/hello.txt")
	if err != nil {
		t.Fatalf("failed to create file in zip: %v", err)
	}
	_, err = w.Write([]byte("Hello, world!"))
	if err != nil {
		t.Fatalf("failed to write to file in zip: %v", err)
	}

	zipWriter.Close()

	// 解压
	req := UnzipRequest{
		ZipPath: zipFilePath,
		DestDir: destDir,
	}

	_, err = UnzipToDir(req)
	if err != nil {
		t.Fatalf("UnzipToDir failed: %v", err)
	}

	// 验证解压后的文件存在
	unzippedFile := filepath.Join(destDir, "testdir", "hello.txt")
	if _, err := os.Stat(unzippedFile); os.IsNotExist(err) {
		t.Fatalf("expected file not found after unzip: %s", unzippedFile)
	}
}

func TestUnzipToDirRejectsZipSlip(t *testing.T) {
	zipFilePath := filepath.Join(t.TempDir(), "slip.zip")
	createZipFile(t, zipFilePath, map[string]string{
		"../evil.txt": "pwned",
	})

	_, err := UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: filepath.Join(t.TempDir(), "dest")})
	if err == nil {
		t.Fatal("expected ZipSlip payload to be rejected")
	}

	if !strings.Contains(err.Error(), "illegal file path") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestUnzipToDirRejectsAbsolutePathEntries(t *testing.T) {
	zipFilePath := filepath.Join(t.TempDir(), "absolute.zip")
	createZipFile(t, zipFilePath, map[string]string{
		"/tmp/evil.txt": "pwned",
	})

	_, err := UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: filepath.Join(t.TempDir(), "dest")})
	if err == nil {
		t.Fatal("expected absolute path payload to be rejected")
	}

	if !strings.Contains(err.Error(), "illegal file path") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestUnzipToDirReplacesExistingDirectoryWithFile(t *testing.T) {
	baseDir := t.TempDir()
	zipFilePath := filepath.Join(baseDir, "replace.zip")
	destDir := filepath.Join(baseDir, "dest")
	targetPath := filepath.Join(destDir, "testdir", "hello.txt")

	if err := os.MkdirAll(targetPath, 0o755); err != nil {
		t.Fatalf("failed to create conflicting directory: %v", err)
	}

	createZipFile(t, zipFilePath, map[string]string{
		"testdir/hello.txt": "Hello, world!",
	})

	_, err := UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: destDir})
	if err != nil {
		t.Fatalf("UnzipToDir failed: %v", err)
	}

	data, err := os.ReadFile(targetPath)
	if err != nil {
		t.Fatalf("expected file at conflicting path: %v", err)
	}

	if string(data) != "Hello, world!" {
		t.Fatalf("unexpected file contents: %q", string(data))
	}
}

func TestUnzipToDirReturnsErrorForEmptyArchive(t *testing.T) {
	zipFilePath := filepath.Join(t.TempDir(), "empty.zip")
	file, err := os.Create(zipFilePath)
	if err != nil {
		t.Fatalf("failed to create zip file: %v", err)
	}

	writer := zip.NewWriter(file)
	if err := writer.Close(); err != nil {
		t.Fatalf("failed to close zip writer: %v", err)
	}
	if err := file.Close(); err != nil {
		t.Fatalf("failed to close zip file: %v", err)
	}

	_, err = UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: t.TempDir()})
	if err == nil {
		t.Fatal("expected empty zip archive to fail")
	}

	if !strings.Contains(err.Error(), "zip file is empty") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestUnzipToDirRejectsMissingDestination(t *testing.T) {
	zipFilePath := filepath.Join(t.TempDir(), "test.zip")
	createZipFile(t, zipFilePath, map[string]string{
		"testdir/hello.txt": "Hello, world!",
	})

	_, err := UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: ""})
	if err == nil {
		t.Fatal("expected missing destination to fail")
	}

	if !strings.Contains(err.Error(), "destination directory is required") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func BenchmarkUnzipToDir(b *testing.B) {
	tempDir := b.TempDir()
	zipFilePath := filepath.Join(tempDir, "benchmark.zip")
	createZipArchiveForBenchmark(b, zipFilePath, 32, 2048)

	b.ReportAllocs()
	for i := range b.N {
		destDir := filepath.Join(tempDir, "dest", strconv.Itoa(i))
		if _, err := UnzipToDir(UnzipRequest{ZipPath: zipFilePath, DestDir: destDir}); err != nil {
			b.Fatalf("unzip failed: %v", err)
		}
	}
}

func createZipFile(t testing.TB, zipFilePath string, files map[string]string) {
	t.Helper()

	f, err := os.Create(zipFilePath)
	if err != nil {
		t.Fatalf("failed to create zip file: %v", err)
	}
	defer f.Close()

	zipWriter := zip.NewWriter(f)
	for name, content := range files {
		w, err := zipWriter.Create(name)
		if err != nil {
			t.Fatalf("failed to create zip entry %s: %v", name, err)
		}
		if _, err := w.Write([]byte(content)); err != nil {
			t.Fatalf("failed to write zip entry %s: %v", name, err)
		}
	}

	if err := zipWriter.Close(); err != nil {
		t.Fatalf("failed to close zip writer: %v", err)
	}
}

func createZipArchiveForBenchmark(b testing.TB, zipFilePath string, fileCount, fileSize int) {
	b.Helper()

	f, err := os.Create(zipFilePath)
	if err != nil {
		b.Fatalf("failed to create zip file: %v", err)
	}
	defer f.Close()

	writer := zip.NewWriter(f)
	payload := bytes.Repeat([]byte("a"), fileSize)
	for i := range fileCount {
		entry, err := writer.Create(filepath.Join("root", "nested", strconv.Itoa(i%3), "file-"+strconv.Itoa(i)+".txt"))
		if err != nil {
			b.Fatalf("failed to create zip entry: %v", err)
		}
		if _, err := entry.Write(payload); err != nil {
			b.Fatalf("failed to write zip entry: %v", err)
		}
	}

	if err := writer.Close(); err != nil {
		b.Fatalf("failed to close zip writer: %v", err)
	}
}
