package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// APIError carries only a bounded local message, never a response body.
type APIError struct {
	Code    int
	Message string
}

func (e *APIError) Error() string { return e.Message }
func operationFailureCode(err error) int {
	var apiError *APIError
	if errors.As(err, &apiError) {
		return apiError.Code
	}
	return 30
}

type APIClient struct {
	manifest Manifest
	http     *http.Client
}
type InstallResult struct {
	Components     []ComponentHealth `json:"components"`
	InstallID      string            `json:"install_id"`
	NodeID         string            `json:"node_id"`
	Status         string            `json:"status"`
	ConfigURL      string            `json:"config_url"`
	PackageSHA256  string            `json:"package_sha256"`
	PackageVersion string            `json:"package_version"`
	LastSeen       string            `json:"last_seen"`
}

func validatePlatformURL(raw string) error {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return errors.New("platform requires an HTTPS origin")
	}
	return nil
}

func newAPIClient(manifest Manifest) (*APIClient, error) {
	if err := validatePlatformURL(manifest.PlatformURL); err != nil {
		return nil, err
	}
	pool, err := x509.SystemCertPool()
	if err != nil {
		pool = x509.NewCertPool()
	}
	if manifest.PlatformCA != "" && !pool.AppendCertsFromPEM([]byte(manifest.PlatformCA)) {
		return nil, errors.New("invalid platform CA")
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	client := &http.Client{Timeout: 30 * time.Second, Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect forbidden") }}
	return &APIClient{manifest: manifest, http: client}, nil
}

func (client *APIClient) call(ctx context.Context, endpoint string, input map[string]any) (InstallResult, error) {
	var result InstallResult
	// Do not accept arbitrary destinations or print transport/server errors: they can contain secrets.
	if endpoint != "environment-install" && endpoint != "environment-install-status" {
		return result, errors.New("invalid operation")
	}
	input["grant_id"] = client.manifest.GrantID
	input["installation_key"] = client.manifest.InstallationKey
	body, err := json.Marshal(input)
	if err != nil {
		return result, errors.New("invalid request")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(client.manifest.PlatformURL, "/")+"/openapi/v1/node-mgmt/"+endpoint, bytes.NewReader(body))
	if err != nil {
		return result, errors.New("invalid request")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+client.manifest.InstallationKey)
	request.Header.Set("X-BKLite-Acting-User", client.manifest.ActingUser)
	request.Header.Set("X-BKLite-Acting-Team", strconv.Itoa(client.manifest.Team))
	response, err := client.http.Do(request)
	if err != nil {
		return result, errors.New("platform connection or TLS verification failed")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		code := 20
		if response.StatusCode == 429 || response.StatusCode >= 500 {
			code = 30
		}
		return result, &APIError{Code: code, Message: fmt.Sprintf("platform rejected operation (HTTP %d)", response.StatusCode)}
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 256*1024+1))
	if err != nil || len(raw) > 256*1024 {
		return result, errors.New("invalid platform response")
	}
	var envelope struct {
		Result bool          `json:"result"`
		Data   InstallResult `json:"data"`
	}
	if json.Unmarshal(raw, &envelope) != nil || !envelope.Result {
		return result, &APIError{Code: 20, Message: "platform rejected installation authorization or request; check grant, quota and identity"}
	}
	return envelope.Data, nil
}
