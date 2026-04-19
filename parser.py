import json
from urllib.parse import urlencode

def parse_response(response_text):
    jsoned = json.loads(response_text)
    gathered_vless_configs = []

    for general_info in jsoned:
        for protocols in general_info["outbounds"]:
            if protocols["protocol"] == "vless":
                ss = protocols.get("streamSettings", {})
                for link_configs in protocols['settings']["vnext"]:
                    for user in link_configs['users']:
                        params = {
                            "encryption": user.get("encryption", "none"),
                            "security":   ss.get("security", "none"),
                            "type":       ss.get("network", "tcp"),
                        }
                        if user.get("flow"):
                            params["flow"] = user["flow"]
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
                        gathered_vless_configs.append(f"vless://{user['id']}@{link_configs['address']}:{link_configs['port']}?{urlencode(params)}#{general_info['remarks']}")

    return gathered_vless_configs
