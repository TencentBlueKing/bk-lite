package main

import (
	"fmt"
	"os"
	"time"
)

// Windows 实时防护（如 Defender）在新文件批量落盘后会短暂持有句柄或直接拒绝
// 目录重命名，表现为 ACCESS_DENIED / SHARING_VIOLATION 的瞬态失败，数秒内自行
// 消失。事务路径上的 rename 统一走短退避重试，避免整单安装因扫描窗口失败。
var (
	transientRenameErrorCheck  = isTransientRenameError
	windowsRenameRetryAttempts = 10
	windowsRenameRetryDelay    = 500 * time.Millisecond
)

func renameWithWindowsTransientRetry(source, target string) error {
	var lastErr error
	for attempt := 0; attempt < windowsRenameRetryAttempts; attempt++ {
		if attempt > 0 {
			time.Sleep(windowsRenameRetryDelay)
		}
		lastErr = os.Rename(source, target)
		if lastErr == nil {
			if attempt > 0 {
				log("rename %s -> %s succeeded after %d transient failures", source, target, attempt)
			}
			return nil
		}
		if !transientRenameErrorCheck(lastErr) {
			return lastErr
		}
		log("transient rename failure (attempt %d/%d): %v", attempt+1, windowsRenameRetryAttempts, lastErr)
	}
	return fmt.Errorf(
		"%w (still failing after %d attempts over %s; source exists: %t; target exists: %t%s)",
		lastErr,
		windowsRenameRetryAttempts,
		time.Duration(windowsRenameRetryAttempts-1)*windowsRenameRetryDelay,
		pathExists(source),
		pathExists(target),
		renameFailureProcessHints(source, target),
	)
}

func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
