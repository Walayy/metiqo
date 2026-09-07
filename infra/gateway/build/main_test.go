package main

import "testing"

func TestGatewayAddress(t *testing.T) {
	for origin, want := range map[string]string{
		"":                                 "https://localhost:8443",
		"https://localhost":                "https://localhost:8443",
		"https://localhost:9443":           "https://localhost:8443",
		"https://[::1]:9443":               "https://[::1]:8443",
		"https://metiquo.example.invalid/": "https://metiquo.example.invalid:8443",
	} {
		got, err := gatewayAddress(origin)
		if err != nil || got != want {
			t.Fatalf("%q: got %q, %v; want %q", origin, got, err, want)
		}
	}
	for _, origin := range []string{"http://localhost", "https://a.invalid/a", "https://user@localhost", "https://localhost?x=1", "https://localhost#x", "https://localhost:invalid", "https://localhost\n}", "https://{env.X}"} {
		if _, err := gatewayAddress(origin); err == nil {
			t.Fatalf("invalid origin accepted: %q", origin)
		}
	}
}
