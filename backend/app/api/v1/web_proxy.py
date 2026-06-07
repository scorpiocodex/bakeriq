"""Dev-only reverse proxy: forwards /web/* requests to the customer Vite
dev server (port 5174 inside the docker network).

Why we need this in dev:
  - The customer-facing web app runs as its own service (frontend-customer
    on port 5174) for Vite's hot-reload dev ergonomics.
  - Twilio sandbox + ngrok free tier give us one public domain. Having
    the api host the customer app's URL avoids needing a second public
    tunnel.
  - In production, a real reverse proxy (nginx, Caddy) will do this same
    routing in front of both the api and the built customer app — this
    code is a dev convenience that mimics that behaviour without adding
    a third container.

How it works:
  - GET /web/                     → proxied to frontend-customer:5174/web/
  - GET /web/reorder/<token>      → proxied to frontend-customer:5174/web/reorder/<token>
  - GET /web/assets/index-abc.js  → proxied to frontend-customer:5174/web/assets/index-abc.js

The path is forwarded *verbatim* — Vite is configured with base='/web/'
so it expects requests under /web/. Stripping the prefix would mismatch
Vite's expected base and trigger redirects.

HMR (Vite's WebSocket) is NOT proxied — dev edits hot-reload only when
accessing the customer app directly at localhost:5174. Through the proxy
you'd need to manually reload. Acceptable trade for dev simplicity.
"""

import httpx
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["web-proxy"])

# Target — the customer Vite dev container, reached via docker network DNS.
# "frontend-customer" is the service name in docker-compose.yml.
CUSTOMER_DEV_TARGET = "http://frontend-customer:5174"

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


async def _proxy(request: Request) -> Response:
    """Forward the request to the customer dev server, preserving the
    original path so Vite's base='/web/' matches correctly."""
    target = f"{CUSTOMER_DEV_TARGET}{request.url.path}"
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


# We need a route for /web (no trailing slash), /web/ (trailing slash),
# and /web/<anything>. FastAPI's path:path matcher doesn't capture the
# empty string, hence the dedicated route for the bare and slash cases.


@router.api_route(
    "/web",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_root_bare(request: Request) -> Response:
    return await _proxy(request)


@router.api_route(
    "/web/",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_root_slash(request: Request) -> Response:
    return await _proxy(request)


@router.api_route(
    "/web/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_to_customer_app(path: str, request: Request) -> Response:
    return await _proxy(request)
