package local

import (
	"context"
	"fmt"
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

func (s *localSCPBDDState) shellIs(shell string) {
	s.req.Shell = shell
}

func (s *localSCPBDDState) scpCommandIs(command string) {
	s.req.Command = command
}

func (s *localSCPBDDState) transferLogContextIs(logContext string) {
	s.req.LogContext = logContext
}

func (s *localSCPBDDState) executeTimeoutIs(seconds int) {
	s.req.ExecuteTimeout = seconds
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

	sc.Step(`^a local SCP executor instance$`, state.aLocalSCPExecutorInstance)
	sc.Step(`^shell is "([^"]*)"$`, state.shellIs)
	sc.Step(`^scp command is "([^"]*)"$`, state.scpCommandIs)
	sc.Step(`^transfer log context is "([^"]*)"$`, state.transferLogContextIs)
	sc.Step(`^execute timeout is (\d+) seconds$`, state.executeTimeoutIs)
	sc.Step(`^the command is executed locally$`, state.theCommandIsExecutedLocally)
	sc.Step(`^the execution succeeds$`, state.theExecutionSucceeds)
	sc.Step(`^the execution fails with code "([^"]*)"$`, state.theExecutionFailsWithCode)
	sc.Step(`^combined output contains "([^"]*)"$`, state.combinedOutputContains)
	sc.Step(`^error contains "([^"]*)"$`, state.errorContains)
}

func TestLocalSCPBDDUserScenarios(t *testing.T) {
	t.Helper()

	suite := godog.TestSuite{
		Name:                "local-scp-bdd",
		ScenarioInitializer: InitializeLocalSCPScenario,
		Options: &godog.Options{
			Format:   "pretty",
			Paths:    []string{"features/local_scp.feature"},
			TestingT: t,
		},
	}

	if status := suite.Run(); status != 0 {
		t.Fatalf("godog suite failed with status %d", status)
	}
}
