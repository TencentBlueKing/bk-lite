package local

import (
	"encoding/json"
	"os"
	"runtime"
	"slices"
	"strings"
	"testing"

	"nats-executor/utils"
)

func TestUsesWindowsFileScript(t *testing.T) {
	if usesWindowsFileScript(ShellTypePowerShell, "linux") {
		t.Fatal("linux must not use Windows file script launch")
	}
	if !usesWindowsFileScript(ShellTypePowerShell, "windows") {
		t.Fatal("windows powershell must use file script launch")
	}
	if !usesWindowsFileScript(ShellTypeBat, "windows") {
		t.Fatal("windows bat must use file script launch")
	}
	if usesWindowsFileScript(ShellTypeSh, "windows") {
		t.Fatal("sh must not use Windows file script launch")
	}
}

func TestPrepareWindowsLocalScriptSkipsNonWindows(t *testing.T) {
	launch, err := prepareWindowsLocalScript(ShellTypePowerShell, "Write-Output hi", "linux", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if launch != nil {
		t.Fatal("expected nil launch on non-windows")
	}
}

func TestPrepareWindowsLocalScriptRejectsOversize(t *testing.T) {
	huge := strings.Repeat("a", windowsScriptMaxBytes+1)
	launch, err := prepareWindowsLocalScript(ShellTypePowerShell, huge, "windows", nil)
	if launch != nil {
		t.Fatal("expected nil launch for oversized script")
	}
	if err == nil || !strings.Contains(err.Error(), "Windows script exceeds 512 KiB limit") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestPrepareWindowsLocalScriptPowerShellUsesFileArgv(t *testing.T) {
	script := "Write-Output 'hello-from-file'\n" + strings.Repeat("# pad\n", 2000)
	launch, err := prepareWindowsLocalScript(ShellTypePowerShell, script, "windows", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if launch == nil {
		t.Fatal("expected launch")
	}
	defer launch.Cleanup()

	if launch.Name != ShellTypePowerShell {
		t.Fatalf("unexpected name: %s", launch.Name)
	}
	joined := strings.Join(launch.Args, " ")
	if !strings.Contains(joined, "-File "+launch.Path) {
		t.Fatalf("expected -File argv, got %v", launch.Args)
	}
	for _, arg := range launch.Args {
		if len(arg) > 4096 {
			t.Fatalf("argv element too long for CreateProcess safety: %d", len(arg))
		}
	}

	content, readErr := os.ReadFile(launch.Path)
	if readErr != nil {
		t.Fatalf("read temp script: %v", readErr)
	}
	if len(content) < 3 || content[0] != 0xef || content[1] != 0xbb || content[2] != 0xbf {
		t.Fatalf("expected UTF-8 BOM, got prefix %v", content[:min(len(content), 3)])
	}
	body := string(content[3:])
	if !strings.Contains(body, "[Console]::OutputEncoding") {
		t.Fatalf("expected encoding preamble in script body")
	}
	if !strings.Contains(body, "hello-from-file") {
		t.Fatalf("expected user script in body")
	}

	launch.Cleanup()
	if _, statErr := os.Stat(launch.Path); !os.IsNotExist(statErr) {
		t.Fatalf("expected temp script removed, stat err=%v", statErr)
	}
}

func TestPrepareWindowsLocalScriptBatUsesCmdFile(t *testing.T) {
	launch, err := prepareWindowsLocalScript(ShellTypeBat, "echo bat-from-file", "windows", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if launch == nil {
		t.Fatal("expected launch")
	}
	defer launch.Cleanup()

	if launch.Name != "cmd" {
		t.Fatalf("unexpected name: %s", launch.Name)
	}
	if len(launch.Args) != 4 || launch.Args[0] != "/d" || launch.Args[1] != "/q" || launch.Args[2] != "/c" {
		t.Fatalf("unexpected cmd argv: %v", launch.Args)
	}
	if launch.Args[3] != launch.Path {
		t.Fatalf("expected script path as last argv, got %v", launch.Args)
	}

	content, readErr := os.ReadFile(launch.Path)
	if readErr != nil {
		t.Fatalf("read temp script: %v", readErr)
	}
	text := string(content)
	if !strings.Contains(text, "chcp 65001") {
		t.Fatalf("expected chcp preamble, got %q", text)
	}
	if !strings.Contains(text, "echo bat-from-file") {
		t.Fatalf("expected user command, got %q", text)
	}
}

func TestExecuteRejectsWindowsScriptOver512KiB(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Execute oversize path is Windows-only")
	}
	huge := strings.Repeat("x", windowsScriptMaxBytes+1)
	resp := Execute(ExecuteRequest{
		Command:        huge,
		ExecuteTimeout: 5,
		Shell:          ShellTypePowerShell,
	}, "oversize-script")
	if resp.Success {
		t.Fatalf("expected failure, got %+v", resp)
	}
	if resp.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("expected invalid_request, got %+v", resp)
	}
	if !strings.Contains(resp.Error, "Windows script exceeds 512 KiB limit") {
		t.Fatalf("unexpected error: %+v", resp)
	}
}

func TestExecuteWindowsLongPowerShellBypassesCommandLineLimit(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("long PowerShell Execute path is Windows-only")
	}
	// Larger than Windows CreateProcess ~32,767 limit; well under 512 KiB.
	const marker = "BKLITE_LONG_SCRIPT_OK"
	pad := strings.Repeat("# pad-line-for-command-line-limit\n", 2500) // ~90KiB
	script := pad + "Write-Output '" + marker + "'\n"
	if len(script) < 40000 {
		t.Fatalf("test script too short to exercise CreateProcess limit: %d", len(script))
	}

	resp := Execute(ExecuteRequest{
		Command:        script,
		ExecuteTimeout: 60,
		Shell:          ShellTypePowerShell,
	}, "long-powershell-script")

	combined := resp.Output + " " + resp.Error
	if strings.Contains(strings.ToLower(combined), "filename or extension is too long") {
		t.Fatalf("CreateProcess command-line limit still hit: %+v", resp)
	}
	if !resp.Success {
		t.Fatalf("expected long script success via -File, got %+v", resp)
	}
	if !strings.Contains(resp.Output, marker) {
		t.Fatalf("expected marker %q in output, got %q", marker, resp.Output)
	}
}

func TestBatArgsCannotSilentlyRunUnderAnotherShell(t *testing.T) {
	var req ExecuteRequest
	if err := json.Unmarshal([]byte(`{"command":"echo wrong-shell","shell":"sh","execute_timeout":5,"bat_args":["expected"]}`), &req); err != nil {
		t.Fatal(err)
	}
	resp := Execute(req, "test")
	if resp.Success || resp.Code != utils.ErrorCodeInvalidRequest {
		t.Fatalf("expected explicit bat_args rejection, got %+v", resp)
	}
}

func TestBatchLaunchCarriesValuesOnlyInProcessEnvironment(t *testing.T) {
	values := []string{"北京", "", `C:\数据 目录\`, "%TEMP% !PATH! & ^", "a=b,c;d"}
	launch, err := prepareWindowsLocalScript(ShellTypeCmd, "@echo %1", "windows", values)
	if err != nil {
		t.Fatal(err)
	}
	defer launch.Cleanup()
	expected := []string{"BK_JOB_BAT_SCRIPT=" + `"` + launch.Path + `"`, "BK_JOB_BAT_ARGS_READY=1",
		"BK_JOB_BAT_ARG_1=北京", `BK_JOB_BAT_ARG_2=""`, `BK_JOB_BAT_ARG_3="C:\数据 目录\"`,
		`BK_JOB_BAT_ARG_4="%TEMP% !PATH! & ^"`, `BK_JOB_BAT_ARG_5="a=b,c;d"`}
	if !slices.Equal(launch.Env, expected) {
		t.Errorf("unexpected batch process environment: %v", launch.Env)
	}
	line := strings.Join(launch.Args, " ")
	if line != "/d /q /v:off /s /c %BK_JOB_BAT_SCRIPT% %BK_JOB_BAT_ARG_1% %BK_JOB_BAT_ARG_2% %BK_JOB_BAT_ARG_3% %BK_JOB_BAT_ARG_4% %BK_JOB_BAT_ARG_5%" {
		t.Fatalf("unexpected cmd line: %q", line)
	}
}

func TestInvalidBatchArgsLeaveNoScriptOrValuesInErrors(t *testing.T) {
	tmp := t.TempDir()
	for _, k := range []string{"TMP", "TEMP", "TMPDIR"} {
		t.Setenv(k, tmp)
	}
	tests := [][]string{
		{"sensitive\x00"}, {"sensitive\r"}, {"sensitive\n"}, {"sensitive\t"},
		{"sensitive\ufffe"}, {"sensitive\uffff"}, {"sensitive\x7f"}, {"sensitive\""}, {"sensitive\xff"}, {strings.Repeat("😀", 4096)},
		make([]string, 512),
	}
	for _, args := range tests {
		_, err := prepareWindowsLocalScript(ShellTypeBat, "@echo %1", "windows", args)
		if err == nil || strings.Contains(err.Error(), "sensitive") {
			t.Fatal("expected a validation error without argument contents")
		}
	}
	if entries, err := os.ReadDir(tmp); err != nil || len(entries) != 0 {
		t.Fatalf("failed launch left files: %v, %v", entries, err)
	}
}

func TestExecuteWindowsNativeBatchArguments(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("requires Windows cmd.exe")
	}
	resp := Execute(ExecuteRequest{
		Command: strings.Join([]string{
			"@echo off", "echo ready=%BK_JOB_BAT_ARGS_READY%", "echo first=%1",
			"echo second=%2", "echo third=%3", "echo fourth=%4", "shift", "echo shifted=%1",
		}, "\r\n"),
		Shell: ShellTypeCmd, ExecuteTimeout: 10,
		BatArgs: []string{"北京", "", `C:\上海 目录\`, "%PATH% & ! ^"},
	}, "batch-test")
	if !resp.Success {
		t.Fatalf("failed to run batch script: %+v", resp)
	}
	for _, want := range []string{"ready=1", "first=北京", `second=""`, `third="C:\上海 目录\"`, `fourth="%PATH% & ! ^"`, `shifted=""`} {
		if !strings.Contains(resp.Output, want) {
			t.Errorf("expected %q in %q", want, resp.Output)
		}
	}
}
