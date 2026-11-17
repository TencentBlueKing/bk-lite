package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	windowsProgramsInstallDir    = `C:\fusion-collectors`
	windowsUninstallExeName      = "uninstall.exe"
	windowsOriginalUninstallName = "original-uninstall.exe"
	windowsInstallerIconName     = "installer.ico"
	windowsSidecarServiceName    = "sidecar"
	windowsUninstallConfirmedArg = "--bklite-uninstall-confirmed"
	windowsUninstallRegistryKey  = `Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar`
	windowsProductRegistryKey    = `Software\FusionCollectors\Sidecar`

	// KEY_WOW64_32KEY。NSIS 是 32 位且没有 SetRegView，远程安装必须写进同一条 32 位卸载记录。
	windowsRegistry32BitView uint32 = 0x200

	windowsInstallCompleteMessage     = "Installation complete"
	windowsInstallUnregisteredMessage = "安装完成，但未登记到程序和功能"
	uninstallConfirmMessage           = "确定要卸载 Collector Sidecar 吗？"
	uninstallSuccessMessage           = "Collector Sidecar 已卸载。"
)

const (
	registryValueString = "string"
	registryValueDWord  = "dword"
	registryValueDelete = "delete"
)

var (
	errProgramsDirNotCanonical   = errors.New(`install directory is not C:\fusion-collectors`)
	errUninstallInstallArguments = errors.New("卸载程序不接受安装参数")
	errUninstallInProgress       = errors.New("正在安装，请稍后再试")
	errUninstallScope            = errors.New("无法确认卸载范围，已中止")
	errUninstallService          = errors.New("停止或删除 sidecar 服务失败")
	errUninstallFiles            = errors.New("删除安装文件失败")
	errUninstallRegistry         = errors.New("清理程序和功能记录失败，请重试")
	errUninstallElevation        = errors.New("未能获得管理员权限，卸载已取消。")
	errUninstallLaunch           = errors.New("未能启动卸载程序。")
	errOriginalUninstallerMove   = errors.New("could not move the running uninstaller")
)

type registryValueOp struct {
	Name   string
	Kind   string
	String string
	DWord  uint32
}

type windowsProgramRegistry interface {
	Apply(ops []registryValueOp) error
	Delete() error
}

// windowsProgramsEnv 把注册表、服务、提权和界面隔离开，便于在非 Windows 上测试编排。
type windowsProgramsEnv struct {
	Executable              func() (string, error)
	CopyUninstaller         func(sourcePath, installDir string) error
	IconExists              func(installDir string) (bool, error)
	Registry                windowsProgramRegistry
	IsElevated              func() bool
	Confirm                 func() (bool, error)
	Notify                  func(success bool, message string) error
	AcquireLock             func(installDir string) (func(), error)
	StopAndDeleteService    func() error
	ListRetainedBackups     func() ([]string, error)
	RemovePath              func(path string) error
	StageUninstaller        func(sourcePath string) (string, error)
	Launch                  func(path string, args []string, verb string, wait bool) (int, error)
	MoveOriginalUninstaller func(stagingDir string) (string, error)
	ScheduleDelete          func(path string) error
	Stderr                  io.Writer
}

type windowsUninstallPlan struct {
	Paths    []string
	LockPath string
	Retained []string
}

func isUninstallExecutable(path string) bool {
	return strings.EqualFold(executableBaseName(path), windowsUninstallExeName)
}

func executableBaseName(path string) string {
	path = strings.TrimSpace(path)
	path = strings.ReplaceAll(path, "/", `\`)
	if index := strings.LastIndex(path, `\`); index >= 0 {
		return path[index+1:]
	}
	return path
}

func windowsPathDir(path string) string {
	normalized := normalizeWindowsPath(path)
	index := strings.LastIndex(normalized, `\`)
	if index <= 0 {
		return ""
	}
	return normalized[:index]
}

func isCanonicalWindowsProgramsDir(path string) bool {
	return strings.EqualFold(normalizeWindowsPath(path), windowsProgramsInstallDir)
}

func normalizeWindowsPath(path string) string {
	path = strings.TrimSpace(path)
	if path == "" {
		return ""
	}
	path = strings.ReplaceAll(path, "/", `\`)
	if strings.HasPrefix(path, `\\`) {
		parts := cleanWindowsParts(strings.TrimPrefix(path, `\\`))
		if len(parts) == 0 {
			return `\\`
		}
		return `\\` + strings.Join(parts, `\`)
	}
	if len(path) >= 2 && path[1] == ':' {
		volume := path[:2]
		rest := path[2:]
		// C:foo 是相对当前目录的路径，不能当成 C:\foo。
		if rest == "" || !strings.HasPrefix(rest, `\`) {
			return volume + rest
		}
		parts := cleanWindowsParts(rest)
		if len(parts) == 0 {
			return volume + `\`
		}
		return volume + `\` + strings.Join(parts, `\`)
	}
	return strings.Join(cleanWindowsParts(path), `\`)
}

func cleanWindowsParts(path string) []string {
	var parts []string
	for _, part := range strings.Split(path, `\`) {
		switch part {
		case "", ".":
			continue
		case "..":
			if len(parts) > 0 {
				parts = parts[:len(parts)-1]
			}
		default:
			parts = append(parts, part)
		}
	}
	return parts
}

func programRegistryOps(version string, iconExists bool) []registryValueOp {
	version = strings.TrimSpace(version)
	ops := []registryValueOp{
		{Name: "DisplayName", Kind: registryValueString, String: "Collector Sidecar"},
		{Name: "Publisher", Kind: registryValueString, String: "BK-Lite"},
	}
	if version == "" {
		ops = append(ops, registryValueOp{Name: "DisplayVersion", Kind: registryValueDelete})
	} else {
		ops = append(ops, registryValueOp{Name: "DisplayVersion", Kind: registryValueString, String: version})
	}
	ops = append(ops,
		registryValueOp{Name: "InstallLocation", Kind: registryValueString, String: windowsProgramsInstallDir},
		registryValueOp{Name: "UninstallString", Kind: registryValueString, String: `"` + windowsProgramsInstallDir + `\uninstall.exe"`},
		registryValueOp{Name: "QuietUninstallString", Kind: registryValueString, String: `"` + windowsProgramsInstallDir + `\uninstall.exe" /S`},
		registryValueOp{Name: "NoModify", Kind: registryValueDWord, DWord: 1},
		registryValueOp{Name: "NoRepair", Kind: registryValueDWord, DWord: 1},
	)
	if iconExists {
		ops = append(ops, registryValueOp{Name: "DisplayIcon", Kind: registryValueString, String: windowsProgramsInstallDir + `\installer.ico`})
	} else {
		ops = append(ops, registryValueOp{Name: "DisplayIcon", Kind: registryValueDelete})
	}
	return ops
}

func windowsRemoteInstallCompleteMessage(cfg *Config, env *windowsProgramsEnv, warn func(string)) string {
	if cfg == nil || strings.TrimSpace(cfg.RemoteExecutionID) == "" {
		return windowsInstallCompleteMessage
	}
	if env == nil {
		env = newWindowsProgramsEnv()
	}
	if err := registerRemoteWindowsPrograms(cfg, env); err != nil {
		if warn != nil {
			warn(programsRegistrationWarning(err))
		}
		return windowsInstallUnregisteredMessage
	}
	return windowsInstallCompleteMessage
}

func registerRemoteWindowsPrograms(cfg *Config, env *windowsProgramsEnv) error {
	if cfg == nil || strings.TrimSpace(cfg.RemoteExecutionID) == "" {
		return nil
	}
	if env == nil {
		env = newWindowsProgramsEnv()
	}
	if !isCanonicalWindowsProgramsDir(cfg.InstallDir) {
		return errProgramsDirNotCanonical
	}
	source, err := env.Executable()
	if err != nil {
		return fmt.Errorf("locate installer executable: %w", err)
	}
	// 先覆盖 uninstall.exe。复制失败时不写注册表，已有的 NSIS 卸载项仍指向原来的文件。
	if err := env.CopyUninstaller(source, cfg.InstallDir); err != nil {
		return fmt.Errorf("install uninstall.exe: %w", err)
	}
	iconExists, err := env.IconExists(cfg.InstallDir)
	if err != nil {
		return fmt.Errorf("check installer icon: %w", err)
	}
	if err := env.Registry.Apply(programRegistryOps(cfg.Package.Version, iconExists)); err != nil {
		return fmt.Errorf("write Programs and Features registration: %w", err)
	}
	return nil
}

func programsRegistrationWarning(err error) string {
	const generic = "Programs and Features registration failed"
	if err == nil || registrationDetailLeaks(err.Error()) {
		return generic
	}
	return generic + ": " + err.Error()
}

func registrationDetailLeaks(detail string) bool {
	lower := strings.ToLower(detail)
	if strings.Contains(detail, "://") {
		return true
	}
	for _, marker := range []string{"token", "password", "secret", "credential"} {
		if strings.Contains(lower, marker) {
			return true
		}
	}
	return false
}

func runWindowsUninstallMode(argv []string) int {
	return runWindowsUninstall(argv, nil)
}

func runWindowsUninstall(argv []string, env *windowsProgramsEnv) int {
	if len(argv) == 0 || !isUninstallExecutable(argv[0]) {
		return 1
	}
	if env == nil {
		env = newWindowsProgramsEnv()
	}
	silent, confirmed, err := parseWindowsUninstallArgs(argv[1:])
	if err != nil {
		env.writeError(errUninstallInstallArguments.Error())
		return 1
	}
	if !confirmed {
		return launchWindowsUninstallPhase(env, silent)
	}
	// 确认标记只对临时副本有效。安装目录里的 uninstall.exe 带上它不能跳过确认。
	if !runningFromUninstallStaging(env) {
		env.writeError(errUninstallInstallArguments.Error())
		return 1
	}
	if !env.isElevated() {
		return finishUninstallPhase(env, silent, errUninstallElevation)
	}
	// 本地卸载不访问网络，也不通知节点管理。
	movedOriginal, uninstallErr := executeWindowsUninstall(env)
	scheduleRunningUninstallerRemoval(env, movedOriginal)
	return finishUninstallPhase(env, silent, uninstallErr)
}

func runningFromUninstallStaging(env *windowsProgramsEnv) bool {
	if env == nil || env.Executable == nil {
		return false
	}
	self, err := env.Executable()
	if err != nil {
		return false
	}
	return isUninstallStagingDirectory(windowsPathDir(self))
}

func parseWindowsUninstallArgs(args []string) (silent bool, confirmed bool, err error) {
	for _, arg := range args {
		switch {
		case strings.EqualFold(arg, "/S"):
			silent = true
		case arg == windowsUninstallConfirmedArg:
			confirmed = true
		default:
			return false, false, errUninstallInstallArguments
		}
	}
	return silent, confirmed, nil
}

func launchWindowsUninstallPhase(env *windowsProgramsEnv, silent bool) int {
	if silent && !env.isElevated() {
		env.writeError(errUninstallElevation.Error())
		return 1
	}
	if !silent {
		if env.Confirm == nil {
			env.writeError(errUninstallLaunch.Error())
			return 1
		}
		accepted, err := env.Confirm()
		if err != nil {
			env.writeError(errUninstallLaunch.Error())
			return 1
		}
		if !accepted {
			return 0
		}
	}
	if env.Executable == nil || env.StageUninstaller == nil || env.Launch == nil {
		return failUninstallLaunch(env, silent, "open")
	}
	source, err := env.Executable()
	if err != nil {
		return failUninstallLaunch(env, silent, "open")
	}
	dest, err := env.StageUninstaller(source)
	if err != nil || !isUninstallExecutable(dest) {
		// 副本必须仍叫 uninstall.exe，否则子进程会进入安装流程。
		removeUninstallStaging(dest)
		return failUninstallLaunch(env, silent, "open")
	}
	verb := "open"
	args := []string{windowsUninstallConfirmedArg}
	wait := false
	if silent {
		args = []string{"/S", windowsUninstallConfirmedArg}
		wait = true
	} else if !env.isElevated() {
		verb = "runas"
	}
	exitCode, launchErr := env.Launch(dest, args, verb, wait)
	if launchErr != nil {
		// 子进程没有启动，临时副本可以马上删掉。
		removeUninstallStaging(dest)
		return failUninstallLaunch(env, silent, verb)
	}
	return exitCode
}

func failUninstallLaunch(env *windowsProgramsEnv, silent bool, verb string) int {
	message := errUninstallLaunch.Error()
	if verb == "runas" {
		message = errUninstallElevation.Error()
	}
	if silent || env.Notify == nil {
		env.writeError(message)
		return 1
	}
	if err := env.Notify(false, message); err != nil {
		env.writeError(message)
	}
	return 1
}

func finishUninstallPhase(env *windowsProgramsEnv, silent bool, err error) int {
	if err == nil {
		if !silent && env.Notify != nil {
			_ = env.Notify(true, uninstallSuccessMessage)
		}
		return 0
	}
	if silent || env.Notify == nil {
		env.writeError(err.Error())
		return 1
	}
	if notifyErr := env.Notify(false, err.Error()); notifyErr != nil {
		env.writeError(err.Error())
	}
	return 1
}

func (env *windowsProgramsEnv) isElevated() bool {
	return env != nil && env.IsElevated != nil && env.IsElevated()
}

func (env *windowsProgramsEnv) writeError(message string) {
	if env == nil || strings.TrimSpace(message) == "" {
		return
	}
	writer := env.Stderr
	if writer == nil {
		writer = os.Stderr
	}
	fmt.Fprintf(writer, "ERROR: %s\n", message)
}

func executeWindowsUninstall(env *windowsProgramsEnv) (string, error) {
	release, err := env.AcquireLock(windowsProgramsInstallDir)
	if err != nil {
		return "", errUninstallInProgress
	}
	locked := true
	defer func() {
		if locked {
			release()
			locked = false
		}
	}()

	retained, err := env.ListRetainedBackups()
	if err != nil {
		return "", errUninstallScope
	}
	plan, err := planWindowsLocalUninstall(retained)
	if err != nil {
		return "", errUninstallScope
	}
	if err := env.StopAndDeleteService(); err != nil {
		return "", errUninstallService
	}
	// 父进程在静默模式下一直映射着安装目录里的 uninstall.exe。NTFS 允许改名正在运行的映像，不允许删除。
	// 改名失败（临时目录不在同一卷）时不报错，后面的删除仍按原有重试处理占用。
	movedOriginal := relocateOriginalUninstaller(env)
	for _, path := range plan.filePaths() {
		if !uninstallPathAllowed(path) {
			return movedOriginal, errUninstallScope
		}
		if err := env.RemovePath(path); err != nil {
			return movedOriginal, errUninstallFiles
		}
	}
	release()
	locked = false
	if !uninstallPathAllowed(plan.LockPath) {
		return movedOriginal, errUninstallScope
	}
	// 锁文件在持有期间删不掉，所以放到释放之后。
	if err := env.RemovePath(plan.LockPath); err != nil {
		return movedOriginal, errUninstallFiles
	}
	// 前面任何一步失败都留着程序记录，用户可以从「程序和功能」重试。
	if err := env.Registry.Delete(); err != nil {
		return movedOriginal, errUninstallRegistry
	}
	return movedOriginal, nil
}

func relocateOriginalUninstaller(env *windowsProgramsEnv) string {
	if env == nil || env.MoveOriginalUninstaller == nil || env.Executable == nil {
		return ""
	}
	self, err := env.Executable()
	if err != nil {
		return ""
	}
	stagingDir := windowsPathDir(self)
	if !isUninstallStagingDirectory(stagingDir) {
		return ""
	}
	dest, err := env.MoveOriginalUninstaller(stagingDir)
	if err != nil {
		return ""
	}
	accepted, ok := acceptedMovedUninstaller(dest, stagingDir)
	if !ok {
		return ""
	}
	return accepted
}

func (plan windowsUninstallPlan) filePaths() []string {
	paths := make([]string, 0, len(plan.Paths)+len(plan.Retained))
	paths = append(paths, plan.Paths...)
	paths = append(paths, plan.Retained...)
	return paths
}

// 与服务端 Windows 远程卸载的固定路径一致。retained 只接受备份目录本身，不接受其子路径。
func planWindowsLocalUninstall(retainedCandidates []string) (windowsUninstallPlan, error) {
	plan := windowsUninstallPlan{
		Paths: []string{
			`C:\fusion-collectors`,
			`C:\fusion-collectors.bklite-staging`,
			`C:\fusion-collectors.bklite-backup`,
			`C:\fusion-collectors.bklite-install.fence`,
		},
		LockPath: `C:\fusion-collectors.bklite-install.lock`,
	}
	seen := map[string]struct{}{}
	for _, candidate := range retainedCandidates {
		normalized := normalizeWindowsPath(candidate)
		if !isWindowsRetainedBackupDir(normalized) {
			return windowsUninstallPlan{}, errUninstallScope
		}
		key := strings.ToLower(normalized)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		plan.Retained = append(plan.Retained, normalized)
	}
	return plan, nil
}

func uninstallPathAllowed(path string) bool {
	normalized := normalizeWindowsPath(path)
	switch strings.ToLower(normalized) {
	case strings.ToLower(`C:\fusion-collectors`),
		strings.ToLower(`C:\fusion-collectors.bklite-staging`),
		strings.ToLower(`C:\fusion-collectors.bklite-backup`),
		strings.ToLower(`C:\fusion-collectors.bklite-install.fence`),
		strings.ToLower(`C:\fusion-collectors.bklite-install.lock`):
		return true
	default:
		return isWindowsRetainedBackupDir(normalized)
	}
}

func isWindowsRetainedBackupDir(path string) bool {
	normalized := normalizeWindowsPath(path)
	const prefix = `C:\fusion-collectors.bklite-backup-retained-`
	if len(normalized) < len(prefix) || !strings.EqualFold(normalized[:len(prefix)], prefix) {
		return false
	}
	rest := normalized[len(prefix):]
	return !strings.ContainsAny(rest, `/\`)
}

func scheduleRunningUninstallerRemoval(env *windowsProgramsEnv, movedOriginal string) {
	if env == nil || env.ScheduleDelete == nil || env.Executable == nil {
		return
	}
	self, err := env.Executable()
	if err != nil {
		return
	}
	dir := windowsPathDir(self)
	if !isUninstallStagingDirectory(dir) {
		return
	}
	// 重启删除按登记顺序执行。被移走的原文件和正在运行的副本必须先于目录，目录才能是空的。
	if accepted, ok := acceptedMovedUninstaller(movedOriginal, dir); ok {
		_ = env.ScheduleDelete(accepted)
	}
	_ = env.ScheduleDelete(self)
	_ = env.ScheduleDelete(dir)
}

func acceptedMovedUninstaller(path, stagingDir string) (string, bool) {
	path = normalizeWindowsPath(path)
	stagingDir = normalizeWindowsPath(stagingDir)
	if path == "" || !isUninstallStagingDirectory(stagingDir) {
		return "", false
	}
	if !strings.EqualFold(windowsPathDir(path), stagingDir) {
		return "", false
	}
	if !strings.EqualFold(executableBaseName(path), windowsOriginalUninstallName) {
		return "", false
	}
	return path, true
}

func originalUninstallerDestination(stagingDir string) (string, error) {
	stagingDir = normalizeWindowsPath(stagingDir)
	dest := stagingDir + `\` + windowsOriginalUninstallName
	accepted, ok := acceptedMovedUninstaller(dest, stagingDir)
	if !ok {
		return "", errOriginalUninstallerMove
	}
	return accepted, nil
}

func moveOriginalUninstaller(stagingDir string) (string, error) {
	self, err := os.Executable()
	if err != nil {
		return "", err
	}
	currentStaging := windowsPathDir(self)
	if !strings.EqualFold(normalizeWindowsPath(stagingDir), currentStaging) {
		return "", errOriginalUninstallerMove
	}
	dest, err := originalUninstallerDestination(currentStaging)
	if err != nil {
		return "", err
	}
	source := windowsProgramsInstallDir + `\` + windowsUninstallExeName
	if err := os.Rename(source, dest); err != nil {
		return "", err
	}
	return dest, nil
}

func isUninstallStagingDirectory(path string) bool {
	return strings.HasPrefix(strings.ToLower(executableBaseName(path)), "bklite-uninstall-")
}

func removeUninstallStaging(exePath string) {
	dir := stagingDirectory(exePath)
	if !isUninstallStagingDirectory(dir) {
		return
	}
	_ = os.RemoveAll(dir)
}

func stagingDirectory(path string) string {
	if strings.Contains(path, `\`) {
		return windowsPathDir(path)
	}
	return filepath.Dir(path)
}

func copyExecutableAsUninstaller(sourcePath, installDir string) error {
	source, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer source.Close()

	temporary, err := os.CreateTemp(installDir, ".uninstall-*.tmp")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	completed := false
	defer func() {
		if !completed {
			_ = os.Remove(temporaryPath)
		}
	}()
	if _, err := io.Copy(temporary, source); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Chmod(0o755); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := replaceFileAtomically(temporaryPath, filepath.Join(installDir, windowsUninstallExeName)); err != nil {
		return err
	}
	completed = true
	return nil
}

func installerIconExists(installDir string) (bool, error) {
	info, err := os.Stat(filepath.Join(installDir, windowsInstallerIconName))
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, err
	}
	return !info.IsDir(), nil
}

func stageWindowsUninstallCopy(tempRoot, sourcePath string) (string, error) {
	if strings.TrimSpace(tempRoot) == "" {
		return "", errors.New("temp directory is unavailable")
	}
	stagingDir, err := os.MkdirTemp(tempRoot, "bklite-uninstall-")
	if err != nil {
		return "", err
	}
	dest := filepath.Join(stagingDir, windowsUninstallExeName)
	if err := copyFileContents(sourcePath, dest); err != nil {
		_ = os.RemoveAll(stagingDir)
		return "", err
	}
	return dest, nil
}

func copyFileContents(sourcePath, destPath string) error {
	source, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer source.Close()

	dest, err := os.OpenFile(destPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o755)
	if err != nil {
		return err
	}
	if _, err := io.Copy(dest, source); err != nil {
		_ = dest.Close()
		return err
	}
	if err := dest.Sync(); err != nil {
		_ = dest.Close()
		return err
	}
	return dest.Close()
}

func removeOwnedWindowsPath(path string) error {
	attempts := 1
	var delay time.Duration
	if strings.EqualFold(normalizeWindowsPath(path), windowsProgramsInstallDir) {
		// 改名失败时，安装目录里的 uninstall.exe 可能仍被父进程占用。
		attempts = 25
		delay = 200 * time.Millisecond
	}
	var last error
	for attempt := 0; attempt < attempts; attempt++ {
		last = os.RemoveAll(path)
		if last == nil {
			return nil
		}
		if attempt+1 < attempts {
			time.Sleep(delay)
		}
	}
	return last
}
