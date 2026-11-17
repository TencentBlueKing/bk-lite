package main

import (
	"bufio"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"strings"
	"testing"
	"time"
)

// A local NATS wire peer exercises the real client TLS handshake. It does not
// stand in for object-store authorization or full controller installation.
func environmentNATSCertificate(t *testing.T, validSAN bool) (tls.Certificate, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ca := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "environment-test-ca"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	caDER, err := x509.CreateCertificate(rand.Reader, ca, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	leaf := &x509.Certificate{SerialNumber: big.NewInt(2), NotBefore: ca.NotBefore, NotAfter: ca.NotAfter, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, DNSNames: []string{"different-host.invalid"}}
	if validSAN {
		leaf.IPAddresses = []net.IP{net.ParseIP("127.0.0.1")}
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leaf, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{leafDER, caDER}, PrivateKey: key}, string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}))
}

func TestEnvironmentNATSConnectionRequiresTrustedCAAndMatchingSAN(t *testing.T) {
	for _, scenario := range []struct {
		name              string
		validSAN, trusted bool
	}{
		{"trusted CA and matching IP", true, true},
		{"untrusted CA", true, false},
		{"mismatched SAN", false, true},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			certificate, ca := environmentNATSCertificate(t, scenario.validSAN)
			if !scenario.trusted {
				_, ca = environmentNATSCertificate(t, true)
			}
			listener, err := net.Listen("tcp4", "127.0.0.1:0")
			if err != nil {
				t.Fatal(err)
			}
			defer listener.Close()
			done := make(chan struct{})
			go func() {
				defer close(done)
				raw, err := listener.Accept()
				if err != nil {
					return
				}
				defer raw.Close()
				_ = raw.SetDeadline(time.Now().Add(5 * time.Second))
				_, err = fmt.Fprint(raw, "INFO {\"server_id\":\"environment-test\",\"version\":\"2.10.0\",\"proto\":1,\"tls_required\":true,\"max_payload\":1048576}\r\n")
				if err != nil {
					return
				}
				secure := tls.Server(raw, &tls.Config{Certificates: []tls.Certificate{certificate}, MinVersion: tls.VersionTLS12})
				if secure.Handshake() != nil {
					return
				}
				scanner := bufio.NewScanner(secure)
				for scanner.Scan() {
					if strings.TrimSpace(scanner.Text()) == "PING" {
						_, _ = fmt.Fprint(secure, "PONG\r\n")
					}
				}
			}()
			oldSkip := *skipTLS
			*skipTLS = false
			defer func() { *skipTLS = oldSkip }()
			conn, err := connectNATS(&StorageConfig{NATSProtocol: "tls", NATSServers: listener.Addr().String(), NATSTLSCA: ca})
			if conn != nil {
				conn.Close()
			}
			if scenario.trusted && scenario.validSAN {
				if err != nil {
					t.Fatalf("valid TLS connection rejected: %v", err)
				}
			} else if err == nil {
				t.Fatal("untrusted or mismatched certificate accepted")
			}
			_ = listener.Close()
			select {
			case <-done:
			case <-time.After(6 * time.Second):
				t.Fatal("test peer failed to terminate")
			}
		})
	}
}
