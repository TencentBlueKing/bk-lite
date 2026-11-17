//go:build linux

package main

import (
	"net"
	"testing"
)

func TestSessionIsRestrictedToSignedPlatformOrigin(t *testing.T) {
	valid := "https://platform.example/api/v1/node_mgmt/open_api/installer/session?token=private"
	if err := sameSessionOrigin("https://platform.example", valid); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []string{
		"http://platform.example/api/v1/node_mgmt/open_api/installer/session?token=private",
		"https://other.example/api/v1/node_mgmt/open_api/installer/session?token=private",
		"https://user@platform.example/api/v1/node_mgmt/open_api/installer/session?token=private",
		"https://platform.example/other?token=private",
		"https://platform.example/api/v1/node_mgmt/open_api/installer/session",
	} {
		if sameSessionOrigin("https://platform.example", invalid) == nil {
			t.Fatal("unsafe session accepted")
		}
	}
}

func TestManagementCIDRMustSelectUniqueNonLoopbackIPv4(t *testing.T) {
	for _, cidr := range []string{"not-a-network", "127.0.0.0/8", "192.0.2.0/24"} {
		if _, err := managementIP(Manifest{ManagementCIDR: cidr}); err == nil {
			t.Fatalf("accepted unusable network %s", cidr)
		}
	}
}

func TestRoutePolicyRejectsDifferentManagementAddresses(t *testing.T) {
	remotes := []net.IP{net.ParseIP("192.0.2.10"), net.ParseIP("192.0.2.11")}
	_, err := routeManagementIP(remotes, func(remote net.IP) (net.IP, error) {
		if remote.Equal(remotes[0]) {
			return net.ParseIP("10.0.0.1"), nil
		}
		return net.ParseIP("10.1.0.1"), nil
	})
	if err == nil {
		t.Fatal("ambiguous platform routes must require a management network")
	}
	ip, err := routeManagementIP(remotes, func(net.IP) (net.IP, error) { return net.ParseIP("10.0.0.1"), nil })
	if err != nil || ip != "10.0.0.1" {
		t.Fatal("same management address should be accepted")
	}
}

func TestRegisteredInactiveControllerRequiresExplicitRecovery(t *testing.T) {
	err := registeredControllerState("registered", false)
	typed, ok := err.(*failure)
	if !ok || typed.code != 60 || typed.stage != "preflight" {
		t.Fatalf("expected non-retryable recovery failure: %v", err)
	}
	if registeredControllerState("registered", true) != nil {
		t.Fatal("healthy repeat was rejected")
	}
	if registeredControllerState("pending", false) != nil {
		t.Fatal("fresh installation was rejected")
	}
}
