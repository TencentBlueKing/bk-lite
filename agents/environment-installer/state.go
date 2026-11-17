package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

type State struct {
	GrantID   string `json:"grant_id"`
	Machine   string `json:"machine"`
	NodeID    string `json:"node_id"`
	RequestID string `json:"request_id"`
	IP        string `json:"ip"`
	NodeName  string `json:"node_name"`
	InstallID string `json:"install_id,omitempty"`
	Phase     string `json:"phase"`
}

func randomUUID() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b)
	return h[:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:], nil
}

func loadOrCreateState(dir, grant, machine, ip, hostname string) (State, error) {
	var state State
	path := filepath.Join(dir, "state.json")
	raw, err := os.ReadFile(path)
	if err == nil {
		if json.Unmarshal(raw, &state) != nil || state.NodeID == "" || state.RequestID == "" {
			return state, errors.New("invalid installation state")
		}
		if state.GrantID != grant || state.Machine != machine {
			return state, errors.New("installation identity conflict")
		}
		return state, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return state, err
	}
	node, err := randomUUID()
	if err != nil {
		return state, err
	}
	request, err := randomUUID()
	if err != nil {
		return state, err
	}
	state = State{GrantID: grant, Machine: machine, NodeID: node, RequestID: request, IP: ip, NodeName: hostname, Phase: "reserved"}
	return state, saveState(dir, state)
}

func saveState(dir string, state State) error {
	content, err := json.Marshal(state)
	if err != nil {
		return err
	}
	file, err := os.CreateTemp(dir, ".state-")
	if err != nil {
		return err
	}
	path := file.Name()
	defer os.Remove(path)
	if _, err = file.Write(content); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(path, filepath.Join(dir, "state.json")); err != nil {
		return err
	}
	directory, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}
