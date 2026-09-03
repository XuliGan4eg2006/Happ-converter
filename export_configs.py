#!/usr/bin/env python3
"""Export Happ subscription entries as standalone Xray JSON configs.

Some subscription entries cannot be expressed as a `vless://` share link at all:

  * balancer entries ("Авто | ...") pick a server at runtime from a pool via
    `routing.balancers` + `burstObservatory` health pings, and chain tiers
    together with `loopback` outbounds. A share link carries exactly one server,
    so the whole selection mechanism is lost.
  * xhttp entries carry an `xhttpSettings.extra` obfuscation block whose fields
    (sessionIDTable, sessionIDLength, seqPlacement, uplinkDataPlacement, ...)
    only exist in Xray-core >= v26.6.27. A client on an older core silently
    ignores them and speaks plain xhttp, which the server rejects.

Each entry in the subscription is already a complete Xray config (dns, routing,
inbounds, outbounds), so it can be handed to `xray -c <file>` unchanged.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# xhttpSettings.extra keys that upstream Xray only understands from v26.6.27 on
# (PR #5414 added the padding/placement options, PR #6258 renamed session* to
# sessionID* and added the table/length knobs).
MODERN_XHTTP_EXTRA_KEYS = {
    "xPaddingObfsMode", "xPaddingKey", "xPaddingHeader", "xPaddingPlacement",
    "xPaddingMethod", "uplinkHTTPMethod", "uplinkDataPlacement", "uplinkDataKey",
    "uplinkChunkSize", "seqPlacement", "seqKey", "sessionIDPlacement",
    "sessionIDKey", "sessionIDTable", "sessionIDLength",
}


def slugify(remarks: str, index: int) -> str:
    """Filesystem-safe name; the remarks are emoji-heavy so keep it conservative."""
    text = re.sub(r"[^\w\-]+", "_", remarks, flags=re.UNICODE).strip("_")
    return f"{index:02d}_{text or 'config'}"


def describe(entry: dict) -> dict:
    """Report what makes this entry unrepresentable as a share link."""
    routing = entry.get("routing") or {}
    balancers = routing.get("balancers") or []
    outbounds = entry.get("outbounds") or []

    modern_keys = set()
    networks = set()
    for outbound in outbounds:
        stream = outbound.get("streamSettings") or {}
        if not stream:
            continue
        networks.add(stream.get("network") or "tcp")
        extra = (stream.get("xhttpSettings") or {}).get("extra") or {}
        modern_keys |= MODERN_XHTTP_EXTRA_KEYS & set(extra)

    proxy_outbounds = [
        o for o in outbounds
        if o.get("protocol") not in ("freedom", "blackhole", "dns", "loopback")
    ]

    return {
        "balancers": [b.get("tag") for b in balancers],
        "servers": len(proxy_outbounds),
        "networks": sorted(networks),
        "modern_xhttp_keys": sorted(modern_keys),
    }


def export(entries: list, out_dir: Path, verbose: bool = True) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for index, entry in enumerate(entries):
        remarks = entry.get("remarks", "")
        info = describe(entry)

        # `remarks` is v2rayN/Happ subscription metadata, not part of the Xray
        # schema — keep it out of the config we hand to the core.
        config = {k: v for k, v in entry.items() if k != "remarks"}

        path = out_dir / f"{slugify(remarks, index)}.json"
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(path)

        if verbose:
            notes = []
            if info["balancers"]:
                notes.append(f"balancers={','.join(info['balancers'])} over {info['servers']} servers")
            if info["modern_xhttp_keys"]:
                notes.append("needs Xray-core >= v26.6.27")
            suffix = f"  [{'; '.join(notes)}]" if notes else ""
            print(f"{path}  — {remarks}{suffix}")

    return written


def safe_name(name: str) -> str:
    """Directory name for a profile — profile names are free text."""
    cleaned = re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")
    return cleaned or "profile"


def export_for_profile(response_text: str, profile_name: str,
                       base_dir: str = "configs", verbose: bool = False) -> tuple[Path, int]:
    """Write one Xray config per subscription entry under configs/<profile>/.

    Returns (directory, count). Raises on malformed JSON so the caller can
    decide whether that is fatal.
    """
    entries = json.loads(response_text)
    if not isinstance(entries, list):
        raise ValueError("subscription is not a JSON array of Xray configs")

    out_dir = Path(base_dir) / safe_name(profile_name)
    # Drop configs from a previous run so removed servers do not linger.
    if out_dir.is_dir():
        for stale in out_dir.glob("*.json"):
            stale.unlink()

    written = export(entries, out_dir, verbose=verbose)
    return out_dir, len(written)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default="debug_response.txt",
                    help="decoded subscription JSON (default: debug_response.txt)")
    ap.add_argument("-o", "--out-dir", default="configs", help="output directory (default: configs)")
    args = ap.parse_args()

    try:
        entries = json.loads(Path(args.source).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: cannot read subscription JSON from {args.source}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(entries, list):
        print("Error: expected a JSON array of Xray configs.", file=sys.stderr)
        sys.exit(1)

    export(entries, Path(args.out_dir))
    print(f"\nRun one with:  xray -c {args.out_dir}/<file>.json   (SOCKS on 127.0.0.1:10808)")


if __name__ == "__main__":
    main()
