package main

import (
	"archive/zip"
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestBundleRejectsTamperedInstaller(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	trustedSigningKey = base64.StdEncoding.EncodeToString(pub)
	installer := []byte("official-installer")
	digest := sha256.Sum256(installer)
	manifest, _ := json.Marshal(Manifest{Schema: 1, InstallerSHA256: hex.EncodeToString(digest[:])})
	for _, corrupt := range []string{"none", "installer", "manifest"} {
		var data bytes.Buffer
		archive := zip.NewWriter(&data)
		files := map[string][]byte{"manifest.json": manifest, "manifest.sig": ed25519.Sign(priv, manifest), "installer": installer}
		if corrupt == "installer" {
			files["installer"] = []byte("tampered")
		}
		if corrupt == "manifest" {
			files["manifest.json"] = append(append([]byte{}, manifest...), byte(' '))
		}
		for name, content := range files {
			f, _ := archive.Create(name)
			_, _ = f.Write(content)
		}
		_ = archive.Close()
		file := filepath.Join(t.TempDir(), "entry")
		_ = os.WriteFile(file, data.Bytes(), 0600)
		_, _, err := loadBundle(file)
		if (err != nil) != (corrupt != "none") {
			t.Fatalf("tampered=%v, error=%v", corrupt, err)
		}
	}
}

func TestStatePersistsIdentityAndRejectsOtherEnvironment(t *testing.T) {
	dir := t.TempDir()
	first, err := loadOrCreateState(dir, "grant-a", "machine-a", "192.0.2.10", "host-a")
	if err != nil {
		t.Fatal(err)
	}
	again, err := loadOrCreateState(dir, "grant-a", "machine-a", "192.0.2.99", "renamed")
	if err != nil {
		t.Fatal(err)
	}
	if first.NodeID != again.NodeID || first.RequestID != again.RequestID || again.IP != "192.0.2.10" {
		t.Fatal("retry changed identity")
	}
	if _, err = loadOrCreateState(dir, "grant-b", "machine-a", "192.0.2.10", "host-a"); err == nil {
		t.Fatal("accepted another grant")
	}
	if _, err = loadOrCreateState(dir, "grant-a", "machine-b", "192.0.2.10", "host-a"); err == nil {
		t.Fatal("accepted cloned identity")
	}
	info, _ := os.Stat(filepath.Join(dir, "state.json"))
	if info.Mode().Perm() != 0600 {
		t.Fatal("state must be private")
	}
}
