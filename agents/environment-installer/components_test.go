package main

import "testing"

func TestRequiredComponentHealthUsesSignedSelection(t *testing.T) {
	required := []RequiredComponent{{ID: "telegraf", Name: "Telegraf"}}
	for _, test := range []struct {
		name     string
		reported []ComponentHealth
		healthy  bool
	}{
		{"healthy", []ComponentHealth{{ID: "telegraf", Status: "healthy"}}, true},
		{"missing", nil, false},
		{"failed", []ComponentHealth{{ID: "telegraf", Status: "unhealthy"}}, false},
		{"different component", []ComponentHealth{{ID: "other", Status: "healthy"}}, false},
		{"duplicate report", []ComponentHealth{{ID: "telegraf", Status: "healthy"}, {ID: "telegraf", Status: "healthy"}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if requiredComponentsHealthy(required, test.reported) != test.healthy {
				t.Fatal("incorrect required component health")
			}
		})
	}
	if !requiredComponentsHealthy(nil, nil) {
		t.Fatal("controller-only package requires no collectors")
	}
}
