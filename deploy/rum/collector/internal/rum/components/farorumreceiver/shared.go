package farorumreceiver

import (
	"context"
	"sync"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/receiver"
)

type sharedRegistry struct {
	mu        sync.Mutex
	receivers map[*Config]*sharedReceiver
}

func newSharedRegistry() *sharedRegistry {
	return &sharedRegistry{receivers: make(map[*Config]*sharedReceiver)}
}

func (registry *sharedRegistry) getOrAdd(cfg *Config, settings receiver.Settings) (*sharedReceiver, error) {
	registry.mu.Lock()
	defer registry.mu.Unlock()
	if existing, ok := registry.receivers[cfg]; ok {
		return existing, nil
	}
	receiver, err := newFaroReceiver(cfg, &settings)
	if err != nil {
		return nil, err
	}
	shared := &sharedReceiver{receiver: receiver}
	shared.remove = func() {
		registry.mu.Lock()
		defer registry.mu.Unlock()
		if registry.receivers[cfg] == shared {
			delete(registry.receivers, cfg)
		}
	}
	registry.receivers[cfg] = shared
	return shared, nil
}

type sharedReceiver struct {
	receiver *faroReceiver
	remove   func()

	startOnce sync.Once
	startErr  error
	stopOnce  sync.Once
	stopErr   error
}

func (shared *sharedReceiver) Start(ctx context.Context, host component.Host) error {
	shared.startOnce.Do(func() {
		shared.startErr = shared.receiver.Start(ctx, host)
	})
	return shared.startErr
}

func (shared *sharedReceiver) Shutdown(ctx context.Context) error {
	shared.stopOnce.Do(func() {
		shared.stopErr = shared.receiver.Shutdown(ctx)
		shared.remove()
	})
	return shared.stopErr
}
