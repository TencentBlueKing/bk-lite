package main

import (
	"context"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAPITrustsConfiguredCAAndRejectsRedirects(t *testing.T) {
	redirect := false
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer secret-sentinel" {
			t.Error("missing installation authorization")
		}
		if redirect {
			http.Redirect(w, r, "https://example.invalid/secret-sentinel", http.StatusFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"result":true,"data":{"install_id":"install-a","status":"pending"}}`))
	}))
	defer server.Close()
	manifest := Manifest{PlatformURL: server.URL, PlatformCA: string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw})), InstallationKey: "secret-sentinel", ActingUser: "installer@test", Team: 1}
	client, err := newAPIClient(manifest)
	if err != nil {
		t.Fatal(err)
	}
	result, err := client.call(context.Background(), "environment-install", map[string]any{})
	if err != nil || result.InstallID != "install-a" {
		t.Fatalf("result=%+v err=%v", result, err)
	}
	redirect = true
	_, err = client.call(context.Background(), "environment-install", map[string]any{})
	if err == nil || strings.Contains(err.Error(), "secret-sentinel") {
		t.Fatal("redirect accepted or secret disclosed")
	}
	manifest.PlatformCA = ""
	client, err = newAPIClient(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = client.call(context.Background(), "environment-install", map[string]any{}); err == nil {
		t.Fatal("untrusted TLS accepted")
	}
}

func TestAPIRejectionsAreNotRetryableTransportFailures(t *testing.T) {
	for _, test := range []struct {
		status int
		body   string
		code   int
	}{
		{401, `secret-sentinel`, 20}, {403, `secret-sentinel`, 20},
		{200, `{"result":false,"message":"secret-sentinel"}`, 20},
		{429, `secret-sentinel`, 30}, {503, `secret-sentinel`, 30},
	} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(test.status); w.Write([]byte(test.body)) }))
		client := &APIClient{manifest: Manifest{PlatformURL: server.URL}, http: server.Client()}
		_, err := client.call(context.Background(), "environment-install", map[string]any{})
		server.Close()
		if err == nil || operationFailureCode(err) != test.code || strings.Contains(err.Error(), "secret-sentinel") {
			t.Fatalf("status %d: unsafe or wrongly classified error: %v", test.status, err)
		}
	}
}
