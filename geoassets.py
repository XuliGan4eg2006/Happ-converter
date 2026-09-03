#!/usr/bin/env python3
"""Download the geoip.dat / geosite.dat files Xray needs for geo routing rules.

Xray only needs these when a config actually references `geosite:` or `geoip:`
names. Subscriptions from these providers use `geosite:category-ru` and friends
to keep Russian traffic on the direct outbound; without the file Xray refuses to
start with:

    common/geodata: failed to open geosite.dat

Note the asset is named geosite.dat but upstream publishes it as `dlc.dat` --
the v2fly domain-list-community build, which is what Xray releases bundle. It is
downloaded and renamed here.
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent

# Primary source first, fallback second. v2fly is what Xray bundles; the
# Loyalsoldier builds are drop-in replacements with a wider domain set.
SOURCES = {
    "geosite.dat": [
        "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat",
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
    ],
    "geoip.dat": [
        "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat",
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
    ],
}


def asset_dir() -> Path:
    """Where Xray looks for the .dat files."""
    env = os.environ.get("XRAY_LOCATION_ASSET")
    return Path(env) if env else HERE


def scan_requirements(text: str) -> set[str]:
    """Which .dat files the given subscription/config text actually needs."""
    needed = set()
    if re.search(r'"geosite:', text):
        needed.add("geosite.dat")
    if re.search(r'"geoip:', text):
        needed.add("geoip.dat")
    return needed


def _download(url: str, dest: Path) -> int:
    """Stream to a temp file, then rename -- never leave a truncated .dat behind."""
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
        size = 0
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
                    size += len(chunk)
            # mkstemp gives 0600; Xray may run as another user (or via sudo).
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return size


def ensure(needed: set[str], dest_dir: Path | None = None,
           force: bool = False, verbose: bool = True) -> list[str]:
    """Fetch any missing .dat files. Returns the names actually downloaded."""
    dest_dir = dest_dir or asset_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    fetched = []

    for name in sorted(needed):
        target = dest_dir / name
        if target.exists() and not force:
            if verbose:
                print(f"  {name}: present ({target.stat().st_size / 1e6:.1f} MB)")
            continue

        for url in SOURCES[name]:
            try:
                size = _download(url, target)
                if verbose:
                    print(f"  {name}: downloaded {size / 1e6:.1f} MB from {url.split('/')[4]}")
                fetched.append(name)
                break
            except Exception as e:
                print(f"  {name}: {url.split('/')[4]} failed ({e})", file=sys.stderr)
        else:
            print(f"  {name}: ALL SOURCES FAILED — geo routing rules will not load",
                  file=sys.stderr)

    return fetched


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?",
                    help="config/subscription JSON to scan; omit to fetch both files")
    ap.add_argument("-d", "--dir", help="destination (default: $XRAY_LOCATION_ASSET or script dir)")
    ap.add_argument("-f", "--force", action="store_true", help="re-download even if present")
    args = ap.parse_args()

    if args.source:
        try:
            needed = scan_requirements(Path(args.source).read_text(encoding="utf-8"))
        except OSError as e:
            print(f"Error: cannot read {args.source}: {e}", file=sys.stderr)
            sys.exit(1)
        if not needed:
            print(f"{args.source} references no geosite:/geoip: rules — no assets needed.")
            return
    else:
        needed = set(SOURCES)

    dest = Path(args.dir) if args.dir else asset_dir()
    print(f"Geo assets -> {dest}")
    ensure(needed, dest, force=args.force)


if __name__ == "__main__":
    main()
