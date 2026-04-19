#!/usr/bin/env python3
"""Happ Proxy Subscription Converter — for V2RayN / V2RayA"""

import base64
import sys
import uuid
import requests

from parser import parse_response

def autogenerate_hwid() -> str:
    return uuid.uuid4().hex[:16]


def get_input(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    return value if value else default


def main():
    sub_url = get_input("Subscription URL: ")
    if not sub_url:
        print("Error: subscription URL is required.", file=sys.stderr)
        sys.exit(1)

    hwid_input = get_input("HWID (leave blank to autogenerate): ")
    hwid = hwid_input if hwid_input else autogenerate_hwid()
    if not hwid_input:
        print(f"  → generated HWID: {hwid}")

    real_ip = get_input("X-Real-Ip (e.g. 101.202.303.404): ", "101.202.303.404")
    forwarded_for = get_input(f"X-Forwarded-For (leave blank to use same as Real-Ip [{real_ip}]): ", real_ip)

    headers = {
        "User-Agent": "Happ/3.13.0",
        "X-Device-Os": "Android",
        "X-Device-Locale": "ru",
        "X-Device-Model": "ELP-NX1",
        "X-Ver-Os": "15",
        "Accept-Encoding": "gzip",
        "Connection": "close",
        "X-Hwid": hwid,
        "X-Real-Ip": real_ip,
        "X-Forwarded-For": forwarded_for,
    }

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

if __name__ == "__main__":
    main()
