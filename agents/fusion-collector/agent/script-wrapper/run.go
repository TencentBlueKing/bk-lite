package main

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"time"
)

type runResult struct {
	Stdout    []byte
	ExitCode  int
	Timeout   bool
	Truncated bool
	Err       error
}

func runScript(cfg config, scriptPath string) runResult {
	args := resolveInterpreter(cfg, scriptPath)
	cmd := exec.Command(args[0], args[1:]...)
	stdout := &limitedBuffer{limit: cfg.MaxBytes}
	cmd.Stdout = stdout
	cmd.Stderr = &limitedBuffer{limit: 32 * 1024}
	cmd.Env = childEnv(cfg)
	cmd.Dir = cfg.Root

	uid, gid, isRoot, err := lookupUser(cfg.User)
	if err != nil {
		return runResult{ExitCode: -1, Err: err}
	}
	if isRoot && !cfg.AllowRoot {
		return runResult{ExitCode: -1, Err: errors.New("root is not allowed")}
	}
	cmd.SysProcAttr = sysProcAttrFor(uid, gid, shouldDropPrivileges(cfg.User))

	if err := cmd.Start(); err != nil {
		return runResult{ExitCode: -1, Err: err}
	}
	applyResourceLimits(cmd.Process.Pid, cfg.MemoryBytes)

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	timer := time.NewTimer(cfg.Timeout)
	defer timer.Stop()

	result := runResult{Stdout: stdout.Bytes(), Truncated: stdout.trunc}
	select {
	case err := <-done:
		result.Stdout = stdout.Bytes()
		result.Truncated = stdout.trunc
		result.ExitCode = exitCodeFrom(err)
		result.Err = err
		if result.ExitCode == 0 {
			result.Err = nil
		}
	case <-timer.C:
		killProcessGroup(cmd.Process.Pid)
		<-done
		result.Stdout = stdout.Bytes()
		result.Truncated = stdout.trunc
		result.Timeout = true
		result.ExitCode = 124
		result.Err = errors.New("timeout")
	}
	return result
}

func exitCodeFrom(err error) int {
	if err == nil {
		return 0
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitErr.ExitCode()
	}
	return -1
}

func childEnv(cfg config) []string {
	keep := make([]string, 0, len(cfg.ParamEnv)+8)
	prefix := envBody + "="
	for _, item := range os.Environ() {
		if len(item) >= len(prefix) && item[:len(prefix)] == prefix {
			continue
		}
		keep = append(keep, item)
	}
	keep = append(keep, cfg.ParamEnv...)
	if cfg.ConfigID != "" {
		keep = append(keep, envConfigID+"="+cfg.ConfigID)
	}
	if cfg.InstanceID != "" {
		keep = append(keep, envInstanceID+"="+cfg.InstanceID)
	}
	return keep
}

type limitedBuffer struct {
	limit int
	buf   bytes.Buffer
	trunc bool
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	if b.limit <= 0 {
		return b.buf.Write(p)
	}
	remain := b.limit - b.buf.Len()
	if remain <= 0 {
		b.trunc = true
		return len(p), nil
	}
	if len(p) > remain {
		b.trunc = true
		_, _ = b.buf.Write(p[:remain])
		return len(p), nil
	}
	return b.buf.Write(p)
}

func (b *limitedBuffer) Bytes() []byte {
	return append([]byte(nil), b.buf.Bytes()...)
}
