import uvicorn
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


app = FastAPI(title="VLESS Sub server")
_vless_links: list[str] = []


def start(vless_links: list[str], host: str = "0.0.0.0", port: int = 8080) -> None:
    global _vless_links
    _vless_links = vless_links
    print(f"\nWeb server running at http://{host}:{port}/")
    print("  GET  /            → plain-text subscription (import this URL in Hiddify/Nekoray/your client)")
    print("  GET  /docs        → Swagger UI")
    print("Press Ctrl+C to stop.\n")
    uvicorn.run(app, host=host, port=port)


@app.get("/")
def subscription():
    """Plain-text subscription: one VLESS link per line."""
    return PlainTextResponse("\n".join(_vless_links))
