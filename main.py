import os
import time
import ssl
import socket
from datetime import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
import httpx

# ====== CONFIG ======
# Pon aquí tu wallet de Base (la que ya tienes)
PAY_TO = os.getenv("PAY_TO_WALLET", "0x71571bd0b9e8407341d58a3fe4327f8337419b0c")  # <-- CAMBIA ESTO

# USDC en Base mainnet
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NETWORK = "eip155:8453"  # Base

# Precios en USDC (6 decimales): 0.004 = 4000
PRICES = {
    "uptime": 4000,      # 0.004 USDC
    "ssl": 5000,         # 0.005 USDC
    "metadata": 8000,    # 0.008 USDC
}

app = FastAPI(
    title="Agent Microservices",
    description="Uptime, SSL and metadata checks for AI agents. Pay per call with x402 (USDC on Base).",
    version="0.2.0",
)


class UrlRequest(BaseModel):
    url: HttpUrl
    timeout: int = 8


def x402_challenge(service: str) -> JSONResponse:
    amount = PRICES[service]
    body = {
        "x402Version": 2,
        "error": "Payment required",
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "asset": USDC_BASE,
                "amount": str(amount),
                "payTo": PAY_TO,
                "maxTimeoutSeconds": 300,
                "extra": {
                    "service": service,
                    "price_usdc": amount / 1_000_000,
                },
            }
        ],
    }
    return JSONResponse(status_code=402, content=body)


def has_payment(request: Request) -> bool:
    """MVP: acepta si viene cabecera de pago o modo test.
    Más adelante se verificará la firma on-chain con un facilitator.
    """
    if request.headers.get("x-payment") or request.headers.get("payment-signature"):
        return True
    # Modo test (solo para que pruebes tú): X-Test-Key: test
    if request.headers.get("x-test-key") == "test":
        return True
    return False


@app.get("/")
def root():
    return {
        "status": "online",
        "version": "0.2.0",
        "protocol": "x402",
        "network": "Base",
        "payTo": PAY_TO,
        "services": {
            "uptime": {"path": "/uptime", "price_usdc": 0.004, "method": "POST"},
            "ssl": {"path": "/ssl", "price_usdc": 0.005, "method": "POST"},
            "metadata": {"path": "/metadata", "price_usdc": 0.008, "method": "POST"},
        },
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@app.get("/.well-known/x402")
def well_known_x402():
    """Manifest para crawlers / directorios x402."""
    return {
        "name": "Agent Microservices",
        "description": "Cheap uptime, SSL expiry and page metadata checks for AI agents",
        "version": "0.2.0",
        "network": NETWORK,
        "asset": USDC_BASE,
        "payTo": PAY_TO,
        "endpoints": [
            {"path": "/uptime", "method": "POST", "price": "0.004", "description": "URL uptime check"},
            {"path": "/ssl", "method": "POST", "price": "0.005", "description": "SSL certificate expiry"},
            {"path": "/metadata", "method": "POST", "price": "0.008", "description": "Page title and description"},
        ],
    }


# ---- GET ready (validadores / marketplaces) ----
@app.get("/uptime")
def uptime_ready():
    return {"status": "ready", "service": "uptime", "price_usdc": 0.004, "pay": "x402"}


@app.get("/ssl")
def ssl_ready():
    return {"status": "ready", "service": "ssl", "price_usdc": 0.005, "pay": "x402"}


@app.get("/metadata")
def metadata_ready():
    return {"status": "ready", "service": "metadata", "price_usdc": 0.008, "pay": "x402"}


# ---- POST pagados ----
@app.post("/uptime")
async def check_uptime(req: UrlRequest, request: Request):
    if not has_payment(request):
        return x402_challenge("uptime")

    url = str(req.url)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=req.timeout) as client:
            r = await client.get(url)
        ms = int((time.perf_counter() - start) * 1000)
        return {
            "ok": r.status_code < 400,
            "status_code": r.status_code,
            "response_time_ms": ms,
            "final_url": str(r.url),
        }
    except Exception as e:
        ms = int((time.perf_counter() - start) * 1000)
        return {"ok": False, "status_code": 0, "response_time_ms": ms, "error": str(e)}


@app.post("/ssl")
async def check_ssl(req: UrlRequest, request: Request):
    if not has_payment(request):
        return x402_challenge("ssl")

    parsed = urlparse(str(req.url))
    host = parsed.hostname
    if not host:
        raise HTTPException(400, "Invalid URL")
    port = parsed.port or 443
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=req.timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        # Convertir fecha
        expire_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        days_left = (expire_dt - datetime.utcnow()).days
        return {
            "ok": True,
            "host": host,
            "expires": not_after,
            "days_left": days_left,
            "expired": days_left < 0,
        }
    except Exception as e:
        return {"ok": False, "host": host, "error": str(e)}


@app.post("/metadata")
async def get_metadata(req: UrlRequest, request: Request):
    if not has_payment(request):
        return x402_challenge("metadata")

    url = str(req.url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=req.timeout) as client:
            r = await client.get(url)
        text = r.text[:50000]
        title = ""
        desc = ""
        # extracción simple
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
        m = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            text,
            re.I | re.S,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
                text,
                re.I | re.S,
            )
        if m:
            desc = re.sub(r"\s+", " ", m.group(1)).strip()[:500]
        return {
            "ok": True,
            "url": str(r.url),
            "status_code": r.status_code,
            "title": title,
            "description": desc,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}