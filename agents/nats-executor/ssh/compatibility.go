package ssh

import (
	"strings"

	"golang.org/x/crypto/ssh"
)

type sshCompatibilityProfile string

const (
	profileModern sshCompatibilityProfile = "modern"
	profileLegacy sshCompatibilityProfile = "legacy"
)

func shouldRetryWithLegacy(errorText string) bool {
	lowerText := strings.ToLower(errorText)
	legacyIndicators := []string{
		"invalid signature algorithm",
		"no matching host key type found",
		"no matching key exchange method found",
		"no matching cipher found",
		"no mutual signature algorithm",
		"unable to negotiate",
	}

	for _, indicator := range legacyIndicators {
		if strings.Contains(lowerText, indicator) {
			return true
		}
	}

	return false
}

func hostKeyAlgorithmsForProfile(profile sshCompatibilityProfile) []string {
	if profile == profileLegacy {
		return []string{ssh.KeyAlgoRSA, ssh.KeyAlgoRSASHA512, ssh.KeyAlgoRSASHA256, ssh.KeyAlgoED25519, ssh.KeyAlgoECDSA256, ssh.KeyAlgoECDSA384, ssh.KeyAlgoECDSA521}
	}

	return []string{ssh.KeyAlgoED25519, ssh.KeyAlgoECDSA256, ssh.KeyAlgoECDSA384, ssh.KeyAlgoECDSA521, ssh.KeyAlgoRSASHA512, ssh.KeyAlgoRSASHA256, ssh.KeyAlgoRSA}
}

func rsaSignerAlgorithmsForProfile(profile sshCompatibilityProfile) []string {
	if profile == profileLegacy {
		return []string{ssh.KeyAlgoRSA, ssh.KeyAlgoRSASHA256, ssh.KeyAlgoRSASHA512}
	}

	return []string{ssh.KeyAlgoRSASHA512, ssh.KeyAlgoRSASHA256}
}

func scpOptionFlags(profile sshCompatibilityProfile) string {
	if profile == profileLegacy {
		return "-o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa"
	}

	return "-o StrictHostKeyChecking=no"
}
