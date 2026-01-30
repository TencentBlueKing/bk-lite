package utils

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

type UnzipRequest struct {
	ZipPath string `json:"zip_path"`
	DestDir string `json:"dest_dir"`
}

// UnzipToDir 解压 .zip 文件到指定目录，返回父目录名称
func UnzipToDir(req UnzipRequest) (string, error) {
	reader, err := zip.OpenReader(req.ZipPath)
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
		fpath := filepath.Join(req.DestDir, f.Name)

		// 防止 ZipSlip 漏洞
		if !strings.HasPrefix(fpath, filepath.Clean(req.DestDir)+string(os.PathSeparator)) {
			return "", fmt.Errorf("illegal file path: %s", fpath)
		}

		if f.FileInfo().IsDir() {
			// 创建目录
			if err := os.MkdirAll(fpath, 0755); err != nil {
				return "", fmt.Errorf("failed to create directory: %w", err)
			}
			continue
		}

		// 创建父目录
		if err := os.MkdirAll(filepath.Dir(fpath), 0755); err != nil {
			return "", fmt.Errorf("failed to create parent directory: %w", err)
		}

		// 检查目标路径是否已存在目录，如果是则删除
		if info, err := os.Stat(fpath); err == nil && info.IsDir() {
			if err := os.RemoveAll(fpath); err != nil {
				return "", fmt.Errorf("failed to remove existing directory: %w", err)
			}
		}

		// 解压文件
		inFile, err := f.Open()
		if err != nil {
			return "", fmt.Errorf("failed to open file in zip: %w", err)
		}
		defer inFile.Close()

		outFile, err := os.OpenFile(fpath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return "", fmt.Errorf("failed to create output file: %w", err)
		}
		defer outFile.Close()

		if _, err := io.Copy(outFile, inFile); err != nil {
			return "", fmt.Errorf("failed to write file: %w", err)
		}
	}

	return parentDir, nil
}
