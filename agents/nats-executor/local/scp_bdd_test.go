package local

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"testing"

	"github.com/cucumber/godog"
)

type localSCPBDDState struct {
	req        ExecuteRequest
	resp       ExecuteResponse
	instanceID string
}

func (s *localSCPBDDState) reset() {
	s.req = ExecuteRequest{
		Shell: ShellTypeSh,
	}
	s.resp = ExecuteResponse{}
	s.instanceID = "instance-bdd"
}

func (s *localSCPBDDState) aLocalSCPExecutorInstance() {
	s.instanceID = "instance-bdd"
}

func (s *localSCPBDDState) theExecuteRequestIs(table *godog.Table) error {
	for rowIndex, row := range table.Rows {
		if rowIndex == 0 {
			continue
		}
		if len(row.Cells) != 2 {
			return fmt.Errorf("expected 2 cells per row, got %d", len(row.Cells))
		}

		field := strings.TrimSpace(row.Cells[0].Value)
		value := row.Cells[1].Value

		switch field {
		case "shell":
			s.req.Shell = value
		case "command":
			s.req.Command = value
		case "log_context":
			s.req.LogContext = value
		case "execute_timeout":
			seconds, err := strconv.Atoi(strings.TrimSpace(value))
			if err != nil {
				return fmt.Errorf("invalid execute_timeout %q: %w", value, err)
			}
			s.req.ExecuteTimeout = seconds
		default:
			return fmt.Errorf("unsupported request field %q", field)
		}
	}

	return nil
}

func (s *localSCPBDDState) theCommandIsExecutedLocally() {
	s.resp = Execute(s.req, s.instanceID)
}

func (s *localSCPBDDState) theExecutionSucceeds() error {
	if !s.resp.Success {
		return fmt.Errorf("expected success, got response=%+v", s.resp)
	}
	return nil
}

func (s *localSCPBDDState) theExecutionFailsWithCode(code string) error {
	if s.resp.Success {
		return fmt.Errorf("expected failure, got response=%+v", s.resp)
	}
	if s.resp.Code != code {
		return fmt.Errorf("expected code %q, got %q, response=%+v", code, s.resp.Code, s.resp)
	}
	return nil
}

func (s *localSCPBDDState) combinedOutputContains(want string) error {
	if !strings.Contains(s.resp.Output, want) {
		return fmt.Errorf("expected output to contain %q, got %q", want, s.resp.Output)
	}
	return nil
}

func (s *localSCPBDDState) errorContains(want string) error {
	if !strings.Contains(s.resp.Error, want) {
		return fmt.Errorf("expected error to contain %q, got %q", want, s.resp.Error)
	}
	return nil
}

func InitializeLocalSCPScenario(sc *godog.ScenarioContext) {
	state := &localSCPBDDState{}

	sc.Before(func(ctx context.Context, _ *godog.Scenario) (context.Context, error) {
		state.reset()
		return ctx, nil
	})

	sc.Step(`^存在一个本地 SCP 执行器实例$`, state.aLocalSCPExecutorInstance)
	sc.Step(`^执行请求为:$`, state.theExecuteRequestIs)
	sc.Step(`^在本地执行该命令$`, state.theCommandIsExecutedLocally)
	sc.Step(`^执行成功$`, state.theExecutionSucceeds)
	sc.Step(`^执行失败且错误码为 "([^"]*)"$`, state.theExecutionFailsWithCode)
	sc.Step(`^组合输出包含 "([^"]*)"$`, state.combinedOutputContains)
	sc.Step(`^错误信息包含 "([^"]*)"$`, state.errorContains)
}

func TestLocalSCPBDDUserScenarios(t *testing.T) {
	t.Helper()

	suite := godog.TestSuite{
		Name:                "local-scp-bdd",
		ScenarioInitializer: InitializeLocalSCPScenario,
		Options: &godog.Options{
			Format:   "pretty",
			Paths:    []string{"../features/local/scp.feature"},
			TestingT: t,
		},
	}

	if status := suite.Run(); status != 0 {
		t.Fatalf("godog suite failed with status %d", status)
	}
}
