"""Saved subscription profiles (URL + request headers) for the Happ converter."""

import json
import os
from copy import deepcopy

from ipdetect import detect_public_ip

PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")

DEFAULT_HEADERS = {
    "User-Agent": "Happ/3.13.0",
    "X-Device-Os": "Android",
    "X-Device-Locale": "ru",
    "X-Device-Model": "ELP-NX1",
    "X-Ver-Os": "15",
    "Accept-Encoding": "gzip",
    "Connection": "close",
}


def _ask(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    return value if value else default


def load_profiles() -> list[dict]:
    """Read profiles.json; a missing or broken file just means 'no profiles'."""
    if not os.path.exists(PROFILES_FILE):
        return []
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Warning: could not read {PROFILES_FILE}: {e}")
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict) and p.get("sub_url")]


def save_profiles(profiles: list[dict]) -> None:
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Warning: could not write {PROFILES_FILE}: {e}")


def _print_profiles(profiles: list[dict]) -> None:
    print("\nSaved profiles:")
    for i, p in enumerate(profiles, 1):
        url = p["sub_url"]
        shown = url if len(url) <= 60 else url[:57] + "..."
        print(f"  {i}. {p.get('name', 'unnamed')} — {shown}")


def _header_value(prompt: str, default: str = "") -> str:
    """Read a header value; 'auto' is replaced by the detected public IP."""
    value = _ask(prompt, default)
    if value.lower() == "auto":
        return detect_public_ip() or default
    return value


def edit_headers(headers: dict) -> None:
    """Interactive header editor — add, change or drop request headers."""
    while True:
        keys = list(headers)
        print("\nRequest headers:")
        if not keys:
            print("  (none)")
        for i, k in enumerate(keys, 1):
            print(f"  {i}. {k}: {headers[k]}")
        print("Enter number to change a header, 'a' to add, 'd N' to delete, Enter to finish.")
        print("(type 'auto' as a value to fill in the detected public IP)")
        choice = _ask("> ")

        if not choice:
            return

        if choice.lower() == "a":
            name = _ask("  Header name: ")
            if not name:
                print("  Name is required.")
                continue
            headers[name] = _header_value(f"  Value for {name}: ")
            continue

        parts = choice.split()
        if parts[0].lower() == "d":
            if len(parts) < 2 or not parts[1].isdigit():
                print("  Usage: d <number>")
                continue
            idx = int(parts[1])
            if not 1 <= idx <= len(keys):
                print("  No such header.")
                continue
            removed = keys[idx - 1]
            del headers[removed]
            print(f"  Removed {removed}")
            continue

        if choice.isdigit():
            idx = int(choice)
            if not 1 <= idx <= len(keys):
                print("  No such header.")
                continue
            key = keys[idx - 1]
            headers[key] = _header_value(f"  {key} [{headers[key]}]: ", headers[key])
            continue

        print("  Unknown command.")


def _edit_profile(profile: dict) -> None:
    while True:
        print(f"\nEditing profile '{profile.get('name', 'unnamed')}'")
        print(f"  1. name             {profile.get('name', '')}")
        print(f"  2. subscription URL {profile['sub_url']}")
        print(f"  3. headers          ({len(profile.get('headers', {}))} set)")
        print("Enter number to edit, or press Enter to finish.")
        choice = _ask("> ")

        if not choice:
            return
        if choice == "1":
            profile["name"] = _ask(f"  Name [{profile.get('name', '')}]: ", profile.get("name", ""))
        elif choice == "2":
            profile["sub_url"] = _ask(f"  URL [{profile['sub_url']}]: ", profile["sub_url"])
        elif choice == "3":
            profile.setdefault("headers", {})
            edit_headers(profile["headers"])
        else:
            print("  Unknown option.")


def select_profile() -> dict | None:
    """Show saved profiles and let the user pick, edit or delete one.

    Returns the chosen profile (a copy) or None to fall through to the
    normal interactive setup.
    """
    profiles = load_profiles()
    if not profiles:
        return None

    while True:
        _print_profiles(profiles)
        print("Enter number to use a profile, 'e N' to edit, 'd N' to delete, "
              "or press Enter for a new setup.")
        choice = _ask("> ")

        if not choice:
            return None

        parts = choice.split()
        cmd = parts[0].lower()

        if cmd in ("e", "d"):
            if len(parts) < 2 or not parts[1].isdigit():
                print(f"  Usage: {cmd} <number>")
                continue
            idx = int(parts[1])
            if not 1 <= idx <= len(profiles):
                print("  No such profile.")
                continue
            if cmd == "e":
                _edit_profile(profiles[idx - 1])
            else:
                removed = profiles.pop(idx - 1)
                print(f"  Deleted profile '{removed.get('name', 'unnamed')}'")
                if not profiles:
                    save_profiles(profiles)
                    return None
            save_profiles(profiles)
            continue

        if choice.isdigit():
            idx = int(choice)
            if not 1 <= idx <= len(profiles):
                print("  No such profile.")
                continue
            chosen = profiles[idx - 1]
            print(f"  → using profile '{chosen.get('name', 'unnamed')}'")
            return deepcopy(chosen)

        print("  Unknown command.")


def offer_save(sub_url: str, headers: dict, used_profile: dict | None) -> None:
    """Ask whether to store the current URL/headers as a profile (or update one)."""
    profiles = load_profiles()

    if used_profile is not None:
        unchanged = (used_profile.get("sub_url") == sub_url
                     and used_profile.get("headers", {}) == headers)
        if unchanged:
            return
        name = used_profile.get("name", "unnamed")
        if _ask(f"\nProfile '{name}' changed. Update it? (y/n): ").lower() != "y":
            return
        for p in profiles:
            if p.get("name") == name:
                p["sub_url"] = sub_url
                p["headers"] = deepcopy(headers)
                break
        else:
            profiles.append({"name": name, "sub_url": sub_url, "headers": deepcopy(headers)})
        save_profiles(profiles)
        print(f"  → profile '{name}' updated ({PROFILES_FILE})")
        return

    if _ask("\nSave this as a profile? (y/n): ").lower() != "y":
        return

    name = _ask("  Profile name: ", "profile")
    existing = next((p for p in profiles if p.get("name") == name), None)
    if existing is not None:
        if _ask(f"  Profile '{name}' already exists. Overwrite? (y/n): ").lower() != "y":
            return
        existing["sub_url"] = sub_url
        existing["headers"] = deepcopy(headers)
    else:
        profiles.append({"name": name, "sub_url": sub_url, "headers": deepcopy(headers)})
    save_profiles(profiles)
    print(f"  → profile '{name}' saved to {PROFILES_FILE}")
