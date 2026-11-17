package main

import (
	"archive/zip"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
)

// Injected at release build time. Never trust a public key supplied by a bundle.
var trustedSigningKey string

type Manifest struct {
	RequiredComponents []RequiredComponent `json:"required_components"`
	Schema             int                 `json:"schema"`
	GrantID            string              `json:"grant_id"`
	PlatformURL        string              `json:"platform_url"`
	InstallationKey    string              `json:"installation_key"`
	ActingUser         string              `json:"acting_user"`
	Team               int                 `json:"team"`
	CloudRegion        int                 `json:"cloud_region"`
	PackageVersion     string              `json:"package_version"`
	PackageSHA256      string              `json:"package_sha256"`
	InstallerSHA256    string              `json:"installer_sha256"`
	ExpiresAt          string              `json:"expires_at"`
	PlatformCA         string              `json:"platform_ca"`
	ManagementCIDR     string              `json:"management_cidr"`
	RequiredFreeBytes  uint64              `json:"required_free_bytes"`
	TimeoutSeconds     int                 `json:"timeout_seconds"`
}

func loadBundle(path string) (Manifest, []byte, error) {
	var manifest Manifest
	archive, err := zip.OpenReader(path)
	if err != nil {
		return manifest, nil, errors.New("invalid bundle archive")
	}
	defer archive.Close()
	limits := map[string]uint64{"manifest.json": 256 * 1024, "manifest.sig": ed25519.SignatureSize, "installer": 64 * 1024 * 1024}
	files := map[string][]byte{}
	for _, f := range archive.File {
		limit, allowed := limits[f.Name]
		if !allowed || files[f.Name] != nil || f.UncompressedSize64 > limit {
			return manifest, nil, errors.New("invalid bundle member")
		}
		reader, err := f.Open()
		if err != nil {
			return manifest, nil, errors.New("unreadable bundle member")
		}
		content, err := io.ReadAll(io.LimitReader(reader, int64(limit)+1))
		reader.Close()
		if err != nil || uint64(len(content)) > limit {
			return manifest, nil, errors.New("invalid bundle content")
		}
		files[f.Name] = content
	}
	publicKey, err := base64.StdEncoding.DecodeString(trustedSigningKey)
	if err != nil || len(publicKey) != ed25519.PublicKeySize || !ed25519.Verify(publicKey, files["manifest.json"], files["manifest.sig"]) {
		return manifest, nil, errors.New("bundle signature verification failed")
	}
	if err := json.Unmarshal(files["manifest.json"], &manifest); err != nil || manifest.Schema != 1 {
		return manifest, nil, errors.New("unsupported manifest")
	}
	digest := sha256.Sum256(files["installer"])
	if len(files["installer"]) == 0 || hex.EncodeToString(digest[:]) != manifest.InstallerSHA256 {
		return manifest, nil, errors.New("installer digest mismatch")
	}
	return manifest, files["installer"], nil
}
