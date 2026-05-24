import base64
import json
import os

from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_der_private_key
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

def _load_json(filename: str) -> dict | list:
    path = os.path.join("assets", filename)
    with open(path, "r") as f:
        return json.load(f)


def _b64_decode(text: str) -> bytes:
    text = text.strip()
    for variant in (text, text.rstrip("=")):
        for alphabet in ("standard", "urlsafe"):
            padded = variant + "=" * ((4 - len(variant) % 4) % 4)
            try:
                return (base64.b64decode if alphabet == "standard" else base64.urlsafe_b64decode)(padded)
            except Exception:
                pass
    raise ValueError(f"Invalid base64: {text[:40]}...")


def _shuffle_blocks(text: str, block_size: int, order: list[int]) -> str:
    data = text.encode()
    full = len(data) // block_size * block_size
    out = bytearray()
    for i in range(0, full, block_size):
        block = data[i:i + block_size]
        for idx in order:
            out.append(block[idx])
    out += data[full:]
    return out.decode()


def m4831f(text: str) -> str:
    return _shuffle_blocks(text, 6, [1, 3, 5, 0, 2, 4])

def inverse_m4831f(text: str) -> str:
    return _shuffle_blocks(text, 6, [3, 0, 4, 1, 5, 2])

def m4842j(text: str) -> str:
    return _shuffle_blocks(text, 2, [1, 0])

def permute4(text: str) -> str:
    return _shuffle_blocks(text, 4, [2, 3, 0, 1])


def _load_private_key(encoded: str):
    der = base64.b64decode(encoded)
    return load_der_private_key(der, password=None)


def _load_native_keys():
    data = _load_json("native_keys.json")
    return [_load_private_key(k) for k in data["keys"]]


def _load_crypt5_keys() -> dict[str, str]:
    data = _load_json("crypt5_final_keys.json")
    return data["keys"]


def _rsa_decrypt(key, ciphertext_bytes: bytes) -> str:
    return key.decrypt(ciphertext_bytes, PKCS1v15()).decode()


def _decrypt_rsa_crypt(ciphertext: str, mode: int) -> str:
    keys = _load_native_keys()
    key = keys[mode]
    return _rsa_decrypt(key, _b64_decode(ciphertext))


def _decrypt_crypt5(payload: str) -> str:
    original = inverse_m4831f(payload)
    shuffled = permute4(original)

    if len(shuffled) < 8:
        raise ValueError("crypt5 payload too short")

    marker = shuffled[:4] + shuffled[-4:]
    body = shuffled[4:-4]

    if len(body) < 13:
        raise ValueError("crypt5 body too short")

    nonce = body[:12].encode()
    rest = body[12:]

    digit_count = len(rest) - len(rest.lstrip("0123456789"))
    if digit_count == 0:
        raise ValueError("crypt5 segment length missing")

    segment_len = int(rest[:digit_count])
    packed = rest[digit_count:]

    if len(packed) < 1 + segment_len:
        raise ValueError("crypt5 encrypted segment truncated")

    encrypted_segment = packed[1:1 + segment_len]
    rsa_ciphertext = packed[1 + segment_len:]

    crypt5_keys = _load_crypt5_keys()
    if marker not in crypt5_keys:
        raise ValueError(f"unknown crypt5 marker: {marker}")

    rsa_plain = _rsa_decrypt(
        _load_private_key(crypt5_keys[marker]),
        _b64_decode(rsa_ciphertext),
    )
    chacha_key = _b64_decode(m4842j(rsa_plain))

    if len(chacha_key) != 32:
        raise ValueError(f"ChaCha20 key has invalid length: {len(chacha_key)}")

    encrypted = _b64_decode(encrypted_segment)
    chacha = ChaCha20Poly1305(chacha_key)
    plaintext = chacha.decrypt(nonce, encrypted, None)
    return plaintext.decode()


def decrypt(value: str) -> str:
    prefixes = [
        ("happ://crypt5/", 4),
        ("happ://crypt4/", 3),
        ("happ://crypt3/", 2),
        ("happ://crypt2/", 1),
        ("happ://crypt/",  0),
    ]

    mode, payload = 4, value
    for prefix, m in prefixes:
        if value.startswith(prefix):
            mode, payload = m, value[len(prefix):]
            break

    if mode == 4:
        step1 = m4831f(payload)
        step2 = _decrypt_crypt5(step1)
        step3 = m4842j(step2)
        return _b64_decode(step3).decode()

    return _decrypt_rsa_crypt(payload, mode)
