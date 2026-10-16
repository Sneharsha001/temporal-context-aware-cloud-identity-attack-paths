"""
tests/unit/test_network.py - Unit tests for network and CIDR validation utilities.
"""

import pytest
from arf_rt.util.network import (
    parse_ip,
    parse_network,
    is_ip_in_network,
    is_ip_in_any_network,
    is_private_ip,
)


def test_parse_ip_valid():
    ip4 = parse_ip("192.168.1.1")
    assert str(ip4) == "192.168.1.1"

    ip6 = parse_ip("2001:db8::1")
    assert str(ip6) == "2001:db8::1"


def test_parse_ip_invalid():
    with pytest.raises(ValueError):
        parse_ip("invalid-ip")


def test_is_ip_in_network():
    assert is_ip_in_network("10.0.1.50", "10.0.0.0/16") is True
    assert is_ip_in_network("192.168.1.1", "10.0.0.0/16") is False


def test_is_ip_in_any_network():
    nets = ["10.0.0.0/8", "172.16.0.0/12"]
    assert is_ip_in_any_network("10.5.20.1", nets) is True
    assert is_ip_in_any_network("172.20.0.5", nets) is True
    assert is_ip_in_any_network("8.8.8.8", nets) is False


def test_is_private_ip():
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("192.168.0.1") is True
    assert is_private_ip("1.1.1.1") is False
