from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import httpx
import time
import ssl
import socket
from datetime import datetime
from urllib.parse import urlparse

app = FastAPI(
    title="Agent Microservices",
    description="Servicios baratos y fiables para agentes AI",
    version="0.1.0"
)

class UrlRequest(BaseModel):
    url: HttpUrl
    timeout: int = 8

@app.get("/")
def root():
    return {
        "status": "online",
        "version": "0.1.0",
        "services": {
            "uptime": {"endpoint": "/uptime", "price": "0.004 USDC"},
            "ssl": {"endpoint": "/ssl", "price": "0.005 USDC"},
            "metadata": {"endpoint": "/metadata", "price": "0.008 USDC"}
        }
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/uptime")
async def check_uptime(req: UrlRequest):
    start = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=req.timeout,
            follow_redirects=True,
            headers={"User-Agent": "AgentMicroservices/0.1"}
        ) as client:
            response = await client.get(str(req.url))
            elapsed = round((time.time() - start) * 1000)

            return {
                "url": str(req.url),
                "status_code": response.status_code,
                "ok": 200 <= response.status_code < 400,
                "response_time_ms": elapsed,
                "final_url": str(response.url)
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout al conectar con la URL")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/ssl")
async def check_ssl(req: UrlRequest):
    try:
        parsed = urlparse(str(req.url))
        hostname = parsed.hostname
        if not hostname:
            raise HTTPException(status_code=400, detail="URL inválida")

        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=req.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expire_str = cert["notAfter"]
                expire_date = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z")
                days_left = (expire_date - datetime.utcnow()).days

                return {
                    "hostname": hostname,
                    "expires": expire_date.isoformat() + "Z",
                    "days_left": days_left,
                    "ok": days_left > 14
                }
    except socket.timeout:
        raise HTTPException(status_code=504, detail="Timeout al comprobar SSL")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/metadata")
async def get_metadata(req: UrlRequest):
    try:
        async with httpx.AsyncClient(
            timeout=req.timeout,
            follow_redirects=True,
            headers={"User-Agent": "AgentMicroservices/0.1"}
        ) as client:
            response = await client.get(str(req.url))
            text = response.text[:20000].lower()

            title = ""
            description = ""

            # Title
            if "<title>" in text:
                start = text.find("<title>") + 7
                end = text.find("</title>", start)
                if end > start:
                    title = response.text[start:end].strip()[:250]

            # Meta description
            if 'name="description"' in text or "name='description'" in text:
                for marker in ['name="description"', "name='description'"]:
                    if marker in text:
                        pos = text.find(marker)
                        content_pos = text.find("content=", pos)
                        if content_pos > 0:
                            quote = text[content_pos + 8]
                            start = content_pos + 9
                            end = text.find(quote, start)
                            if end > start:
                                description = response.text[start:end].strip()[:300]
                        break

            return {
                "url": str(req.url),
                "status_code": response.status_code,
                "title": title,
                "description": description
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout al obtener metadata")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.get("/uptime")
def uptime_ready():
    return {"status": "ready", "service": "uptime", "method": "POST with body {\"url\": \"https://example.com\"}"}

@app.get("/ssl")
def ssl_ready():
    return {"status": "ready", "service": "ssl", "method": "POST with body {\"url\": \"https://example.com\"}"}

@app.get("/metadata")
def metadata_ready():
    return {"status": "ready", "service": "metadata", "method": "POST with body {\"url\": \"https://example.com\"}"}