package ssh

import (
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"fmt"
	"net"
	"strings"
	"testing"
	"time"

	gossh "golang.org/x/crypto/ssh"
)

func TestExecuteAuthenticatesPasswordThroughKeyboardInteractive(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, _, serverDone := startKeyboardInteractiveSSHServer(
		t,
		"secret",
		[]keyboardInteractiveRound{{
			questions: []string{"Password:"},
			echos:     []bool{false},
		}},
	)

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "secret",
	}, "instance-keyboard-interactive")

	if !response.Success {
		t.Fatalf("expected keyboard-interactive authentication to succeed, got %+v", response)
	}

	select {
	case err := <-serverDone:
		if err != nil {
			t.Fatalf("keyboard-interactive SSH server failed: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("keyboard-interactive SSH server did not finish")
	}
}

func TestExecuteKeepsPasswordAuthentication(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, serverDone := startPasswordSSHServer(t, "secret")

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "secret",
	}, "instance-password")

	if !response.Success {
		t.Fatalf("expected password authentication to remain supported, got %+v", response)
	}

	select {
	case err := <-serverDone:
		if err != nil {
			t.Fatalf("password SSH server failed: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("password SSH server did not finish")
	}
}

func TestExecuteRejectsWrongKeyboardInteractivePassword(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, _, _ := startKeyboardInteractiveSSHServer(
		t,
		"secret",
		[]keyboardInteractiveRound{{
			questions: []string{"Password:"},
			echos:     []bool{false},
		}},
	)

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "wrong-password",
	}, "instance-wrong-password")

	if response.Success {
		t.Fatalf("expected keyboard-interactive authentication with a wrong password to fail, got %+v", response)
	}
	if response.Category != sshCategoryAuth {
		t.Fatalf("expected an authentication failure category, got %+v", response)
	}
}

func TestExecuteLegacyRetryAuthenticatesPasswordThroughKeyboardInteractive(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, _, serverDone := startKeyboardInteractiveSSHServer(
		t,
		"secret",
		[]keyboardInteractiveRound{{
			questions: []string{"Password:"},
			echos:     []bool{false},
		}},
	)

	originalDial := sshDialFn
	dialAttempts := 0
	sshDialFn = func(network, address string, config *gossh.ClientConfig) (sshClient, error) {
		dialAttempts++
		if dialAttempts == 1 {
			return nil, errors.New("no matching host key type found")
		}
		client, err := gossh.Dial(network, address, config)
		if err != nil {
			return nil, err
		}
		return realSSHClient{client: client}, nil
	}
	t.Cleanup(func() { sshDialFn = originalDial })

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "secret",
	}, "instance-keyboard-interactive-legacy")

	if !response.Success {
		t.Fatalf("expected legacy retry keyboard-interactive authentication to succeed, got %+v", response)
	}
	if dialAttempts != 2 {
		t.Fatalf("expected modern and legacy dial attempts, got %d", dialAttempts)
	}

	select {
	case err := <-serverDone:
		if err != nil {
			t.Fatalf("legacy keyboard-interactive SSH server failed: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("legacy keyboard-interactive SSH server did not finish")
	}
}

func TestExecuteRejectsMultiPromptKeyboardInteractiveChallenge(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, observedAnswers, _ := startKeyboardInteractiveSSHServer(
		t,
		"secret",
		[]keyboardInteractiveRound{{
			questions: []string{"Password:", "Verification code:"},
			echos:     []bool{false, false},
		}},
	)

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "secret",
	}, "instance-multi-prompt")

	if response.Success {
		t.Fatalf("expected a multi-prompt keyboard-interactive challenge to be rejected, got %+v", response)
	}
	if !strings.Contains(response.Error, "unsupported keyboard-interactive challenge") {
		t.Fatalf("expected an explicit unsupported challenge error, got %+v", response)
	}
	if response.Category != sshCategoryAuth {
		t.Fatalf("expected an authentication failure category, got %+v", response)
	}

	select {
	case answersByRound := <-observedAnswers:
		if len(answersByRound) != 1 || len(answersByRound[0]) != 0 {
			t.Fatalf("expected no credential answers for a multi-prompt challenge, got %v", answersByRound)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("keyboard-interactive SSH server did not observe the rejected challenge")
	}
}

func TestExecuteRejectsAdditionalKeyboardInteractivePromptRound(t *testing.T) {
	t.Setenv(sshKnownHostsFileEnv, "")
	host, port, observedAnswers, _ := startKeyboardInteractiveSSHServer(
		t,
		"secret",
		[]keyboardInteractiveRound{
			{questions: []string{"Password:"}, echos: []bool{false}},
			{questions: []string{"Verification code:"}, echos: []bool{false}},
		},
	)

	response := Execute(ExecuteRequest{
		Command:        "true",
		ExecuteTimeout: 5,
		Host:           host,
		Port:           port,
		User:           "root",
		Password:       "secret",
	}, "instance-additional-prompt")

	if response.Success {
		t.Fatalf("expected an additional keyboard-interactive prompt round to be rejected, got %+v", response)
	}
	if !strings.Contains(response.Error, "unsupported keyboard-interactive challenge") {
		t.Fatalf("expected an explicit unsupported challenge error, got %+v", response)
	}
	if response.Category != sshCategoryAuth {
		t.Fatalf("expected an authentication failure category, got %+v", response)
	}

	select {
	case answersByRound := <-observedAnswers:
		if len(answersByRound) != 2 || len(answersByRound[1]) != 0 {
			t.Fatalf("expected no credential answer for the additional prompt round, got %v", answersByRound)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("keyboard-interactive SSH server did not observe the rejected prompt round")
	}
}

type keyboardInteractiveRound struct {
	questions []string
	echos     []bool
}

func startPasswordSSHServer(t *testing.T, password string) (string, uint, <-chan error) {
	t.Helper()
	serverConfig := &gossh.ServerConfig{
		PasswordCallback: func(_ gossh.ConnMetadata, candidate []byte) (*gossh.Permissions, error) {
			if string(candidate) != password {
				return nil, errors.New("invalid password")
			}
			return nil, nil
		},
	}
	return startSSHTestServer(t, serverConfig)
}

func startKeyboardInteractiveSSHServer(
	t *testing.T,
	password string,
	rounds []keyboardInteractiveRound,
) (string, uint, <-chan [][]string, <-chan error) {
	t.Helper()

	observedAnswers := make(chan [][]string, 1)
	serverConfig := &gossh.ServerConfig{
		KeyboardInteractiveCallback: func(_ gossh.ConnMetadata, challenge gossh.KeyboardInteractiveChallenge) (*gossh.Permissions, error) {
			answersByRound := make([][]string, 0, len(rounds))
			for _, round := range rounds {
				answers, err := challenge("", "", round.questions, round.echos)
				answersByRound = append(answersByRound, answers)
				if err != nil {
					observedAnswers <- answersByRound
					return nil, err
				}
			}
			observedAnswers <- answersByRound
			if len(answersByRound) != 1 || len(answersByRound[0]) != 1 || answersByRound[0][0] != password {
				return nil, errors.New("invalid keyboard-interactive password")
			}
			return nil, nil
		},
	}
	host, port, done := startSSHTestServer(t, serverConfig)
	return host, port, observedAnswers, done
}

func startSSHTestServer(t *testing.T, serverConfig *gossh.ServerConfig) (string, uint, <-chan error) {
	t.Helper()

	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate SSH host key: %v", err)
	}
	hostSigner, err := gossh.NewSignerFromSigner(privateKey)
	if err != nil {
		t.Fatalf("create SSH host signer: %v", err)
	}
	serverConfig.AddHostKey(hostSigner)

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen for SSH test server: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })

	done := make(chan error, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			done <- fmt.Errorf("accept SSH connection: %w", err)
			return
		}
		defer conn.Close()

		serverConn, channels, requests, err := gossh.NewServerConn(conn, serverConfig)
		if err != nil {
			done <- fmt.Errorf("complete SSH handshake: %w", err)
			return
		}
		defer serverConn.Close()
		go gossh.DiscardRequests(requests)

		for newChannel := range channels {
			if newChannel.ChannelType() != "session" {
				_ = newChannel.Reject(gossh.UnknownChannelType, "unsupported channel type")
				continue
			}

			channel, channelRequests, err := newChannel.Accept()
			if err != nil {
				done <- fmt.Errorf("accept SSH session channel: %w", err)
				return
			}

			for request := range channelRequests {
				if request.Type != "exec" {
					_ = request.Reply(false, nil)
					continue
				}

				_ = request.Reply(true, nil)
				_, _ = channel.SendRequest("exit-status", false, gossh.Marshal(struct{ Status uint32 }{Status: 0}))
				_ = channel.Close()
			}
		}
		done <- nil
	}()

	address := listener.Addr().(*net.TCPAddr)
	return address.IP.String(), uint(address.Port), done
}
