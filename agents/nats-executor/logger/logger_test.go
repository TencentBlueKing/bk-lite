package logger

import (
	"log/slog"
	"testing"
)

func TestSetLevelFromEnvAndGetLevel(t *testing.T) {
	testCases := []struct {
		env  string
		want string
	}{
		{env: "debug", want: "debug"},
		{env: "info", want: "info"},
		{env: "warning", want: "warn"},
		{env: "error", want: "error"},
		{env: "unexpected", want: "info"},
		{env: "", want: "info"},
	}

	for _, tt := range testCases {
		t.Run(tt.env, func(t *testing.T) {
			t.Setenv("LOG_LEVEL", tt.env)
			currentLevel = &slog.LevelVar{}
			setLevelFromEnv()
			if got := GetLevel(); got != tt.want {
				t.Fatalf("GetLevel() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestSetLevelIgnoresUnknownValue(t *testing.T) {
	currentLevel = &slog.LevelVar{}
	currentLevel.Set(slog.LevelWarn)

	SetLevel("unknown")

	if got := GetLevel(); got != "warn" {
		t.Fatalf("expected level to stay warn, got %q", got)
	}
}

func TestSetLevelSupportsAllDeclaredLevels(t *testing.T) {
	testCases := []struct {
		input string
		want  string
	}{
		{input: "debug", want: "debug"},
		{input: "info", want: "info"},
		{input: "warn", want: "warn"},
		{input: "warning", want: "warn"},
		{input: "error", want: "error"},
	}

	for _, tt := range testCases {
		t.Run(tt.input, func(t *testing.T) {
			currentLevel = &slog.LevelVar{}
			SetLevel(tt.input)
			if got := GetLevel(); got != tt.want {
				t.Fatalf("GetLevel() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestLogHelpersAndFatalUseConfiguredExit(t *testing.T) {
	calls := 0
	originalExit := exitFunc
	exitFunc = func(code int) {
		calls++
		if code != 1 {
			t.Fatalf("unexpected exit code: %d", code)
		}
	}
	defer func() { exitFunc = originalExit }()

	Debug("debug message")
	Debugf("debug %s", "formatted")
	Info("info message")
	Infof("info %s", "formatted")
	Warn("warn message")
	Warnf("warn %s", "formatted")
	Error("error message")
	Errorf("error %s", "formatted")
	Fatal("fatal message")
	Fatalf("fatal %s", "formatted")

	if calls != 2 {
		t.Fatalf("expected Fatal and Fatalf to invoke exit twice, got %d", calls)
	}
}
