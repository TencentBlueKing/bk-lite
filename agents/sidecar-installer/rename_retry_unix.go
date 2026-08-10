//go:build !windows

package main

// 非 Windows 平台没有实时防护扫描窗口这类瞬态 rename 失败，一次失败即为终态。
func isTransientRenameError(error) bool {
	return false
}

func renameFailureProcessHints(...string) string {
	return ""
}
