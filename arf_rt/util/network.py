"""
arf_rt/util/network.py - Network and IP address validation utilities.

Provides helper routines for parsing IPv4/IPv6 addresses, calculating CIDR block
containment, and validating source IP constraints in cloud policy conditions.
"""

from __future__ import annotations

import ipaddress
from typing import Sequence, Union

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_ip(ip_str: str) -> IPAddress:
    """Parse a string into an IPv4Address or IPv6Address object.

    Args:
        ip_str: IP address string.

    Returns:
        IPv4Address or IPv6Address.

    Raises:
        ValueError: If ip_str is not a valid IP address.
    """
    return ipaddress.ip_address(ip_str.strip())


def parse_network(cidr_str: str) -> IPNetwork:
    """Parse a CIDR string into an IPv4Network or IPv6Network.

    Args:
        cidr_str: CIDR string (e.g., '10.0.0.0/16').

    Returns:
        IPv4Network or IPv6Network object with strict host bit checking.
    """
    return ipaddress.ip_network(cidr_str.strip(), strict=False)


def is_ip_in_network(ip: Union[str, IPAddress], network: Union[str, IPNetwork]) -> bool:
    """Check whether an IP address is contained within a CIDR network block.

    Args:
        ip: IP address string or object.
        network: Network CIDR string or object.

    Returns:
        True if ip is inside network, False otherwise.
    """
    if isinstance(ip, str):
        ip = parse_ip(ip)
    if isinstance(network, str):
        network = parse_network(network)

    return ip in network


def is_ip_in_any_network(
    ip: Union[str, IPAddress],
    networks: Sequence[Union[str, IPNetwork]],
) -> bool:
    """Check if an IP address falls within any of the provided CIDR networks.

    Args:
        ip: IP address string or object.
        networks: Sequence of network CIDRs.

    Returns:
        True if ip matches at least one network in the sequence.
    """
    if isinstance(ip, str):
        ip = parse_ip(ip)

    for net in networks:
        if isinstance(net, str):
            net = parse_network(net)
        if ip in net:
            return True
    return False


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address belongs to RFC 1918 / RFC 4193 private space.

    Args:
        ip_str: IP address string.

    Returns:
        True if address is private/internal.
    """
    return parse_ip(ip_str).is_private


def network_overlaps(network1: Union[str, IPNetwork], network2: Union[str, IPNetwork]) -> bool:
    """Check if two CIDR networks overlap.

    Args:
        network1: First network CIDR string or object.
        network2: Second network CIDR string or object.

    Returns:
        True if networks overlap, False otherwise.
    """
    if isinstance(network1, str):
        network1 = parse_network(network1)
    if isinstance(network2, str):
        network2 = parse_network(network2)

    return network1.overlaps(network2)


def network_contains(outer: Union[str, IPNetwork], inner: Union[str, IPNetwork]) -> bool:
    """Check if one network fully contains another.

    Args:
        outer: Outer network CIDR string or object.
        inner: Inner network CIDR string or object.

    Returns:
        True if outer contains inner, False otherwise.
    """
    if isinstance(outer, str):
        outer = parse_network(outer)
    if isinstance(inner, str):
        inner = parse_network(inner)

    return outer.supernet_of(inner)


def get_network_bounds(network: Union[str, IPNetwork]) -> tuple[IPAddress, IPAddress]:
    """Get the first and last IP addresses in a network.

    Args:
        network: Network CIDR string or object.

    Returns:
        Tuple of (first_ip, last_ip) as IPAddress objects.
    """
    if isinstance(network, str):
        network = parse_network(network)

    return (network.network_address, network.broadcast_address)


def calculate_subnet_split(network: Union[str, IPNetwork], new_prefix: int) -> list[IPNetwork]:
    """Split a network into subnets of a given prefix length.

    Args:
        network: Network CIDR string or object.
        new_prefix: New prefix length (must be >= current prefix).

    Returns:
        List of subnet IPNetwork objects.

    Raises:
        ValueError: If new_prefix is smaller than current prefix.
    """
    if isinstance(network, str):
        network = parse_network(network)

    if new_prefix < network.prefixlen:
        raise ValueError(f"New prefix {new_prefix} must be >= current prefix {network.prefixlen}")

    return list(network.subnets(new_prefix - network.prefixlen))


def format_cidr(network: Union[str, IPNetwork]) -> str:
    """Format a network as a standard CIDR string.

    Args:
        network: Network CIDR string or object.

    Returns:
        Formatted CIDR string.
    """
    if isinstance(network, str):
        network = parse_network(network)

    return str(network)


def is_reserved_ip(ip: Union[str, IPAddress]) -> bool:
    """Check if an IP address is reserved (loopback, multicast, etc.).

    Args:
        ip: IP address string or object.

    Returns:
        True if address is reserved/special-use.
    """
    if isinstance(ip, str):
        ip = parse_ip(ip)

    return ip.is_loopback or ip.is_multicast or ip.is_reserved or ip.is_unspecified
