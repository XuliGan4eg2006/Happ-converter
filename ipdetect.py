"""Public IP auto-detection for the X-Real-Ip / X-Forwarded-For headers.

The lookup leaves the machine exactly like the subscription request does:
requests reads HTTP_PROXY / HTTPS_PROXY / ALL_PROXY (and NO_PROXY) by itself, so
with a proxy configured both go through it and the detected address is the one
the provider will actually see; without one, both go out directly.
"""

import ipaddress

import requests

IP_SERVICES = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ip.me",
    "https://icanhazip.com",
)
TIMEOUT = 5


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def detect_public_ip(verbose: bool = True) -> str | None:
    """Ask each echo service in turn; return the first well-formed address."""
    if verbose:
        print("  → detecting public IP...")

    for url in IP_SERVICES:
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        ip = resp.text.strip()
        if _valid_ip(ip):
            if verbose:
                print(f"  → detected public IP: {ip}")
            return ip

    if verbose:
        print("  → could not detect public IP, enter it manually.")
    return None
