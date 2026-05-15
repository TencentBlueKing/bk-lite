package utils

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

var (
	openZipArchive = zip.OpenReader
	makeDirAll     = os.MkdirAll
	statPath       = os.Stat
	removePath     = os.RemoveAll
	openZipEntry   = func(f *zip.File) (io.ReadCloser, error) { return f.Open() }
	openDestFile   = func(path string, mode os.FileMode) (*os.File, error) {
		return os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, mode)
	}
	copyToDest = io.Copy
)

type UnzipRequest struct {
	ZipPath string `json:"zip_path"`
	DestDir string `json:"dest_dir"`
}

// UnzipToDir 解压 .zip 文件到指定目录，返回父目录名称
func UnzipToDir(req UnzipRequest) (string, error) {
	if strings.TrimSpace(req.DestDir) == "" {
		return "", fmt.Errorf("destination directory is required")
	}

	reader, err := openZipArchive(req.ZipPath)
	if err != nil {
		return "", fmt.Errorf("failed to open zip file: %w", err)
	}
	defer reader.Close()

	if len(reader.File) == 0 {
		return "", fmt.Errorf("zip file is empty")
	}

	// 获取父目录名称
	firstFile := reader.File[0]
	parts := strings.SplitN(firstFile.Name, string(os.PathSeparator), 2)
	if len(parts) == 0 {
		return "", fmt.Errorf("failed to determine parent directory")
	}
	parentDir := parts[0]

	for _, f := range reader.File {
		if filepath.IsAbs(f.Name) {
			return "", fmt.Errorf("illegal file path: %s", f.Name)
		}

		fpath := filepath.Join(req.DestDir, f.Name)

		// 防止 ZipSlip 漏洞
		if !strings.HasPrefix(fpath, filepath.Clean(req.DestDir)+string(os.PathSeparator)) {
			return "", fmt.Errorf("illegal file path: %s", fpath)
		}

		if f.Mode()&os.ModeType != 0 && !f.FileInfo().IsDir() {
			return "", fmt.Errorf("unsupported file type in zip: %s", f.Name)
		}

		if f.FileInfo().IsDir() {
			// 创建目录
			if err := makeDirAll(fpath, 0755); err != nil {
				return "", fmt.Errorf("failed to create directory: %w", err)
			}
			continue
		}

		// 创建父目录
		if err := makeDirAll(filepath.Dir(fpath), 0755); err != nil {
			return "", fmt.Errorf("failed to create parent directory: %w", err)
		}

		// 检查目标路径是否已存在目录，如果是则删除
		if info, err := statPath(fpath); err == nil && info.IsDir() {
			if err := removePath(fpath); err != nil {
				return "", fmt.Errorf("failed to remove existing directory: %w", err)
			}
		}

		if err := extractZipFile(f, fpath); err != nil {
			return "", err
		}
	}

	return parentDir, nil
}

func extractZipFile(f *zip.File, fpath string) error {
	inFile, err := openZipEntry(f)
	if err != nil {
		return fmt.Errorf("failed to open file in zip: %w", err)
	}
	defer inFile.Close()

	outFile, err := openDestFile(fpath, f.Mode())
	if err != nil {
		return fmt.Errorf("failed to create output file: %w", err)
	}
	defer outFile.Close()

	if _, err := copyToDest(outFile, inFile); err != nil {
		return fmt.Errorf("failed to write file: %w", err)
	}

	return nil
}
