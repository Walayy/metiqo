"""Classifier une exposition sans résolution DNS ni confiance implicite au LAN."""

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from urllib.parse import urlsplit

type Network = IPv4Network | IPv6Network

_PRIVATE: tuple[Network, ...] = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
    IPv6Network("fc00::/7"),
)


def private_networks(values: tuple[str, ...]) -> tuple[Network, ...]:
    result: list[Network] = []
    if len(values) > 32:
        raise ValueError("AUTH_PRIVATE_NETWORKS accepte au maximum 32 réseaux")
    for value in values:
        try:
            network = ip_network(value, strict=True)
        except ValueError:
            raise ValueError("AUTH_PRIVATE_NETWORKS exige des CIDR privés explicites") from None
        if not any(
            network.version == parent.version
            and int(network.network_address) >= int(parent.network_address)
            and int(network.broadcast_address) <= int(parent.broadcast_address)
            for parent in _PRIVATE
        ):
            raise ValueError("AUTH_PRIVATE_NETWORKS interdit les plages publiques ou réservées")
        result.append(network)
    return tuple(result)


def literal_address(host: str) -> IPv4Address | IPv6Address:
    try:
        return ip_address(host)
    except ValueError:
        raise ValueError("APP_PUBLISH_HOST exige une adresse IP littérale") from None


def allowed_without_auth(host: str, networks: tuple[Network, ...]) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback or any(address in network for network in networks)


def origin_host(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or not valid_port
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        return parsed.hostname
    except ValueError:
        raise ValueError(
            "APP_PUBLIC_ORIGIN exige une origine HTTP ou HTTPS sans chemin ni identifiants"
        ) from None
