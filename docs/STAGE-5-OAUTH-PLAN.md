# Stage 5 — MCP OAuth Layer (implementation plan)

> Decision record: `docs/DECISIONS.md` → **D-048**. Branch: `feat/stage-5-mcp-oauth`.
> Goal: make MIKAI's `/mcp` endpoint addable as a Claude.ai web + Claude mobile
> Custom Connector by implementing the OAuth 2.1 flow Claude's connector requires.

## Why

Claude.ai's connector backend, as of 2026-05, refuses an MCP server that has no
OAuth discovery endpoints (D-044 → D-048). The MCP handshake itself already
works; only the OAuth step is missing. This stage adds it.

## What Claude.ai's connector runs

```
GET  /.well-known/oauth-protected-resource     → which AS protects /mcp
GET  /.well-known/oauth-authorization-server   → authorize/token/register URLs
POST /oauth/register                           → Dynamic Client Registration (RFC 7591)
GET  /oauth/authorize  → operator password page → 302 back with ?code=
POST /oauth/token      → code + PKCE verifier   → JWT access + refresh tokens
POST /mcp  Authorization: Bearer <jwt>          → validated on every call
```

## Design (single-user, bundled AS)

- **Public clients + PKCE (S256)** — no client secrets.
- **Stateless JWT tokens** (HS256): access TTL 1h, refresh TTL 30d.
- **One credential**: `MIKAI_OAUTH_PASSWORD`, checked at the `/authorize` consent page.
- **Persistence**: JWT signing secret + registered DCR clients in a JSON file on a
  Docker volume (`/data/oauth_state.json`). Authorization codes are in-memory,
  5-minute TTL — a restart mid-flow just means re-authorizing.
- **Issuer URL** derived per-request from `X-Forwarded-Proto` + `Host` (works
  through any tunnel), overridable with `MIKAI_OAUTH_ISSUER`.

## Files

| File | Change |
|---|---|
| `infra/graphiti/sidecar/oauth.py` | **New.** `OAuthConfig`, `OAuthStore`, `OAuthProvider` (router + token mint/verify), `OAuthMiddleware`. |
| `infra/graphiti/sidecar/main.py` | Replace `MCPBearerAuthMiddleware` with `OAuthMiddleware`; mount the OAuth router; report OAuth status in `/mcp-healthcheck`. |
| `infra/graphiti/docker-compose.yml` | Pass `MIKAI_OAUTH_*` env; add `oauth_data` volume at `/data`. |
| `infra/graphiti/.env` / `.env.example` | Add `MIKAI_OAUTH_ENABLED`, `MIKAI_OAUTH_PASSWORD`, `MIKAI_OAUTH_ISSUER`. |
| `infra/graphiti/tests/test_oauth.py` | **New.** PKCE, DCR, code→token, token verification, password gate, middleware 401. |
| `scripts/preflight.sh` | Add an OAuth-metadata reachability check. |

## Flag behavior

`MIKAI_OAUTH_ENABLED` unset → sidecar unchanged (open, or static `MIKAI_MCP_TOKEN`).
`MIKAI_OAUTH_ENABLED=1` → OAuth routes live, `/mcp` requires a valid token, an
unauthenticated `/mcp` request returns `401` + `WWW-Authenticate` pointing at the
protected-resource metadata.

## Verification

1. Unit tests (`pytest tests/test_oauth.py`) — flow correctness, runnable offline.
2. Local end-to-end — full `register → authorize → token → /mcp` against the
   running sidecar with a JWT.
3. Live — add the connector in Claude.ai web; confirm the consent page, then a
   tool call in-chat. This is the only true test and needs Brian in the loop.
