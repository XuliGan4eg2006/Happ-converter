#!/usr/bin/env python3
"""Happ Proxy Subscription Converter — for V2RayN / V2RayA"""

import base64
import sys
import uuid
import requests

from urllib.parse import urlparse

from parser import parse_response
from server import start as start_server
from happ_decrypt import decrypt as happ_decrypt
from profiles import DEFAULT_HEADERS, edit_headers, offer_save, select_profile
from ipdetect import detect_public_ip
from export_configs import export_for_profile
import geoassets

def autogenerate_hwid() -> str:
    return uuid.uuid4().hex[:16]


def get_input(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    return value if value else default


def build_headers() -> dict:
    """Interactive header setup for a fresh run."""
    hwid_input = get_input("HWID (leave blank to autogenerate): ")
    hwid = hwid_input if hwid_input else autogenerate_hwid()
    if not hwid_input:
        print(f"  \u2192 generated HWID: {hwid}")

    default_ip = detect_public_ip() or "101.101.101.101"
    real_ip = get_input(f"X-Real-Ip [{default_ip}]: ", default_ip)
    forwarded_for = get_input(f"X-Forwarded-For (leave blank to use same as Real-Ip [{real_ip}]): ", real_ip)

    headers = dict(DEFAULT_HEADERS)
    headers["X-Hwid"] = hwid
    headers["X-Real-Ip"] = real_ip
    headers["X-Forwarded-For"] = forwarded_for

    if get_input("Edit request headers? (y/n): ").lower() == "y":
        edit_headers(headers)

    return headers


def config_dir_name(profile: dict | None, sub_url: str) -> str:
    """Name for configs/<name>/ — the profile name, else the subscription host."""
    if profile and profile.get("name"):
        return profile["name"]
    return urlparse(sub_url).hostname or "profile"


def refresh_profile_ip(headers: dict) -> None:
    """Re-detect the public IP for a stored profile — it changes between sessions."""
    old = headers.get("X-Real-Ip")
    if not old:
        return

    ip = detect_public_ip()
    if not ip or ip == old:
        return

    if get_input(f"Profile IP is {old}, detected {ip}. Use detected? (y/n): ").lower() != "y":
        return

    headers["X-Real-Ip"] = ip
    if headers.get("X-Forwarded-For") == old:
        headers["X-Forwarded-For"] = ip


def main():
    profile = select_profile()

    if profile is not None:
        sub_url = profile["sub_url"]
        headers = dict(profile.get("headers") or DEFAULT_HEADERS)
        refresh_profile_ip(headers)
    else:
        sub_url = get_input("Subscription URL: ")
        if not sub_url:
            print("Error: subscription URL is required.", file=sys.stderr)
            sys.exit(1)
        headers = None

    if sub_url.startswith("happ://crypt"):
        print("  \u2192 detected happ://crypt link, decrypting...")
        try:
            sub_url = happ_decrypt(sub_url)
            print(f"  \u2192 decrypted URL: {sub_url}")
        except Exception as e:
            print(f"Error: decryption failed: {e}", file=sys.stderr)
            sys.exit(1)

    if headers is None:
        headers = build_headers()

    try:
        resp = requests.get(sub_url, headers=headers, timeout=30, verify=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error 502: Failed to fetch subscription\n  {e}\nHint: check the URL, headers, or try changing HWID/IP.", file=sys.stderr)
        sys.exit(2)

    raw = resp.content
    try:
        output = base64.b64decode(raw, validate=True).decode("utf-8")
    except Exception:
        output = raw.decode("utf-8", errors="replace")

    with open("debug_response.txt", "w") as f:
        f.write(output)

    vless_links = parse_response(output)

    print("Extracted VLESS links: \n")
    print("\n".join(vless_links))

    # Share links cannot carry routing, balancers or the observatory, so also
    # keep each entry as the full Xray config it arrived as.
    try:
        out_dir, count = export_for_profile(output, config_dir_name(profile, sub_url))
        print(f"\n  → wrote {count} full Xray configs to {out_dir}/")
    except Exception as e:
        print(f"\nWarning: could not export configs: {e}", file=sys.stderr)

    # Configs using geosite:/geoip: rules will not start without the .dat files.
    needed = geoassets.scan_requirements(output)
    if needed:
        print(f"  → geo rules need {', '.join(sorted(needed))}")
        try:
            geoassets.ensure(needed)
        except Exception as e:
            print(f"Warning: could not fetch geo assets: {e}", file=sys.stderr)

    offer_save(sub_url, headers, profile)

    print("\nStart sub server? (y/n)")
    server_prompt = get_input(">")
    if server_prompt == "y":
        start_server(vless_links)

if __name__ == "__main__":
    main()
