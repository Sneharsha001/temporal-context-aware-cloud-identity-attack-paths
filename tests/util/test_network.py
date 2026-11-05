"""Tests for network module."""

from __future__ import annotations

import pytest

from arf_rt.util.network import (
    parse_ip,
    parse_network,
    is_ip_in_network,
    is_ip_in_any_network,
    is_private_ip,
    network_overlaps,
    network_contains,
    get_network_bounds,
    calculate_subnet_split,
    format_cidr,
    is_reserved_ip,
)


class TestParseIP:
    """Tests for parse_ip function."""

    def test_parse_ipv4(self):
        """Test parsing IPv4 address."""
        ip = parse_ip("192.168.1.1")
        assert str(ip) == "192.168.1.1"

    def test_parse_ipv6(self):
        """Test parsing IPv6 address."""
        ip = parse_ip("2001:db8::1")
        assert str(ip) == "2001:db8::1"

    def test_parse_with_whitespace(self):
        """Test parsing with leading/trailing whitespace."""
        ip = parse_ip("  10.0.0.1  ")
        assert str(ip) == "10.0.0.1"

    def test_invalid_ip(self):
        """Test parsing invalid IP raises ValueError."""
        with pytest.raises(ValueError):
            parse_ip("not.an.ip")


class TestParseNetwork:
    """Tests for parse_network function."""

    def test_parse_ipv4_cidr(self):
        """Test parsing IPv4 CIDR."""
        net = parse_network("10.0.0.0/16")
        assert str(net) == "10.0.0.0/16"

    def test_parse_ipv6_cidr(self):
        """Test parsing IPv6 CIDR."""
        net = parse_network("2001:db8::/32")
        assert str(net) == "2001:db8::/32"

    def test_parse_with_whitespace(self):
        """Test parsing with leading/trailing whitespace."""
        net = parse_network("  192.168.0.0/24  ")
        assert str(net) == "192.168.0.0/24"


class TestIsIPInNetwork:
    """Tests for is_ip_in_network function."""

    def test_ip_in_network(self):
        """Test IP in network."""
        assert is_ip_in_network("10.0.1.5", "10.0.0.0/16") is True

    def test_ip_not_in_network(self):
        """Test IP not in network."""
        assert is_ip_in_network("192.168.1.1", "10.0.0.0/16") is False

    def test_ip_on_boundary(self):
        """Test IP on network boundary."""
        assert is_ip_in_network("10.0.0.0", "10.0.0.0/16") is True
        assert is_ip_in_network("10.0.255.255", "10.0.0.0/16") is True


class TestIsIPInAnyNetwork:
    """Tests for is_ip_in_any_network function."""

    def test_ip_in_first_network(self):
        """Test IP matches first network."""
        networks = ["10.0.0.0/16", "192.168.0.0/16"]
        assert is_ip_in_any_network("10.0.1.1", networks) is True

    def test_ip_in_second_network(self):
        """Test IP matches second network."""
        networks = ["10.0.0.0/16", "192.168.0.0/16"]
        assert is_ip_in_any_network("192.168.1.1", networks) is True

    def test_ip_in_no_network(self):
        """Test IP matches no network."""
        networks = ["10.0.0.0/16", "192.168.0.0/16"]
        assert is_ip_in_any_network("172.16.0.1", networks) is False


class TestIsPrivateIP:
    """Tests for is_private_ip function."""

    def test_rfc1918_class_a(self):
        """Test RFC 1918 Class A (10.0.0.0/8)."""
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True

    def test_rfc1918_class_b(self):
        """Test RFC 1918 Class B (172.16.0.0/12)."""
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True

    def test_rfc1918_class_c(self):
        """Test RFC 1918 Class C (192.168.0.0/16)."""
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True

    def test_public_ip(self):
        """Test public IP is not private."""
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False


class TestNetworkOverlaps:
    """Tests for network_overlaps function."""

    def test_overlapping_networks(self):
        """Test overlapping networks."""
        assert network_overlaps("10.0.0.0/16", "10.0.128.0/17") is True

    def test_non_overlapping_networks(self):
        """Test non-overlapping networks."""
        assert network_overlaps("10.0.0.0/16", "192.168.0.0/16") is False

    def test_adjacent_networks(self):
        """Test adjacent networks (no overlap)."""
        assert network_overlaps("10.0.0.0/16", "10.1.0.0/16") is False


class TestNetworkContains:
    """Tests for network_contains function."""

    def test_contains_subnet(self):
        """Test network contains subnet."""
        assert network_contains("10.0.0.0/16", "10.0.1.0/24") is True

    def test_not_contains(self):
        """Test network does not contain."""
        assert network_contains("10.0.0.0/16", "192.168.1.0/24") is False

    def test_equal_networks(self):
        """Test equal networks."""
        assert network_contains("10.0.0.0/16", "10.0.0.0/16") is True


class TestGetNetworkBounds:
    """Tests for get_network_bounds function."""

    def test_ipv4_bounds(self):
        """Test IPv4 network bounds."""
        first, last = get_network_bounds("192.168.1.0/24")
        assert str(first) == "192.168.1.0"
        assert str(last) == "192.168.1.255"

    def test_ipv4_cidr_16(self):
        """Test IPv4 /16 bounds."""
        first, last = get_network_bounds("10.0.0.0/16")
        assert str(first) == "10.0.0.0"
        assert str(last) == "10.0.255.255"


class TestCalculateSubnetSplit:
    """Tests for calculate_subnet_split function."""

    def test_split_16_to_24(self):
        """Test splitting /16 into /24s."""
        subnets = calculate_subnet_split("10.0.0.0/16", 24)
        assert len(subnets) == 256
        assert str(subnets[0]) == "10.0.0.0/24"
        assert str(subnets[-1]) == "10.0.255.0/24"

    def test_split_24_to_28(self):
        """Test splitting /24 into /28s."""
        subnets = calculate_subnet_split("192.168.1.0/24", 28)
        assert len(subnets) == 16

    def test_invalid_prefix(self):
        """Test invalid prefix raises ValueError."""
        with pytest.raises(ValueError):
            calculate_subnet_split("10.0.0.0/16", 8)


class TestFormatCIDR:
    """Tests for format_cidr function."""

    def test_format_string(self):
        """Test formatting string CIDR."""
        assert format_cidr("10.0.0.0/16") == "10.0.0.0/16"

    def test_format_object(self):
        """Test formatting network object."""
        from ipaddress import ip_network
        net = ip_network("192.168.0.0/24")
        assert format_cidr(net) == "192.168.0.0/24"


class TestIsReservedIP:
    """Tests for is_reserved_ip function."""

    def test_loopback(self):
        """Test loopback addresses."""
        assert is_reserved_ip("127.0.0.1") is True
        assert is_reserved_ip("::1") is True

    def test_multicast(self):
        """Test multicast addresses."""
        assert is_reserved_ip("224.0.0.1") is True
        assert is_reserved_ip("ff02::1") is True

    def test_unspecified(self):
        """Test unspecified addresses."""
        assert is_reserved_ip("0.0.0.0") is True
        assert is_reserved_ip("::") is True

    def test_private_not_reserved(self):
        """Test private IPs are not reserved."""
        assert is_reserved_ip("10.0.0.1") is False
        assert is_reserved_ip("192.168.1.1") is False

    def test_public_not_reserved(self):
        """Test public IPs are not reserved."""
        assert is_reserved_ip("8.8.8.8") is False
        assert is_reserved_ip("1.1.1.1") is False