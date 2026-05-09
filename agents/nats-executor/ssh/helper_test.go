package ssh

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	gossh "golang.org/x/crypto/ssh"
	"nats-executor/utils"
)

type rsaSignerWithoutAlgorithmSupport struct {
	delegate gossh.Signer
}

func (s rsaSignerWithoutAlgorithmSupport) PublicKey() gossh.PublicKey {
	return s.delegate.PublicKey()
}

func (s rsaSignerWithoutAlgorithmSupport) Sign(rand io.Reader, data []byte) (*gossh.Signature, error) {
	return s.delegate.Sign(rand, data)
}

func TestSSHTransferHelpers(t *testing.T) {
	sourceFile := filepath.Join(t.TempDir(), "artifact.txt")
	if err := os.WriteFile(sourceFile, []byte(strings.Repeat("x", 2048)), 0o600); err != nil {
		t.Fatalf("failed to write source file: %v", err)
	}

	t.Run("describes file transfer context", func(t *testing.T) {
		meta := describeTransferSource(sourceFile)
		if meta.Kind != "file" || meta.BaseName != "artifact.txt" {
			t.Fatalf("unexpected source meta: %+v", meta)
		}

		logContext := buildTransferLogContext("upload", "10.0.0.1", 22, "root", sourceFile, "/tmp/remote", transferAuthMethod("secret", ""), meta)
		for _, want := range []string{"upload", "root@10.0.0.1:22", "auth=password", "kind=file", "artifact.txt"} {
			if !strings.Contains(logContext, want) {
				t.Fatalf("expected log context to contain %q, got %q", want, logContext)
			}
		}
	})

	t.Run("missing source becomes inaccessible", func(t *testing.T) {
		meta := describeTransferSource(filepath.Join(t.TempDir(), "missing.txt"))
		if meta.Kind != "missing_or_inaccessible" {
			t.Fatalf("unexpected source meta: %+v", meta)
		}
	})

	t.Run("directory source reports dir kind", func(t *testing.T) {
		meta := describeTransferSource(t.TempDir())
		if meta.Kind != "dir" {
			t.Fatalf("unexpected source meta: %+v", meta)
		}
	})

	t.Run("human readable size and auth fallbacks", func(t *testing.T) {
		if got := humanReadableSize(1536); got != "1.5KB" {
			t.Fatalf("unexpected size formatting: %q", got)
		}
		if got := humanReadableSize(-1); got != "unknown" {
			t.Fatalf("unexpected unknown size formatting: %q", got)
		}
		if got := transferAuthMethod("", "private"); got != "private_key" {
			t.Fatalf("unexpected auth method: %q", got)
		}
		if got := transferAuthMethod("", ""); got != "unknown" {
			t.Fatalf("unexpected auth method fallback: %q", got)
		}
	})

	t.Run("truncates multiline transfer output", func(t *testing.T) {
		output := truncateTransferOutput(strings.Repeat("line\n", 80))
		if !strings.Contains(output, " | ") || !strings.HasSuffix(output, "...") {
			t.Fatalf("unexpected truncated output: %q", output)
		}
	})
}

func TestTimeoutAndDurationHelpers(t *testing.T) {
	resp := timeoutResponse("instance-1", "partial", "timed out")
	if resp.Code != utils.ErrorCodeTimeout || resp.Category != sshCategoryRemoteTimeout || resp.Stage != "" {
		t.Fatalf("unexpected timeout response: %+v", resp)
	}
	if got := minDuration(2*time.Second, 5*time.Second); got != 2*time.Second {
		t.Fatalf("unexpected min duration: %v", got)
	}
}

func TestBuildPublicKeyAuthMethodSupportsRSAAndNonRSAKeys(t *testing.T) {
	_, edPrivate, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate ed25519 key: %v", err)
	}
	edSigner, err := gossh.NewSignerFromSigner(edPrivate)
	if err != nil {
		t.Fatalf("failed to create ed25519 signer: %v", err)
	}
	if auth := buildPublicKeyAuthMethod(edSigner, profileModern); auth == nil {
		t.Fatal("expected auth method for ed25519 signer")
	}

	rsaPrivate, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("failed to generate rsa key: %v", err)
	}
	rsaSigner, err := gossh.NewSignerFromSigner(rsaPrivate)
	if err != nil {
		t.Fatalf("failed to create rsa signer: %v", err)
	}
	if auth := buildPublicKeyAuthMethod(rsaSigner, profileLegacy); auth == nil {
		t.Fatal("expected auth method for rsa signer")
	}
	if auth := buildPublicKeyAuthMethod(rsaSignerWithoutAlgorithmSupport{delegate: rsaSigner}, profileModern); auth == nil {
		t.Fatal("expected fallback auth method for rsa signer without algorithm support")
	}
}

func TestSSHHelperPredicatesAndTimeoutBudgets(t *testing.T) {
	if got := tcpProbeTimeout(500 * time.Millisecond); got != 500*time.Millisecond {
		t.Fatalf("unexpected short timeout probe budget: %v", got)
	}
	if got := tcpProbeTimeout(50 * time.Second); got != 5*time.Second {
		t.Fatalf("unexpected capped probe timeout: %v", got)
	}

	if !isLikelyAuthError(errors.New("ssh: unable to authenticate")) || isLikelyAuthError(nil) {
		t.Fatal("unexpected auth error classification")
	}
	if !isLikelyTimeoutError(errors.New("deadline exceeded")) || isLikelyTimeoutError(nil) {
		t.Fatal("unexpected timeout error classification")
	}
	if !isLikelyNetworkError(errors.New("connection refused")) || isLikelyNetworkError(errors.New("permission denied")) {
		t.Fatal("unexpected network error classification")
	}
	if !isLikelyNetworkError(errors.New("lookup example.internal: no such host")) {
		t.Fatal("expected DNS lookup failures to be treated as network errors")
	}

	if got := validateTransferTimeout(0); got == "" {
		t.Fatal("expected invalid timeout message")
	}
	if got := remainingBudgetSeconds(time.Now().Add(-time.Second)); got != 0 {
		t.Fatalf("expected exhausted budget to clamp to 0 seconds, got %d", got)
	}
	if got := localTimeoutResponse("instance-1", "timed out"); got.Code != utils.ErrorCodeTimeout {
		t.Fatalf("unexpected local timeout response: %+v", got)
	}

	msg := natsInboundMsg{Msg: &nats.Msg{Data: []byte("payload")}}
	if got := string(msg.Payload()); got != "payload" {
		t.Fatalf("unexpected payload: %q", got)
	}
}

func TestDecodeIncomingMessageRejectsMalformedPayloads(t *testing.T) {
	if msg, ok := decodeIncomingMessage([]byte(`{"kwargs":{}}`)); ok || msg != nil {
		t.Fatalf("expected missing args payload to be rejected, got ok=%v msg=%+v", ok, msg)
	}
	if msg, ok := decodeIncomingMessage([]byte(`{"args":[`)); ok || msg != nil {
		t.Fatalf("expected malformed json payload to be rejected, got ok=%v msg=%+v", ok, msg)
	}
}
