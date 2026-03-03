package logger

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
)

var (
	defaultLogger *slog.Logger
	currentLevel  *slog.LevelVar
)

func init() {
	currentLevel = &slog.LevelVar{}
	setLevelFromEnv()

	handler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: currentLevel,
	})
	defaultLogger = slog.New(handler)
	slog.SetDefault(defaultLogger)
}

func setLevelFromEnv() {
	levelStr := strings.ToLower(os.Getenv("LOG_LEVEL"))
	switch levelStr {
	case "debug":
		currentLevel.Set(slog.LevelDebug)
	case "info", "":
		currentLevel.Set(slog.LevelInfo)
	case "warn", "warning":
		currentLevel.Set(slog.LevelWarn)
	case "error":
		currentLevel.Set(slog.LevelError)
	default:
		currentLevel.Set(slog.LevelInfo)
	}
}

func SetLevel(level string) {
	switch strings.ToLower(level) {
	case "debug":
		currentLevel.Set(slog.LevelDebug)
	case "info":
		currentLevel.Set(slog.LevelInfo)
	case "warn", "warning":
		currentLevel.Set(slog.LevelWarn)
	case "error":
		currentLevel.Set(slog.LevelError)
	}
}

func GetLevel() string {
	switch currentLevel.Level() {
	case slog.LevelDebug:
		return "debug"
	case slog.LevelInfo:
		return "info"
	case slog.LevelWarn:
		return "warn"
	case slog.LevelError:
		return "error"
	default:
		return "info"
	}
}

func Debug(msg string, args ...any) {
	defaultLogger.Debug(msg, args...)
}

func Debugf(format string, args ...any) {
	defaultLogger.Debug(fmt.Sprintf(format, args...))
}

func Info(msg string, args ...any) {
	defaultLogger.Info(msg, args...)
}

func Infof(format string, args ...any) {
	defaultLogger.Info(fmt.Sprintf(format, args...))
}

func Warn(msg string, args ...any) {
	defaultLogger.Warn(msg, args...)
}

func Warnf(format string, args ...any) {
	defaultLogger.Warn(fmt.Sprintf(format, args...))
}

func Error(msg string, args ...any) {
	defaultLogger.Error(msg, args...)
}

func Errorf(format string, args ...any) {
	defaultLogger.Error(fmt.Sprintf(format, args...))
}

func Fatal(msg string, args ...any) {
	defaultLogger.Error(msg, args...)
	os.Exit(1)
}

func Fatalf(format string, args ...any) {
	defaultLogger.Error(fmt.Sprintf(format, args...))
	os.Exit(1)
}
