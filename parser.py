import json
from urllib.parse import urlencode

def _stream_params(ss):
    """Build the shared security/transport query params for vless & trojan."""
    params = {
        "security": ss.get("security", "none"),
        "type":     ss.get("network", "tcp"),
    }
    sec = ss.get("security")
    if sec == "reality":
        r = ss.get("realitySettings", {})
        params.update({
            "pbk": r.get("publicKey", ""),
            "sni": r.get("serverName", ""),
            "fp":  r.get("fingerprint", ""),
            "sid": r.get("shortId", ""),
        })
    elif sec == "tls":
        t = ss.get("tlsSettings", {})
        if t.get("serverName"):
            params["sni"] = t["serverName"]
        if t.get("fingerprint"):
            params["fp"] = t["fingerprint"]
        if t.get("alpn"):
            params["alpn"] = ",".join(t["alpn"])
    net = ss.get("network", "tcp")
    if net == "ws":
        ws = ss.get("wsSettings", {})
        if ws.get("path"):
            params["path"] = ws["path"]
        if ws.get("headers", {}).get("Host"):
            params["host"] = ws["headers"]["Host"]
    elif net == "grpc":
        grpc = ss.get("grpcSettings", {})
        if grpc.get("serviceName"):
            params["serviceName"] = grpc["serviceName"]
    elif net == "xhttp":
        xh = ss.get("xhttpSettings", {})
        if xh.get("path"):
            params["path"] = xh["path"]
        if xh.get("host"):
            params["host"] = xh["host"]
        if xh.get("mode"):
            params["mode"] = xh["mode"]
    return params

def parse_response(response_text):
    jsoned = json.loads(response_text)
    gathered_vpn_configs = []

    for general_info in jsoned:
        for protocols in general_info["outbounds"]:
            if protocols["protocol"] == "vless":
                ss = protocols.get("streamSettings", {})
                for link_configs in protocols['settings']["vnext"]:
                    for user in link_configs['users']:
                        params = {"encryption": user.get("encryption", "none")}
                        params.update(_stream_params(ss))
                        if user.get("flow"):
                            params["flow"] = user["flow"]
                        gathered_vpn_configs.append(f"vless://{user['id']}@{link_configs['address']}:{link_configs['port']}?{urlencode(params)}#{general_info['remarks']}")
            elif protocols["protocol"] == "trojan":
                ss = protocols.get("streamSettings", {})
                params = _stream_params(ss)
                for server in protocols['settings']["servers"]:
                    gathered_vpn_configs.append(f"trojan://{server['password']}@{server['address']}:{server['port']}?{urlencode(params)}#{general_info['remarks']}")
            elif protocols["protocol"] == "hysteria":
                s = protocols.get("settings", {})
                ss = protocols.get("streamSettings", {})
                hy = ss.get("hysteriaSettings", {})
                tls = ss.get("tlsSettings", {})
                # only Hysteria2 has a standard share link
                if s.get("version") == 2 or hy.get("version") == 2:
                    auth = hy.get("auth", s.get("auth", ""))
                    address = s.get("address")
                    port = s.get("port")
                    params = {}
                    sni = tls.get("serverName")
                    if sni:
                        params["sni"] = sni
                    params["insecure"] = "1" if tls.get("allowInsecure") else "0"
                    if hy.get("obfs"):
                        params["obfs"] = "salamander"
                        if hy.get("obfsParam"):
                            params["obfs-password"] = hy["obfsParam"]
                    gathered_vpn_configs.append(f"hysteria2://{auth}@{address}:{port}?{urlencode(params)}#{general_info['remarks']}")

    return gathered_vpn_configs
