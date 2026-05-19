"""MIKAI sidecar — minimal OAuth 2.1 Authorization Server for MCP connector auth.

Why this exists: Claude.ai web and Claude mobile connect to an MCP server only
via OAuth 2.0 + Dynamic Client Registration (D-044 finding 4, D-048). This
module makes the sidecar its own single-user Authorization Server + Resource
Server, co-located with the /mcp endpoint.

Scope is deliberately minimal:
  - one user, gated by a single operator password (MIKAI_OAUTH_PASSWORD)
  - public clients with PKCE (S256) — no client secrets
  - stateless JWT access/refresh tokens (HS256)
  - Dynamic Client Registration (RFC 7591); clients persisted to a JSON file
  - authorization codes held in memory with a short TTL

Activated by MIKAI_OAUTH_ENABLED=1. When unset, the sidecar keeps its prior
behavior (open, or static MIKAI_MCP_TOKEN bearer) and none of these routes —
nor the /mcp token check — are active.

Endpoints (mounted at the site root by main.py):
  GET  /.well-known/oauth-protected-resource     RFC 9728
  GET  /.well-known/oauth-authorization-server   RFC 8414
  POST /oauth/register                           RFC 7591 Dynamic Client Registration
  GET  /oauth/authorize                          operator consent / password page
  POST /oauth/authorize                          password check -> authorization code
  POST /oauth/token                              code / refresh -> JWT
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import time
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("mikai-graphiti")

ACCESS_TTL = 3600           # access token lifetime — 1 hour
REFRESH_TTL = 30 * 86400    # refresh token lifetime — 30 days
CODE_TTL = 300              # authorization code lifetime — 5 minutes
SCOPE = "mcp"
WRONG_PASSWORD_DELAY = 1.0  # seconds — blunts brute force on the consent page


# ── config ───────────────────────────────────────────────────────────────────

@dataclass
class OAuthConfig:
    """Resolved from the environment once at startup."""

    enabled: bool
    password: str
    issuer_override: str | None
    state_path: Path
    static_token: str | None  # MIKAI_MCP_TOKEN — accepted alongside OAuth JWTs

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        enabled = os.environ.get("MIKAI_OAUTH_ENABLED", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        return cls(
            enabled=enabled,
            password=os.environ.get("MIKAI_OAUTH_PASSWORD", ""),
            issuer_override=(os.environ.get("MIKAI_OAUTH_ISSUER") or "").strip() or None,
            state_path=Path(
                os.environ.get("MIKAI_OAUTH_STATE", "/data/oauth_state.json")
            ),
            static_token=(os.environ.get("MIKAI_MCP_TOKEN") or "").strip() or None,
        )


# ── persistence ──────────────────────────────────────────────────────────────

class OAuthStore:
    """Persists the JWT signing secret + registered DCR clients to a JSON file.

    Authorization codes are kept in memory only — they live for CODE_TTL
    seconds, so a sidecar restart mid-flow just means the operator re-authorizes.
    """

    def __init__(self, path: Path):
        self.path = path
        self.secret: str = ""
        self.clients: dict[str, dict] = {}
        self._codes: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            self.secret = data.get("secret", "")
            self.clients = data.get("clients", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        if not self.secret:
            # First boot, or the state file could not be read. Generate a
            # signing secret and try to persist it so tokens survive restarts.
            self.secret = secrets.token_urlsafe(48)
            self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"secret": self.secret, "clients": self.clients}, indent=2)
            )
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning(
                "oauth: could not persist state to %s (%s) — tokens will not "
                "survive a restart", self.path, exc,
            )

    def add_client(self, client: dict) -> None:
        self.clients[client["client_id"]] = client
        self._save()

    def get_client(self, client_id: str) -> dict | None:
        return self.clients.get(client_id)

    def put_code(self, code: str, payload: dict) -> None:
        self._codes[code] = payload

    def pop_code(self, code: str) -> dict | None:
        """Single-use: return the code payload and remove it, or None if the
        code is unknown or expired. Also GCs other expired codes."""
        payload = self._codes.pop(code, None)
        now = time.time()
        for stale in [k for k, v in self._codes.items() if v["exp"] < now]:
            self._codes.pop(stale, None)
        if not payload or payload["exp"] < now:
            return None
        return payload


# ── helpers ──────────────────────────────────────────────────────────────────

def _b64url(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """RFC 7636 S256: BASE64URL(SHA256(verifier)) must equal the challenge."""
    if not code_verifier or not code_challenge:
        return False
    expected = _b64url(hashlib.sha256(code_verifier.encode()).digest())
    return hmac.compare_digest(expected, code_challenge)


async def _form(request: Request) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body without depending on a
    multipart parser."""
    body = (await request.body()).decode("utf-8", "replace")
    return dict(parse_qsl(body))


# ── provider ─────────────────────────────────────────────────────────────────

class OAuthProvider:
    """Authorization Server + Resource Server logic for the sidecar."""

    def __init__(self, config: OAuthConfig):
        self.cfg = config
        self.store: OAuthStore | None = (
            OAuthStore(config.state_path) if config.enabled else None
        )
        if config.enabled and not config.password:
            logger.warning(
                "oauth: MIKAI_OAUTH_ENABLED is set but MIKAI_OAUTH_PASSWORD is "
                "empty — the consent page will reject every login"
            )

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    @property
    def active(self) -> bool:
        """True when /mcp should require a token (OAuth on, or a static token)."""
        return self.cfg.enabled or bool(self.cfg.static_token)

    # ── issuer / token plumbing ──────────────────────────────────────────────

    def base_url(self, request: Request) -> str:
        """The public origin. Derived from forwarded headers so it works
        through any tunnel; overridable with MIKAI_OAUTH_ISSUER."""
        if self.cfg.issuer_override:
            return self.cfg.issuer_override.rstrip("/")
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("host", request.url.netloc)
        return f"{proto}://{host}"

    def _mint(self, sub: str, base: str, typ: str, ttl: int) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "sub": sub,
                "aud": f"{base}/mcp",
                "iss": base,
                "typ": typ,
                "scope": SCOPE,
                "iat": now,
                "exp": now + ttl,
            },
            self.store.secret,
            algorithm="HS256",
        )

    def _decode(self, token: str, base: str, typ: str) -> dict | None:
        try:
            claims = jwt.decode(
                token,
                self.store.secret,
                algorithms=["HS256"],
                audience=f"{base}/mcp",
                issuer=base,
            )
        except jwt.PyJWTError:
            return None
        return claims if claims.get("typ") == typ else None

    def authenticate(self, request: Request) -> bool:
        """True if the request carries a credential valid for /mcp."""
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:]
        if self.cfg.static_token and hmac.compare_digest(token, self.cfg.static_token):
            return True
        if not self.cfg.enabled:
            return False
        return self._decode(token, self.base_url(request), "access") is not None

    # ── route handlers ───────────────────────────────────────────────────────

    def router(self) -> APIRouter:
        """The OAuth endpoints. Mounted at the site root by main.py."""
        r = APIRouter()

        @r.get("/.well-known/oauth-authorization-server")
        async def authorization_server_metadata(request: Request):  # RFC 8414
            base = self.base_url(request)
            return JSONResponse({
                "issuer": base,
                "authorization_endpoint": f"{base}/oauth/authorize",
                "token_endpoint": f"{base}/oauth/token",
                "registration_endpoint": f"{base}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "scopes_supported": [SCOPE],
            })

        async def protected_resource_metadata(request: Request):  # RFC 9728
            base = self.base_url(request)
            return JSONResponse({
                "resource": f"{base}/mcp",
                "authorization_servers": [base],
                "scopes_supported": [SCOPE],
                "bearer_methods_supported": ["header"],
            })

        # Claude.ai probes the bare path; the RFC also allows a resource-path
        # suffix. Serve both so discovery succeeds either way.
        r.add_api_route(
            "/.well-known/oauth-protected-resource",
            protected_resource_metadata, methods=["GET"],
        )
        r.add_api_route(
            "/.well-known/oauth-protected-resource/mcp",
            protected_resource_metadata, methods=["GET"],
        )

        @r.post("/oauth/register")
        async def register(request: Request):  # RFC 7591 Dynamic Client Registration
            try:
                body = await request.json()
            except (json.JSONDecodeError, ValueError):
                return JSONResponse(status_code=400, content={
                    "error": "invalid_client_metadata",
                    "error_description": "request body must be JSON",
                })
            redirect_uris = body.get("redirect_uris") or []
            if not redirect_uris or not all(isinstance(u, str) for u in redirect_uris):
                return JSONResponse(status_code=400, content={
                    "error": "invalid_redirect_uri",
                    "error_description": "redirect_uris must be a non-empty list of strings",
                })
            client = {
                "client_id": "mikai-" + secrets.token_urlsafe(16),
                "redirect_uris": redirect_uris,
                "client_name": str(body.get("client_name", "unknown"))[:200],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_id_issued_at": int(time.time()),
            }
            self.store.add_client(client)
            logger.info(
                "oauth: registered client %s (%s)",
                client["client_id"], client["client_name"],
            )
            return JSONResponse(status_code=201, content=client)

        @r.get("/oauth/authorize")
        async def authorize_get(request: Request):
            params = dict(request.query_params)
            err = self._validate_authorize(params)
            if err:
                return HTMLResponse(self._error_page(err), status_code=400)
            return HTMLResponse(self._consent_page(params))

        @r.post("/oauth/authorize")
        async def authorize_post(request: Request):
            form = await _form(request)
            password = form.pop("password", "")
            err = self._validate_authorize(form)
            if err:
                return HTMLResponse(self._error_page(err), status_code=400)
            if not self.cfg.password or not hmac.compare_digest(
                password, self.cfg.password
            ):
                await asyncio.sleep(WRONG_PASSWORD_DELAY)
                return HTMLResponse(
                    self._consent_page(form, error="Incorrect password."),
                    status_code=401,
                )
            code = secrets.token_urlsafe(32)
            self.store.put_code(code, {
                "client_id": form["client_id"],
                "redirect_uri": form["redirect_uri"],
                "code_challenge": form["code_challenge"],
                "exp": time.time() + CODE_TTL,
            })
            query = {"code": code}
            if form.get("state"):
                query["state"] = form["state"]
            sep = "&" if "?" in form["redirect_uri"] else "?"
            return RedirectResponse(
                f"{form['redirect_uri']}{sep}{urlencode(query)}", status_code=302,
            )

        @r.post("/oauth/token")
        async def token(request: Request):
            form = await _form(request)
            base = self.base_url(request)
            grant = form.get("grant_type")
            if grant == "authorization_code":
                return self._grant_code(form, base)
            if grant == "refresh_token":
                return self._grant_refresh(form, base)
            return JSONResponse(status_code=400, content={
                "error": "unsupported_grant_type",
            })

        return r

    # ── validation + grants ──────────────────────────────────────────────────

    def _validate_authorize(self, p: dict) -> str | None:
        """Return a human-readable error string, or None if the request is OK."""
        if p.get("response_type") != "code":
            return "Unsupported response_type — only 'code' is allowed."
        client = self.store.get_client(p.get("client_id", ""))
        if not client:
            return "Unknown client_id — the client must register first."
        if p.get("redirect_uri") not in client["redirect_uris"]:
            return "redirect_uri is not registered for this client."
        if p.get("code_challenge_method") != "S256":
            return "code_challenge_method must be 'S256'."
        if not p.get("code_challenge"):
            return "Missing PKCE code_challenge."
        return None

    def _grant_code(self, form: dict, base: str) -> JSONResponse:
        payload = self.store.pop_code(form.get("code", ""))
        if not payload:
            return JSONResponse(status_code=400, content={
                "error": "invalid_grant",
                "error_description": "authorization code is unknown or expired",
            })
        if form.get("client_id") != payload["client_id"] or (
            form.get("redirect_uri") != payload["redirect_uri"]
        ):
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        if not verify_pkce(form.get("code_verifier", ""), payload["code_challenge"]):
            return JSONResponse(status_code=400, content={
                "error": "invalid_grant",
                "error_description": "PKCE verification failed",
            })
        return self._token_response(payload["client_id"], base)

    def _grant_refresh(self, form: dict, base: str) -> JSONResponse:
        claims = self._decode(form.get("refresh_token", ""), base, "refresh")
        if not claims:
            return JSONResponse(status_code=400, content={"error": "invalid_grant"})
        return self._token_response(claims["sub"], base)

    def _token_response(self, client_id: str, base: str) -> JSONResponse:
        return JSONResponse({
            "access_token": self._mint(client_id, base, "access", ACCESS_TTL),
            "token_type": "Bearer",
            "expires_in": ACCESS_TTL,
            "refresh_token": self._mint(client_id, base, "refresh", REFRESH_TTL),
            "scope": SCOPE,
        })

    # ── HTML ─────────────────────────────────────────────────────────────────

    def _consent_page(self, params: dict, error: str | None = None) -> str:
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k, True)}" '
            f'value="{html.escape(v, True)}">'
            for k, v in params.items()
            if k != "password"
        )
        client = self.store.get_client(params.get("client_id", "")) if self.store else None
        client_name = html.escape(client["client_name"]) if client else "An application"
        err_html = (
            f'<p class="err">{html.escape(error)}</p>' if error else ""
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize MIKAI</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center;
         justify-content:center; background:#0d0d0f; color:#e8e8ea;
         font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  .card {{ width:340px; padding:32px; background:#17171a;
          border:1px solid #2a2a2e; border-radius:14px; }}
  h1 {{ margin:0 0 4px; font-size:18px; }}
  p.sub {{ margin:0 0 20px; color:#9a9aa0; font-size:13px; }}
  label {{ display:block; font-size:12px; color:#9a9aa0; margin-bottom:6px; }}
  input[type=password] {{ width:100%; box-sizing:border-box; padding:10px 12px;
          background:#0d0d0f; border:1px solid #2a2a2e; border-radius:8px;
          color:#e8e8ea; font-size:14px; }}
  button {{ width:100%; margin-top:16px; padding:11px; border:0;
          border-radius:8px; background:#e8e8ea; color:#0d0d0f;
          font-size:14px; font-weight:600; cursor:pointer; }}
  .err {{ color:#ff6b6b; font-size:13px; margin:12px 0 0; }}
</style></head><body>
<form class="card" method="post" action="/oauth/authorize">
  <h1>Authorize access to MIKAI</h1>
  <p class="sub">{client_name} is requesting access to your MIKAI
     knowledge graph. Enter your operator password to allow it.</p>
  {hidden}
  <label for="pw">Operator password</label>
  <input id="pw" type="password" name="password" autofocus
         autocomplete="current-password">
  {err_html}
  <button type="submit">Authorize</button>
</form></body></html>"""

    def _error_page(self, message: str) -> str:
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>MIKAI — authorization error</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center;
         justify-content:center; background:#0d0d0f; color:#e8e8ea;
         font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  .card {{ width:340px; padding:32px; background:#17171a;
          border:1px solid #2a2a2e; border-radius:14px; }}
  h1 {{ margin:0 0 8px; font-size:17px; color:#ff6b6b; }}
  p {{ margin:0; color:#9a9aa0; font-size:13px; }}
</style></head><body>
<div class="card"><h1>Authorization request rejected</h1>
<p>{html.escape(message)}</p></div></body></html>"""


# ── middleware ───────────────────────────────────────────────────────────────

class OAuthMiddleware(BaseHTTPMiddleware):
    """Gates /mcp. Replaces the old MCPBearerAuthMiddleware.

    - OAuth on  → requires a valid JWT access token (or the static token).
    - Static token only (OAuth off) → requires that bearer token.
    - Neither   → open passthrough (localhost-solo mode).

    Never touches non-/mcp paths, so the OAuth routes and /mcp-healthcheck
    stay reachable.
    """

    def __init__(self, app, provider: OAuthProvider):
        super().__init__(app)
        self.provider = provider

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not (path == "/mcp" or path.startswith("/mcp/")):
            return await call_next(request)

        p = self.provider
        if not p.active:
            return await call_next(request)
        if p.authenticate(request):
            return await call_next(request)

        headers = {}
        if p.enabled:
            base = p.base_url(request)
            headers["WWW-Authenticate"] = (
                f'Bearer resource_metadata='
                f'"{base}/.well-known/oauth-protected-resource"'
            )
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "error_description": "valid bearer token required"},
            headers=headers,
        )
