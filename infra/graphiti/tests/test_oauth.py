"""Tests for sidecar/oauth.py — the bundled OAuth 2.1 AS (D-048).

These exercise the full register -> authorize -> token -> /mcp flow with a
FastAPI TestClient. No Neo4j or Graphiti involved — oauth.py has no graph
dependency, so the suite stays fast.
"""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidecar.oauth import (
    OAuthConfig,
    OAuthMiddleware,
    OAuthProvider,
    _b64url,
    verify_pkce,
)

ISSUER = "https://test.example"
PASSWORD = "operator-pw-123"
REDIRECT = "https://claude.example/callback"


def make_client(tmp_path, *, enabled=True, password=PASSWORD, static_token=None):
    """Build a FastAPI app with the OAuth router + middleware and a stub /mcp."""
    cfg = OAuthConfig(
        enabled=enabled,
        password=password,
        issuer_override=ISSUER,
        state_path=tmp_path / "oauth_state.json",
        static_token=static_token,
    )
    provider = OAuthProvider(cfg)
    app = FastAPI()
    if provider.enabled:
        app.include_router(provider.router())
    app.add_middleware(OAuthMiddleware, provider=provider)

    @app.post("/mcp")
    async def mcp():
        return {"mcp": "reached"}

    @app.get("/mcp-healthcheck")
    async def healthcheck():
        return {"hc": "ok"}

    return TestClient(app), provider


def pkce_pair():
    verifier = "v" * 64
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def register(client) -> str:
    resp = client.post("/oauth/register", json={
        "redirect_uris": [REDIRECT],
        "client_name": "Claude Test",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def get_code(client, client_id, challenge) -> str:
    """Run the consent POST and return the issued authorization code."""
    resp = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert location.startswith(REDIRECT)
    assert "state=xyz" in location
    return location.split("code=")[1].split("&")[0]


# ── PKCE ──────────────────────────────────────────────────────────────────────

def test_verify_pkce_roundtrip():
    verifier, challenge = pkce_pair()
    assert verify_pkce(verifier, challenge) is True


def test_verify_pkce_rejects_wrong_verifier():
    _, challenge = pkce_pair()
    assert verify_pkce("not-the-verifier", challenge) is False
    assert verify_pkce("", challenge) is False


# ── discovery metadata ────────────────────────────────────────────────────────

def test_authorization_server_metadata(tmp_path):
    client, _ = make_client(tmp_path)
    meta = client.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"] == ISSUER
    assert meta["authorization_endpoint"] == f"{ISSUER}/oauth/authorize"
    assert meta["token_endpoint"] == f"{ISSUER}/oauth/token"
    assert meta["registration_endpoint"] == f"{ISSUER}/oauth/register"
    assert meta["code_challenge_methods_supported"] == ["S256"]


def test_protected_resource_metadata(tmp_path):
    client, _ = make_client(tmp_path)
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        meta = client.get(path).json()
        assert meta["resource"] == f"{ISSUER}/mcp"
        assert meta["authorization_servers"] == [ISSUER]


# ── dynamic client registration ───────────────────────────────────────────────

def test_register_issues_client_id(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    assert client_id.startswith("mikai-")


def test_register_rejects_missing_redirect_uris(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/oauth/register", json={"client_name": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_redirect_uri"


# ── /mcp gate ──────────────────────────────────────────────────────────────────

def test_mcp_unauthenticated_returns_401_with_challenge(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/mcp")
    assert resp.status_code == 401
    www = resp.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www
    assert "/.well-known/oauth-protected-resource" in www


def test_mcp_healthcheck_is_never_gated(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/mcp-healthcheck").status_code == 200


# ── full authorization-code flow ──────────────────────────────────────────────

def test_full_flow_grants_working_token(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    verifier, challenge = pkce_pair()

    # consent page renders
    page = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": client_id,
        "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "xyz",
    })
    assert page.status_code == 200
    assert "Operator password" in page.text

    code = get_code(client, client_id, challenge)

    tok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": verifier,
    })
    assert tok.status_code == 200, tok.text
    body = tok.json()
    assert body["token_type"] == "Bearer"
    access = body["access_token"]

    # token unlocks /mcp
    ok = client.post("/mcp", headers={"Authorization": f"Bearer {access}"})
    assert ok.status_code == 200
    assert ok.json() == {"mcp": "reached"}

    # refresh token mints a fresh, working access token
    refreshed = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": body["refresh_token"],
    })
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]
    assert client.post(
        "/mcp", headers={"Authorization": f"Bearer {new_access}"}
    ).status_code == 200


def test_wrong_password_does_not_issue_code(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    _, challenge = pkce_pair()
    resp = client.post("/oauth/authorize", data={
        "response_type": "code", "client_id": client_id,
        "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "password": "wrong",
    }, follow_redirects=False)
    assert resp.status_code == 401
    assert "location" not in resp.headers


def test_pkce_mismatch_rejects_token(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    _, challenge = pkce_pair()
    code = get_code(client, client_id, challenge)
    resp = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": "wrong-verifier",
    })
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


def test_authorization_code_is_single_use(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    verifier, challenge = pkce_pair()
    code = get_code(client, client_id, challenge)
    data = {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": verifier,
    }
    assert client.post("/oauth/token", data=data).status_code == 200
    # second exchange of the same code must fail
    assert client.post("/oauth/token", data=data).status_code == 400


def test_authorize_rejects_unknown_client(tmp_path):
    client, _ = make_client(tmp_path)
    _, challenge = pkce_pair()
    resp = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": "mikai-nope",
        "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    assert resp.status_code == 400
    assert "Unknown client_id" in resp.text


def test_tampered_token_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    client_id = register(client)
    verifier, challenge = pkce_pair()
    code = get_code(client, client_id, challenge)
    access = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": verifier,
    }).json()["access_token"]
    tampered = access[:-4] + ("aaaa" if not access.endswith("aaaa") else "bbbb")
    resp = client.post("/mcp", headers={"Authorization": f"Bearer {tampered}"})
    assert resp.status_code == 401


# ── non-OAuth modes ────────────────────────────────────────────────────────────

def test_static_token_mode(tmp_path):
    client, _ = make_client(tmp_path, enabled=False, static_token="secret-tok")
    assert client.post("/mcp").status_code == 401
    ok = client.post("/mcp", headers={"Authorization": "Bearer secret-tok"})
    assert ok.status_code == 200
    bad = client.post("/mcp", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    # no OAuth advertised when only a static token is configured
    assert "www-authenticate" not in bad.headers


def test_open_mode_passthrough(tmp_path):
    client, _ = make_client(tmp_path, enabled=False, static_token=None)
    assert client.post("/mcp").status_code == 200


def test_signing_secret_persists_across_restart(tmp_path):
    """A new provider over the same state file keeps tokens valid."""
    client, _ = make_client(tmp_path)
    client_id = register(client)
    verifier, challenge = pkce_pair()
    code = get_code(client, client_id, challenge)
    access = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": verifier,
    }).json()["access_token"]

    # simulate a restart: brand-new app + provider, same state_path
    client2, _ = make_client(tmp_path)
    resp = client2.post("/mcp", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 200
