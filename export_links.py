#!/usr/bin/env python3
"""Export a Happ subscription JSON to share links, one per proxy outbound.

`parser.parse_response` names every link after the entry's `remarks`, which is
fine for single-server entries but produces N identically-named links for the
balancer ("Авто ...") entries -- clients then dedupe them and you cannot tell
which server you are testing. This adds the outbound tag and address to the
name so each link is individually identifiable.

Entries whose xhttpSettings.extra uses the post-#6258 field names are marked,
since they need Xray-core >= v26.6.27 on the importing client; an older core
silently ignores those keys and fails with no error.
"""

import argparse
import json
import sys
from pathlib import Path

from parser import parse_response

MODERN_XHTTP_EXTRA_KEYS = {
    "xPaddingObfsMode", "xPaddingKey", "xPaddingHeader", "xPaddingPlacement",
    "xPaddingMethod", "uplinkHTTPMethod", "uplinkDataPlacement", "uplinkDataKey",
    "uplinkChunkSize", "seqPlacement", "seqKey", "sessionIDPlacement",
    "sessionIDKey", "sessionIDTable", "sessionIDLength",
}

PROXY_PROTOCOLS = ("vless", "trojan", "hysteria")


def address_of(outbound: dict) -> str:
    settings = outbound.get("settings") or {}
    for key in ("vnext", "servers"):
        entries = settings.get(key)
        if entries:
            return entries[0].get("address") or "?"
    return settings.get("address") or "?"


def needs_modern_core(outbound: dict) -> bool:
    stream = outbound.get("streamSettings") or {}
    extra = (stream.get("xhttpSettings") or {}).get("extra") or {}
    return bool(MODERN_XHTTP_EXTRA_KEYS & set(extra))


def export(entries: list, *, dedupe: bool) -> list:
    links, seen = [], set()

    for index, entry in enumerate(entries):
        remarks = entry.get("remarks", "")
        outbounds = [o for o in entry.get("outbounds") or [] if o.get("protocol") in PROXY_PROTOCOLS]
        multi = len(outbounds) > 1

        for outbound in outbounds:
            address = address_of(outbound)
            # Only disambiguate when an entry holds a pool; single-server entries
            # keep their remarks intact so they look the same as in Happ.
            name = f"{index:02d} {remarks}"
            if multi:
                name += f" [{outbound.get('tag', '?')} {address}]"
            if needs_modern_core(outbound):
                name += " ⚠26.6.27+"

            for link in parse_response(json.dumps([{"remarks": name, "outbounds": [outbound]}])):
                endpoint = link.split("#")[0]
                if dedupe and endpoint in seen:
                    continue
                seen.add(endpoint)
                links.append(link)

    return links


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="decoded subscription JSON")
    ap.add_argument("-o", "--out", help="output file (default: stdout)")
    ap.add_argument("--dedupe", action="store_true", help="skip links whose endpoint already appeared")
    args = ap.parse_args()

    try:
        entries = json.loads(Path(args.source).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: cannot read {args.source}: {e}", file=sys.stderr)
        sys.exit(1)

    links = export(entries, dedupe=args.dedupe)

    if args.out:
        Path(args.out).write_text("\n".join(links) + "\n", encoding="utf-8")
        print(f"{len(links)} links -> {args.out}")
    else:
        print("\n".join(links))


if __name__ == "__main__":
    main()
