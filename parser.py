import json
from urllib.parse import urlencode

DEFAULT_NETWORK = "tcp"


def _blank(value) -> bool:
    """Kotlin zl4.F0 / isBlank equivalent."""
    return value is None or str(value).strip() == ""


def _put(params: dict, key: str, value) -> None:
    """Append a query param only if it is non-blank (Happ skips blanks)."""
    if not _blank(value):
        params[key] = value


def _tls_params(ss: dict, params: dict) -> None:
    """Emit TLS / REALITY query params.

    Happ picks tlsSettings first and falls back to realitySettings, then reads
    every field off whichever bean is present (serverName, alpn, fp, ech, pbk,
    sid, spx, pqv, pcs, pcn).
    """
    t = ss.get("tlsSettings") or ss.get("realitySettings")
    if not t:
        return

    _put(params, "sni", t.get("serverName"))

    alpn = t.get("alpn")
    if alpn:
        joined = ",".join(alpn) if isinstance(alpn, list) else str(alpn)
        _put(params, "alpn", joined)

    _put(params, "fp",  t.get("fingerprint"))
    _put(params, "ech", t.get("echConfigList"))
    _put(params, "pbk", t.get("publicKey"))
    _put(params, "sid", t.get("shortId"))
    _put(params, "spx", t.get("spiderX"))
    _put(params, "pqv", t.get("mldsa65Verify"))
    _put(params, "pcs", t.get("pinnedPeerCertSha256"))
    _put(params, "pcn", t.get("verifyPeerCertByName"))


def _network_params(ss: dict, params: dict) -> None:
    """Emit transport-specific params, mirroring OutboundBean.l() + the builders."""
    net = ss.get("network") or DEFAULT_NETWORK

    if net == "tcp":
        header = (ss.get("tcpSettings", {}) or {}).get("header", {}) or {}
        params["headerType"] = header.get("type") or "none"
        req = header.get("request", {}) or {}
        host = (req.get("headers", {}) or {}).get("Host")
        if isinstance(host, list):
            host = ",".join(host)
        _put(params, "host", host)

    elif net in ("ws", "httpupgrade"):
        s = ss.get("wsSettings" if net == "ws" else "httpupgradeSettings", {}) or {}
        if net == "ws":
            host = (s.get("headers", {}) or {}).get("Host")
        else:
            host = s.get("host")
        _put(params, "host", host)
        _put(params, "path", s.get("path"))

    elif net in ("xhttp", "splithttp"):
        xh = ss.get("xhttpSettings", {}) or {}
        _put(params, "mode", xh.get("mode"))
        _put(params, "host", xh.get("host"))
        _put(params, "path", xh.get("path"))
        # Happ serializes the whole `extra` object to compact JSON and passes it
        # as the `extra` query param. Dropping it makes xhttp servers that rely
        # on custom padding / xmux / seq settings reject the client -> the exact
        # failure the converter had before.
        extra = xh.get("extra")
        if extra is not None:
            params["extra"] = json.dumps(extra, separators=(",", ":"), ensure_ascii=False)

    elif net == "grpc":
        g = ss.get("grpcSettings", {}) or {}
        multi = g.get("multiMode")
        if multi is None:
            multi = g.get("mode")  # subscription JSON uses `mode` (bool)
        params["mode"] = "multi" if multi is True else "gun"
        params["authority"] = g.get("authority") or ""
        params["serviceName"] = g.get("serviceName") or ""

    elif net == "kcp":
        kcp = ss.get("kcpSettings", {}) or {}
        params["headerType"] = (kcp.get("header", {}) or {}).get("type") or "none"
        _put(params, "seed", kcp.get("seed"))


def _stream_params(ss: dict, *, encryption: str = None, flow: str = None) -> dict:
    """Build the shared query string for vless / trojan links."""
    params = {}
    if encryption is not None:
        params["encryption"] = encryption if encryption else "none"
    _put(params, "flow", flow)

    security = ss.get("security")
    params["security"] = security if security else "none"

    _tls_params(ss, params)

    params["type"] = ss.get("network") or DEFAULT_NETWORK
    _network_params(ss, params)
    return params


def _hysteria2_link(protocol: dict, remarks: str) -> str | None:
    """Standard hysteria2 share link (hiddify / nekobox compatible)."""
    s = protocol.get("settings", {}) or {}
    ss = protocol.get("streamSettings", {}) or {}
    hy = ss.get("hysteriaSettings", {}) or {}
    tls = ss.get("tlsSettings", {}) or {}

    if not (s.get("version") == 2 or hy.get("version") == 2):
        return None

    auth = hy.get("auth", s.get("auth", ""))
    address = s.get("address")
    port = s.get("port")
    params = {}
    _put(params, "sni", tls.get("serverName"))
    params["insecure"] = "1" if tls.get("allowInsecure") else "0"
    if hy.get("obfs"):
        params["obfs"] = "salamander"
        _put(params, "obfs-password", hy.get("obfsParam"))
    return f"hysteria2://{auth}@{address}:{port}?{urlencode(params)}#{remarks}"


def parse_response(response_text):
    jsoned = json.loads(response_text)
    gathered_vpn_configs = []

    for general_info in jsoned:
        remarks = general_info.get("remarks", "")
        for protocols in general_info["outbounds"]:
            proto = protocols["protocol"]

            if proto == "vless":
                ss = protocols.get("streamSettings", {}) or {}
                for link_configs in protocols['settings']["vnext"]:
                    for user in link_configs['users']:
                        params = _stream_params(
                            ss,
                            encryption=user.get("encryption", "none"),
                            flow=user.get("flow"),
                        )
                        gathered_vpn_configs.append(
                            f"vless://{user['id']}@{link_configs['address']}:{link_configs['port']}?{urlencode(params)}#{remarks}"
                        )

            elif proto == "trojan":
                ss = protocols.get("streamSettings", {}) or {}
                for server in protocols['settings']["servers"]:
                    params = _stream_params(ss, flow=server.get("flow"))
                    gathered_vpn_configs.append(
                        f"trojan://{server['password']}@{server['address']}:{server['port']}?{urlencode(params)}#{remarks}"
                    )

            elif proto == "hysteria":
                link = _hysteria2_link(protocols, remarks)
                if link:
                    gathered_vpn_configs.append(link)

    return gathered_vpn_configs
