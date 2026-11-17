package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestRemoteRegistrationWritesProgramRecord(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.files[windowsProgramsInstallDir+`\uninstall.exe`] = []byte("old-nsis")
	fixture.files[windowsProgramsInstallDir+`\installer.ico`] = []byte("icon")
	fixture.registry.strings["DisplayVersion"] = "1.0.0"
	fixture.registry.productKeyPresent = true
	cfg := remoteProgramsConfig("3.2.1")

	var warnings []string
	message := windowsRemoteInstallCompleteMessage(cfg, fixture.env, func(warning string) {
		warnings = append(warnings, warning)
	})

	if message != windowsInstallCompleteMessage || len(warnings) != 0 {
		t.Fatalf("message=%q warnings=%v", message, warnings)
	}
	if !reflect.DeepEqual(fixture.events, []string{"copy", "registry"}) {
		t.Fatalf("events = %#v", fixture.events)
	}
	if got := fixture.files[windowsProgramsInstallDir+`\uninstall.exe`]; string(got) != "bootstrap-bytes" {
		t.Fatalf("uninstall.exe = %q", got)
	}
	want := []registryValueOp{
		{Name: "DisplayName", Kind: registryValueString, String: "Collector Sidecar"},
		{Name: "Publisher", Kind: registryValueString, String: "BK-Lite"},
		{Name: "DisplayVersion", Kind: registryValueString, String: "3.2.1"},
		{Name: "InstallLocation", Kind: registryValueString, String: `C:\fusion-collectors`},
		{Name: "UninstallString", Kind: registryValueString, String: `"C:\fusion-collectors\uninstall.exe"`},
		{Name: "QuietUninstallString", Kind: registryValueString, String: `"C:\fusion-collectors\uninstall.exe" /S`},
		{Name: "NoModify", Kind: registryValueDWord, DWord: 1},
		{Name: "NoRepair", Kind: registryValueDWord, DWord: 1},
		{Name: "DisplayIcon", Kind: registryValueString, String: `C:\fusion-collectors\installer.ico`},
	}
	if !reflect.DeepEqual(fixture.registry.ops, want) {
		t.Fatalf("registry ops = %#v", fixture.registry.ops)
	}
	if strings.Contains(fixture.registry.strings["UninstallString"], "/S") {
		t.Fatalf("interactive UninstallString must not contain /S: %s", fixture.registry.strings["UninstallString"])
	}
	if !strings.HasSuffix(fixture.registry.strings["QuietUninstallString"], " /S") {
		t.Fatalf("QuietUninstallString = %s", fixture.registry.strings["QuietUninstallString"])
	}
	if fixture.registry.productKeyPresent != true || fixture.registry.deleteCalls != 0 {
		t.Fatalf("registration must not write FusionCollectors\\Sidecar: present=%v deletes=%d", fixture.registry.productKeyPresent, fixture.registry.deleteCalls)
	}
}

func TestRemoteRegistrationDeletesEmptyVersionAndMissingIcon(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.registry.strings["DisplayVersion"] = "1.0.0"
	fixture.registry.strings["DisplayIcon"] = `C:\fusion-collectors\installer.ico`
	cfg := remoteProgramsConfig("  ")

	if err := registerRemoteWindowsPrograms(cfg, fixture.env); err != nil {
		t.Fatalf("register: %v", err)
	}
	if _, ok := fixture.registry.strings["DisplayVersion"]; ok {
		t.Fatal("empty version must delete DisplayVersion")
	}
	if _, ok := fixture.registry.strings["DisplayIcon"]; ok {
		t.Fatal("missing installer.ico must delete DisplayIcon")
	}
	if fixture.registry.strings["DisplayName"] != "Collector Sidecar" || fixture.registry.dwords["NoModify"] != 1 {
		t.Fatalf("registration was incomplete: %#v %#v", fixture.registry.strings, fixture.registry.dwords)
	}
}

func TestNonRemoteInstallDoesNotRegisterPrograms(t *testing.T) {
	fixture := newProgramsFixture()
	cfg := remoteProgramsConfig("3.2.1")
	cfg.RemoteExecutionID = ""
	var warnings []string
	message := windowsRemoteInstallCompleteMessage(cfg, fixture.env, func(warning string) {
		warnings = append(warnings, warning)
	})
	if message != windowsInstallCompleteMessage || len(warnings) != 0 || len(fixture.events) != 0 || fixture.registry.applied {
		t.Fatalf("message=%q warnings=%v events=%v applied=%v", message, warnings, fixture.events, fixture.registry.applied)
	}
}

func TestNonCanonicalInstallDirSkipsProgramRegistration(t *testing.T) {
	for _, installDir := range []string{`D:\fusion-collectors`, `C:\fusion-collectors\bin`, `C:fusion-collectors`, `C:\fusion-collectors.bklite-backup`} {
		fixture := newProgramsFixture()
		cfg := remoteProgramsConfig("3.2.1")
		cfg.InstallDir = installDir
		var warnings []string
		message := windowsRemoteInstallCompleteMessage(cfg, fixture.env, func(warning string) {
			warnings = append(warnings, warning)
		})
		if message != windowsInstallUnregisteredMessage || len(warnings) != 1 || len(fixture.events) != 0 || fixture.registry.applied {
			t.Fatalf("dir %s message=%q warnings=%v events=%v", installDir, message, warnings, fixture.events)
		}
	}
}

func TestCanonicalInstallDirVariantsRegister(t *testing.T) {
	for _, installDir := range []string{`C:\fusion-collectors`, `c:/fusion-collectors/`, `C:\fusion-collectors\bin\..`} {
		if !isCanonicalWindowsProgramsDir(installDir) {
			t.Fatalf("%s should be the canonical install directory", installDir)
		}
	}
}

func TestUninstallerCopyFailureSkipsRegistry(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.copyErr = errors.New("disk full")
	fixture.files[windowsProgramsInstallDir+`\uninstall.exe`] = []byte("old-nsis")
	var warnings []string
	message := windowsRemoteInstallCompleteMessage(remoteProgramsConfig("3.2.1"), fixture.env, func(warning string) {
		warnings = append(warnings, warning)
	})
	if message != windowsInstallUnregisteredMessage || len(warnings) != 1 {
		t.Fatalf("message=%q warnings=%v", message, warnings)
	}
	if fixture.registry.applied || fixture.registry.applyAttempted {
		t.Fatal("registry was written after uninstall.exe copy failed")
	}
	if string(fixture.files[windowsProgramsInstallDir+`\uninstall.exe`]) != "old-nsis" {
		t.Fatal("failed copy changed uninstall.exe")
	}
}

func TestRegistryFailureKeepsInstallationSuccessful(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.registry.applyErr = errors.New("write https://server.example/session?token=abc password=secret")
	fixture.registry.strings["DisplayName"] = "previous"
	var warnings []string
	message := windowsRemoteInstallCompleteMessage(remoteProgramsConfig("3.2.1"), fixture.env, func(warning string) {
		warnings = append(warnings, "WARN: "+warning)
	})
	if message != windowsInstallUnregisteredMessage {
		t.Fatalf("message=%q", message)
	}
	if len(warnings) != 1 || !strings.HasPrefix(warnings[0], "WARN: ") {
		t.Fatalf("warnings=%v", warnings)
	}
	if strings.Contains(warnings[0], "server.example") || strings.Contains(warnings[0], "token") || strings.Contains(warnings[0], "secret") {
		t.Fatalf("warning leaked credentials: %s", warnings[0])
	}
	if fixture.registry.strings["DisplayName"] != "previous" {
		t.Fatal("failed registry write changed the existing record")
	}
	if string(fixture.files[windowsProgramsInstallDir+`\uninstall.exe`]) != "bootstrap-bytes" {
		t.Fatal("uninstall.exe should already have been replaced before the registry failure")
	}
}

func TestProgramRegistryUses32BitView(t *testing.T) {
	if windowsRegistry32BitView != 0x200 {
		t.Fatalf("32-bit registry view = %#x", windowsRegistry32BitView)
	}
}

func TestUninstallExecutableRejectsInstallArguments(t *testing.T) {
	fixture := newProgramsFixture()
	code := runWindowsUninstall([]string{
		`C:\fusion-collectors\Uninstall.EXE`,
		"--url",
		"https://server.example/session?token=abc",
		"--execution-id",
		"abc",
	}, fixture.env)
	if code == 0 {
		t.Fatal("install arguments were accepted")
	}
	if len(fixture.removed) != 0 || len(fixture.launches) != 0 || fixture.confirmCalls != 0 || fixture.serviceCalls != 0 {
		t.Fatalf("install arguments had side effects: removed=%v launches=%v confirm=%d service=%d", fixture.removed, fixture.launches, fixture.confirmCalls, fixture.serviceCalls)
	}
	if strings.Contains(fixture.stderr.String(), "server.example") || strings.Contains(fixture.stderr.String(), "token") {
		t.Fatalf("stderr leaked arguments: %s", fixture.stderr.String())
	}
	if isUninstallExecutable(`C:\Windows\Temp\bklite-controller-bootstrap.exe`) {
		t.Fatal("bootstrap executable entered uninstall mode")
	}
}

func TestInteractiveUninstallCancelDoesNothing(t *testing.T) {
	fixture := newProgramsFixture()
	code := runWindowsUninstall([]string{`C:\fusion-collectors\uninstall.exe`}, fixture.env)
	if code != 0 || fixture.confirmCalls != 1 {
		t.Fatalf("code=%d confirm=%d", code, fixture.confirmCalls)
	}
	if len(fixture.removed) != 0 || len(fixture.launches) != 0 || fixture.serviceCalls != 0 || len(fixture.notices) != 0 {
		t.Fatalf("cancel had side effects: removed=%v launches=%v service=%d notices=%v", fixture.removed, fixture.launches, fixture.serviceCalls, fixture.notices)
	}
}

func TestInteractiveUninstallRelaunchesCopy(t *testing.T) {
	for _, elevated := range []bool{false, true} {
		fixture := newProgramsFixture()
		fixture.confirm = true
		fixture.elevated = elevated
		code := runWindowsUninstall([]string{`C:\fusion-collectors\uninstall.exe`}, fixture.env)
		if code != 0 || len(fixture.launches) != 1 {
			t.Fatalf("elevated=%v code=%d launches=%v", elevated, code, fixture.launches)
		}
		launch := fixture.launches[0]
		if launch.wait || executableBaseName(launch.path) != windowsUninstallExeName {
			t.Fatalf("launch = %#v", launch)
		}
		if !strings.HasPrefix(strings.ToLower(executableBaseName(windowsPathDir(launch.path))), "bklite-uninstall-") {
			t.Fatalf("copy directory = %s", launch.path)
		}
		wantVerb := "runas"
		if elevated {
			wantVerb = "open"
		}
		if launch.verb != wantVerb || !reflect.DeepEqual(launch.args, []string{windowsUninstallConfirmedArg}) {
			t.Fatalf("launch = %#v", launch)
		}
		if string(fixture.files[launch.path]) != "bootstrap-bytes" {
			t.Fatal("staged uninstall.exe content mismatch")
		}
		if fixture.serviceCalls != 0 || len(fixture.removed) != 0 {
			t.Fatal("parent executed uninstall before the elevated copy")
		}
	}
}

func TestUninstallLaunchFailureShowsElevationMessage(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.confirm = true
	fixture.launchErr = errors.New("The operation was canceled by the user")
	code := runWindowsUninstall([]string{`C:\fusion-collectors\uninstall.exe`}, fixture.env)
	if code == 0 || len(fixture.notices) != 1 || fixture.notices[0] != errUninstallElevation.Error() {
		t.Fatalf("code=%d notices=%v", code, fixture.notices)
	}
	if len(fixture.removed) != 0 || fixture.serviceCalls != 0 {
		t.Fatal("failed elevation deleted files")
	}
}

func TestSilentUninstallWithoutElevationFails(t *testing.T) {
	fixture := newProgramsFixture()
	code := runWindowsUninstall([]string{`C:\fusion-collectors\uninstall.exe`, "/s"}, fixture.env)
	if code == 0 {
		t.Fatal("silent unelevated uninstall succeeded")
	}
	if len(fixture.launches) != 0 || len(fixture.removed) != 0 || len(fixture.notices) != 0 || fixture.confirmCalls != 0 {
		t.Fatalf("silent unelevated uninstall had side effects: launches=%v removed=%v notices=%v confirm=%d", fixture.launches, fixture.removed, fixture.notices, fixture.confirmCalls)
	}
	if !strings.Contains(fixture.stderr.String(), errUninstallElevation.Error()) {
		t.Fatalf("stderr=%s", fixture.stderr.String())
	}
}

func TestSilentElevatedUninstallReturnsChildExitCode(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.launchCode = 7
	code := runWindowsUninstall([]string{`C:\fusion-collectors\uninstall.exe`, "/S"}, fixture.env)
	if code != 7 || len(fixture.launches) != 1 {
		t.Fatalf("code=%d launches=%v", code, fixture.launches)
	}
	launch := fixture.launches[0]
	if !launch.wait || launch.verb != "open" || !reflect.DeepEqual(launch.args, []string{"/S", windowsUninstallConfirmedArg}) {
		t.Fatalf("launch = %#v", launch)
	}
	if fixture.serviceCalls != 0 {
		t.Fatal("parent performed uninstall itself")
	}
}

func TestConfirmedUninstallWithoutElevationDoesNotDelete(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.executable = `C:\Temp\bklite-uninstall-test\uninstall.exe`
	code := runWindowsUninstall([]string{
		fixture.executable,
		"/S",
		windowsUninstallConfirmedArg,
	}, fixture.env)
	if code == 0 || len(fixture.launches) != 0 || len(fixture.removed) != 0 || len(fixture.notices) != 0 {
		t.Fatalf("code=%d launches=%v removed=%v notices=%v", code, fixture.launches, fixture.removed, fixture.notices)
	}
	if !strings.Contains(fixture.stderr.String(), errUninstallElevation.Error()) {
		t.Fatalf("stderr=%s", fixture.stderr.String())
	}
}

func TestUninstallLockFailureDeletesNothing(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.confirm = true
	fixture.lockErr = errors.New("another installation is already running: https://secret.example/token")
	fixture.registry.productKeyPresent = true
	fixture.executable = `C:\Temp\bklite-uninstall-child\uninstall.exe`
	code := runWindowsUninstall([]string{
		fixture.executable,
		windowsUninstallConfirmedArg,
	}, fixture.env)
	if code == 0 || len(fixture.notices) != 1 || fixture.notices[0] != errUninstallInProgress.Error() {
		t.Fatalf("code=%d notices=%v", code, fixture.notices)
	}
	if strings.Contains(fixture.notices[0], "secret.example") || strings.Contains(fixture.stderr.String(), "secret.example") {
		t.Fatal("lock failure leaked the underlying error")
	}
	if len(fixture.removed) != 0 || fixture.serviceCalls != 0 || fixture.registry.deleteCalls != 0 || !fixture.registry.productKeyPresent {
		t.Fatalf("lock failure deleted state: removed=%v service=%d deletes=%d", fixture.removed, fixture.serviceCalls, fixture.registry.deleteCalls)
	}
}

func TestWindowsUninstallPlanIsWhitelistOnly(t *testing.T) {
	plan, err := planWindowsLocalUninstall([]string{`C:/fusion-collectors.bklite-backup-retained-42`})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		`C:\fusion-collectors`,
		`C:\fusion-collectors.bklite-staging`,
		`C:\fusion-collectors.bklite-backup`,
		`C:\fusion-collectors.bklite-install.fence`,
		`C:\fusion-collectors.bklite-backup-retained-42`,
		`C:\fusion-collectors.bklite-install.lock`,
	}
	got := append(append([]string{}, plan.filePaths()...), plan.LockPath)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("plan = %#v", got)
	}
	for _, path := range got {
		if !uninstallPathAllowed(path) {
			t.Fatalf("planned path is outside the whitelist: %s", path)
		}
	}
	for _, candidate := range []string{
		`C:\Windows`,
		`C:\fusion-collectors.bklite-backup-retained-1\nested`,
		`D:\fusion-collectors.bklite-backup-retained-1`,
		`C:\fusion-collectors.bklite-backup-retained-1\..\Windows`,
	} {
		if _, err := planWindowsLocalUninstall([]string{candidate}); !errors.Is(err, errUninstallScope) {
			t.Fatalf("candidate %s error = %v", candidate, err)
		}
	}
}

func TestUninstallRejectsRetainedPathBeforeDeleting(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.executable = `C:\Temp\bklite-uninstall-child\uninstall.exe`
	fixture.retained = []string{`C:\Windows\System32`}
	fixture.registry.productKeyPresent = true
	code := runWindowsUninstall(confirmedUninstallArgs(), fixture.env)
	if code == 0 || fixture.serviceCalls != 0 || len(fixture.removed) != 0 || fixture.registry.deleteCalls != 0 || !fixture.registry.productKeyPresent {
		t.Fatalf("code=%d service=%d removed=%v deletes=%d", code, fixture.serviceCalls, fixture.removed, fixture.registry.deleteCalls)
	}
}

func TestUninstallFailureKeepsProgramRegistry(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.executable = `C:\Temp\bklite-uninstall-child\uninstall.exe`
	fixture.registry.productKeyPresent = true
	fixture.removeErr = map[string]error{
		strings.ToLower(`C:\fusion-collectors.bklite-staging`): errors.New("token=secret"),
	}
	code := runWindowsUninstall(confirmedUninstallArgs(), fixture.env)
	if code == 0 || len(fixture.notices) != 1 || fixture.notices[0] != errUninstallFiles.Error() {
		t.Fatalf("code=%d notices=%v", code, fixture.notices)
	}
	if strings.Contains(fixture.notices[0], "secret") || fixture.registry.deleteCalls != 0 || !fixture.registry.productKeyPresent {
		t.Fatalf("registry was dropped: notices=%v deletes=%d present=%v", fixture.notices, fixture.registry.deleteCalls, fixture.registry.productKeyPresent)
	}
	if containsPath(fixture.removed, `C:\fusion-collectors.bklite-install.lock`) {
		t.Fatal("lock file was removed after a failed uninstall")
	}
}

func TestUninstallIsIdempotentWhenAlreadyRemoved(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.executable = `C:\Temp\bklite-uninstall-test\uninstall.exe`
	fixture.retained = []string{`C:\fusion-collectors.bklite-backup-retained-7`}
	code := runWindowsUninstall([]string{fixture.executable, "/S", windowsUninstallConfirmedArg}, fixture.env)
	if code != 0 {
		t.Fatalf("code=%d stderr=%s", code, fixture.stderr.String())
	}
	if len(fixture.notices) != 0 || fixture.stderr.Len() != 0 {
		t.Fatalf("silent success produced output: notices=%v stderr=%s", fixture.notices, fixture.stderr.String())
	}
	want := []string{
		`C:\fusion-collectors`,
		`C:\fusion-collectors.bklite-staging`,
		`C:\fusion-collectors.bklite-backup`,
		`C:\fusion-collectors.bklite-install.fence`,
		`C:\fusion-collectors.bklite-backup-retained-7`,
		`C:\fusion-collectors.bklite-install.lock`,
	}
	if !reflect.DeepEqual(fixture.removed, want) {
		t.Fatalf("removed = %#v", fixture.removed)
	}
	if fixture.lockRemovedWhileHeld {
		t.Fatal("lock file was removed while the install lock was held")
	}
	if len(fixture.removedWhileLocked) != len(want) || !fixture.removedWhileLocked[0] || fixture.removedWhileLocked[len(want)-1] {
		t.Fatalf("lock state during removal = %v", fixture.removedWhileLocked)
	}
	if fixture.lockDir != windowsProgramsInstallDir || !fixture.serviceWhileLocked || fixture.registry.deleteCalls != 1 {
		t.Fatalf("lockDir=%s serviceLocked=%v deletes=%d", fixture.lockDir, fixture.serviceWhileLocked, fixture.registry.deleteCalls)
	}
	if !reflect.DeepEqual(fixture.scheduled, []string{
		`C:\Temp\bklite-uninstall-test\` + windowsOriginalUninstallName,
		fixture.executable,
		`C:\Temp\bklite-uninstall-test`,
	}) {
		t.Fatalf("scheduled = %#v", fixture.scheduled)
	}
}

func TestPhaseTwoMovesOriginalUninstallerBeforeDeletingInstallDir(t *testing.T) {
	cases := []struct {
		name       string
		executable string
		args       []string
	}{
		{
			name:       "silent",
			executable: `C:\Users\Admin\AppData\Local\Temp\bklite-uninstall-silent\uninstall.exe`,
			args:       []string{"/S", windowsUninstallConfirmedArg},
		},
		{
			name:       "interactive",
			executable: `C:\Users\Admin\AppData\Local\Temp\bklite-uninstall-interactive\uninstall.exe`,
			args:       []string{windowsUninstallConfirmedArg},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fixture := newProgramsFixture()
			fixture.elevated = true
			fixture.executable = tc.executable
			code := runWindowsUninstall(append([]string{tc.executable}, tc.args...), fixture.env)
			if code != 0 {
				t.Fatalf("code=%d stderr=%s notices=%v", code, fixture.stderr.String(), fixture.notices)
			}
			staging := windowsPathDir(tc.executable)
			if !reflect.DeepEqual(fixture.moveTargets, []string{staging}) {
				t.Fatalf("move targets = %#v", fixture.moveTargets)
			}
			if fixture.installDirRemovedBeforeMove {
				t.Fatal("install directory was deleted before the original uninstaller was moved")
			}
			if !containsPath(fixture.removed, windowsProgramsInstallDir) {
				t.Fatal("install directory was not deleted after the move")
			}
			if !reflect.DeepEqual(fixture.scheduled, []string{
				staging + `\` + windowsOriginalUninstallName,
				tc.executable,
				staging,
			}) {
				t.Fatalf("scheduled = %#v", fixture.scheduled)
			}
		})
	}
}

func TestOriginalUninstallerMoveFailureDoesNotBlockDeletion(t *testing.T) {
	fixture := newProgramsFixture()
	fixture.elevated = true
	fixture.executable = `C:\Temp\bklite-uninstall-test\uninstall.exe`
	fixture.moveErr = errors.New("cross-volume")
	code := runWindowsUninstall([]string{fixture.executable, "/S", windowsUninstallConfirmedArg}, fixture.env)
	if code != 0 {
		t.Fatalf("code=%d stderr=%s", code, fixture.stderr.String())
	}
	if !reflect.DeepEqual(fixture.moveTargets, []string{`C:\Temp\bklite-uninstall-test`}) {
		t.Fatalf("move targets = %#v", fixture.moveTargets)
	}
	if !containsPath(fixture.removed, windowsProgramsInstallDir) {
		t.Fatal("install directory was not deleted after the move failed")
	}
	if !reflect.DeepEqual(fixture.scheduled, []string{fixture.executable, `C:\Temp\bklite-uninstall-test`}) {
		t.Fatalf("scheduled = %#v", fixture.scheduled)
	}
}

func TestConfirmedArgumentOutsideStagingIsRejected(t *testing.T) {
	executables := []string{
		`C:\fusion-collectors\uninstall.exe`,
		`C:\Temp\bklite-uninstall\uninstall.exe`,
	}
	argSets := [][]string{
		{windowsUninstallConfirmedArg},
		{"/S", windowsUninstallConfirmedArg},
	}
	for _, executable := range executables {
		for _, extra := range argSets {
			fixture := newProgramsFixture()
			fixture.elevated = true
			fixture.executable = executable
			fixture.registry.productKeyPresent = true
			code := runWindowsUninstall(append([]string{executable}, extra...), fixture.env)
			if code == 0 || len(fixture.removed) != 0 || fixture.serviceCalls != 0 || len(fixture.moveTargets) != 0 || len(fixture.launches) != 0 || fixture.registry.deleteCalls != 0 || !fixture.registry.productKeyPresent {
				t.Fatalf("executable=%s args=%v code=%d removed=%v service=%d moves=%v launches=%v deletes=%d", executable, extra, code, fixture.removed, fixture.serviceCalls, fixture.moveTargets, fixture.launches, fixture.registry.deleteCalls)
			}
			if !strings.Contains(fixture.stderr.String(), errUninstallInstallArguments.Error()) || strings.Contains(fixture.stderr.String(), windowsUninstallConfirmedArg) {
				t.Fatalf("stderr=%s", fixture.stderr.String())
			}
		}
	}
}

func TestMoveOriginalUninstallerOnlyAcceptsRunningStaging(t *testing.T) {
	dest, err := originalUninstallerDestination(`C:\Temp\bklite-uninstall-1`)
	if err != nil || dest != `C:\Temp\bklite-uninstall-1\`+windowsOriginalUninstallName {
		t.Fatalf("dest=%s err=%v", dest, err)
	}
	for _, staging := range []string{
		`C:\fusion-collectors`,
		`C:\Temp\bklite-uninstall`,
		`C:\Temp\bklite-uninstall-1\..\Windows`,
	} {
		if _, err := originalUninstallerDestination(staging); err == nil {
			t.Fatalf("accepted staging %s", staging)
		}
	}
	if _, err := moveOriginalUninstaller(`C:\Temp\bklite-uninstall-test`); err == nil {
		t.Fatal("moved uninstall.exe into a staging directory that is not the running copy")
	}
}

func TestRemoveUninstallStagingLeavesInstallDir(t *testing.T) {
	root := t.TempDir()
	staging, err := os.MkdirTemp(root, "bklite-uninstall-")
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(staging, windowsUninstallExeName)
	if err := os.WriteFile(exe, []byte("x"), 0o755); err != nil {
		t.Fatal(err)
	}
	removeUninstallStaging(exe)
	if _, err := os.Stat(staging); !os.IsNotExist(err) {
		t.Fatalf("staging directory still exists: %v", err)
	}
	removeUninstallStaging(windowsProgramsInstallDir + `\` + windowsUninstallExeName)
}

func TestCopyExecutableAsUninstallerReplacesExistingFile(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "bootstrap.exe")
	if err := os.WriteFile(source, []byte("new-uninstaller"), 0o755); err != nil {
		t.Fatal(err)
	}
	installDir := filepath.Join(dir, "install")
	if err := os.Mkdir(installDir, 0o755); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(installDir, windowsUninstallExeName)
	if err := os.WriteFile(target, []byte("old-nsis"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := copyExecutableAsUninstaller(source, installDir); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(target)
	if err != nil || string(got) != "new-uninstaller" {
		t.Fatalf("uninstall.exe = %q, %v", got, err)
	}
	entries, err := os.ReadDir(installDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Name() != windowsUninstallExeName {
		names := make([]string, 0, len(entries))
		for _, entry := range entries {
			names = append(names, entry.Name())
		}
		t.Fatalf("temp uninstaller left behind: %v", names)
	}
}

func TestStageUninstallerKeepsUninstallFileName(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "uninstall.exe")
	if err := os.WriteFile(source, []byte("bytes"), 0o755); err != nil {
		t.Fatal(err)
	}
	dest, err := stageWindowsUninstallCopy(root, source)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(dest) != windowsUninstallExeName {
		t.Fatalf("staged name = %s", dest)
	}
	if !strings.HasPrefix(filepath.Base(filepath.Dir(dest)), "bklite-uninstall-") {
		t.Fatalf("staged directory = %s", dest)
	}
	got, err := os.ReadFile(dest)
	if err != nil || string(got) != "bytes" {
		t.Fatalf("staged content = %q, %v", got, err)
	}
}

type programsFixture struct {
	env                         *windowsProgramsEnv
	files                       map[string][]byte
	events                      []string
	copyErr                     error
	registry                    *fakeProgramRegistry
	elevated                    bool
	confirm                     bool
	confirmCalls                int
	notices                     []string
	lockErr                     error
	lockHeld                    bool
	lockDir                     string
	lockRemovedWhileHeld        bool
	removedWhileLocked          []bool
	serviceErr                  error
	serviceCalls                int
	serviceWhileLocked          bool
	retained                    []string
	removed                     []string
	removeErr                   map[string]error
	launches                    []recordedLaunch
	launchCode                  int
	launchErr                   error
	scheduled                   []string
	moveErr                     error
	moveTargets                 []string
	installDirRemovedBeforeMove bool
	stderr                      bytes.Buffer
	executable                  string
}

type recordedLaunch struct {
	path string
	args []string
	verb string
	wait bool
}

type fakeProgramRegistry struct {
	fixture           *programsFixture
	strings           map[string]string
	dwords            map[string]uint32
	ops               []registryValueOp
	applyErr          error
	applied           bool
	applyAttempted    bool
	deleteErr         error
	deleteCalls       int
	productKeyPresent bool
}

func newProgramsFixture() *programsFixture {
	fixture := &programsFixture{
		files: map[string][]byte{
			`C:\Windows\Temp\bklite-controller-bootstrap.exe`: []byte("bootstrap-bytes"),
		},
		executable: `C:\Windows\Temp\bklite-controller-bootstrap.exe`,
		registry: &fakeProgramRegistry{
			strings: map[string]string{},
			dwords:  map[string]uint32{},
		},
	}
	fixture.registry.fixture = fixture
	fixture.env = &windowsProgramsEnv{
		Executable: func() (string, error) {
			return fixture.executable, nil
		},
		CopyUninstaller: func(sourcePath, installDir string) error {
			fixture.events = append(fixture.events, "copy")
			if fixture.copyErr != nil {
				return fixture.copyErr
			}
			content, ok := fixture.files[sourcePath]
			if !ok {
				return errors.New("missing executable")
			}
			copied := append([]byte(nil), content...)
			fixture.files[installDir+`\uninstall.exe`] = copied
			return nil
		},
		IconExists: func(installDir string) (bool, error) {
			_, ok := fixture.files[installDir+`\installer.ico`]
			return ok, nil
		},
		Registry: fixture.registry,
		IsElevated: func() bool {
			return fixture.elevated
		},
		Confirm: func() (bool, error) {
			fixture.confirmCalls++
			return fixture.confirm, nil
		},
		Notify: func(_ bool, message string) error {
			fixture.notices = append(fixture.notices, message)
			return nil
		},
		AcquireLock: func(installDir string) (func(), error) {
			fixture.lockDir = installDir
			if fixture.lockErr != nil {
				return nil, fixture.lockErr
			}
			fixture.lockHeld = true
			return func() {
				fixture.lockHeld = false
			}, nil
		},
		StopAndDeleteService: func() error {
			fixture.serviceCalls++
			fixture.serviceWhileLocked = fixture.lockHeld
			return fixture.serviceErr
		},
		ListRetainedBackups: func() ([]string, error) {
			return append([]string(nil), fixture.retained...), nil
		},
		RemovePath:       fixture.removePath,
		StageUninstaller: fixture.stageUninstaller,
		Launch: func(path string, args []string, verb string, wait bool) (int, error) {
			fixture.launches = append(fixture.launches, recordedLaunch{path: path, args: append([]string(nil), args...), verb: verb, wait: wait})
			return fixture.launchCode, fixture.launchErr
		},
		MoveOriginalUninstaller: func(stagingDir string) (string, error) {
			stagingDir = normalizeWindowsPath(stagingDir)
			fixture.moveTargets = append(fixture.moveTargets, stagingDir)
			fixture.installDirRemovedBeforeMove = containsPath(fixture.removed, windowsProgramsInstallDir)
			if fixture.moveErr != nil {
				return "", fixture.moveErr
			}
			return stagingDir + `\` + windowsOriginalUninstallName, nil
		},
		ScheduleDelete: func(path string) error {
			fixture.scheduled = append(fixture.scheduled, path)
			return nil
		},
		Stderr: &fixture.stderr,
	}
	return fixture
}

func (fixture *programsFixture) stageUninstaller(sourcePath string) (string, error) {
	content, ok := fixture.files[sourcePath]
	if !ok {
		return "", errors.New("missing executable")
	}
	dest := `C:\Temp\bklite-uninstall-test\uninstall.exe`
	fixture.files[dest] = append([]byte(nil), content...)
	return dest, nil
}

func (fixture *programsFixture) removePath(path string) error {
	normalized := normalizeWindowsPath(path)
	if !uninstallPathAllowed(normalized) {
		return errUninstallScope
	}
	if strings.EqualFold(normalized, `C:\fusion-collectors.bklite-install.lock`) {
		fixture.lockRemovedWhileHeld = fixture.lockHeld
	}
	if fixture.removeErr != nil {
		if err := fixture.removeErr[strings.ToLower(normalized)]; err != nil {
			return err
		}
	}
	fixture.removedWhileLocked = append(fixture.removedWhileLocked, fixture.lockHeld)
	fixture.removed = append(fixture.removed, normalized)
	return nil
}

func (registry *fakeProgramRegistry) Apply(ops []registryValueOp) error {
	registry.applyAttempted = true
	registry.fixture.events = append(registry.fixture.events, "registry")
	if registry.applyErr != nil {
		return registry.applyErr
	}
	registry.ops = append([]registryValueOp(nil), ops...)
	for _, op := range ops {
		switch op.Kind {
		case registryValueDelete:
			delete(registry.strings, op.Name)
			delete(registry.dwords, op.Name)
		case registryValueString:
			registry.strings[op.Name] = op.String
			delete(registry.dwords, op.Name)
		case registryValueDWord:
			registry.dwords[op.Name] = op.DWord
			delete(registry.strings, op.Name)
		default:
			return errors.New("unexpected registry operation")
		}
	}
	registry.applied = true
	return nil
}

func (registry *fakeProgramRegistry) Delete() error {
	registry.deleteCalls++
	if registry.deleteErr != nil {
		return registry.deleteErr
	}
	registry.strings = map[string]string{}
	registry.dwords = map[string]uint32{}
	registry.productKeyPresent = false
	return nil
}

func remoteProgramsConfig(version string) *Config {
	return &Config{
		RemoteExecutionID: "1123456789abcdef0123456789abcdef",
		InstallDir:        windowsProgramsInstallDir,
		Package:           PackageConfig{Version: version},
	}
}

func confirmedUninstallArgs() []string {
	return []string{`C:\Temp\bklite-uninstall-child\uninstall.exe`, windowsUninstallConfirmedArg}
}

func containsPath(paths []string, want string) bool {
	for _, path := range paths {
		if strings.EqualFold(path, want) {
			return true
		}
	}
	return false
}
