package main

import (
	"fmt"
	"net"
	"net/url"
	"os"
	"regexp"

	cmd "github.com/caddyserver/caddy/v2/cmd"
	_ "github.com/caddyserver/caddy/v2/modules/standard"
)

func gatewayAddress(origin string) (string, error) {
	if origin == "" {
		origin = "https://localhost:8443"
	}
	u, err := url.Parse(origin)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil ||
		(u.Path != "" && u.Path != "/") || u.RawQuery != "" || u.Fragment != "" {
		return "", fmt.Errorf("APP_PUBLIC_ORIGIN doit être une origine HTTPS")
	}
	host := u.Hostname()
	if net.ParseIP(host) == nil && !regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}$`).MatchString(host) {
		return "", fmt.Errorf("hôte HTTPS invalide")
	}
	return "https://" + net.JoinHostPort(host, "8443"), nil
}

func main() {
	address, err := gatewayAddress(os.Getenv("APP_PUBLIC_ORIGIN"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := os.Setenv("METIQUO_GATEWAY_ADDRESS", address); err != nil {
		fmt.Fprintln(os.Stderr, "configuration HTTPS indisponible")
		os.Exit(2)
	}
	cmd.Main()
}
