"""Dev-only reverse proxy: forwards /web/* to the customer Vite dev server
(frontend-customer:5174) and /app/* to the dashboard Vite dev server
(frontend:5173).

Why we need this in dev:
  - Both front ends run as their own services for Vite's hot-reload dev
    ergonomics.
  - Twilio sandbox + ngrok free tier give us one public domain. Having
    the api host both front ends' URLs avoids needing extra public
    tunnels.
  - In production, a real reverse proxy (nginx, Caddy) will do this same
    routing in front of the api and both built bundles — this code is a
    dev convenience that mimics that behaviour without adding more
    containers.

Two proxied prefixes:

  /web/*  → frontend-customer:5174   the customer ordering + registration app
  /app/*  → frontend:5173            the owner dashboard

Both forward the path *verbatim*. That only works because each Vite
config declares a matching `base` — '/web/' and '/app/' respectively —
so the dev server expects requests under its own prefix. Stripping the
prefix would mismatch Vite's base and break asset URLs.

The /app prefix exists specifically so the owner-notification WhatsApp
card can carry a tappable link to the approvals page. Without it the
dashboard is unreachable through the single ngrok tunnel, and the card's
button 404s on a phone.

HMR (Vite's WebSocket) is NOT proxied — dev edits hot-reload only when
accessing each app directly on its own port. Through the proxy you'd
need to manually reload. Acceptable trade for dev simplicity.
"""

import httpx
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["web-proxy"])

# Targets — the Vite dev containers, reached via docker network DNS.
# These are the service names in docker-compose.yml.
CUSTOMER_DEV_TARGET = "http://frontend-customer:5174"
DASHBOARD_DEV_TARGET = "http://frontend:5173"

# Headers we strip when forwarding — these are connection-level and would
# confuse the dev server or break streaming. We also strip 'host' because
# httpx sets it from the URL; otherwise we'd send the original request's
# host (localhost:8000) to the upstream and confuse Vite's host checks.
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


async def _proxy(request: Request, target_base: str) -> Response:
    """Forward the request to a Vite dev server, preserving the original
    path so that server's configured `base` matches correctly."""
    target = f"{target_base}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }

    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            content=body,
            follow_redirects=False,
        )

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


# Each prefix needs three routes: bare (no trailing slash), trailing
# slash, and the catch-all. FastAPI's path:path matcher doesn't capture
# the empty string, hence the dedicated bare and slash cases.

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


# === /web → customer app ===================================================


@router.api_route("/web", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_customer_bare(request: Request) -> Response:
    return await _proxy(request, CUSTOMER_DEV_TARGET)


@router.api_route("/web/", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_customer_slash(request: Request) -> Response:
    return await _proxy(request, CUSTOMER_DEV_TARGET)


@router.api_route("/web/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_to_customer_app(path: str, request: Request) -> Response:
    return await _proxy(request, CUSTOMER_DEV_TARGET)


# === /app → owner dashboard ================================================


@router.api_route("/app", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_dashboard_bare(request: Request) -> Response:
    return await _proxy(request, DASHBOARD_DEV_TARGET)


@router.api_route("/app/", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_dashboard_slash(request: Request) -> Response:
    return await _proxy(request, DASHBOARD_DEV_TARGET)


@router.api_route("/app/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
async def proxy_to_dashboard(path: str, request: Request) -> Response:
    return await _proxy(request, DASHBOARD_DEV_TARGET)
