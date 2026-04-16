"""
Shared Graphiti client helpers for MIKAI.

One DeepSeekClient + PassthroughReranker + init_graphiti() used by every
surface that talks to the knowledge graph — the FastAPI sidecar, the Python
MCP server for Claude Desktop, the MCP ingestion daemon, and the script-level
importers. Keeping these in one place means a fix (e.g. to DeepSeek's
json_object handling) lands everywhere at once.

Consumers that live outside the sidecar/ package (top-level scripts, the
scripts/ directory) should add `infra/graphiti/` to sys.path before importing
this module — see the `_ensure_on_path()` helper below.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import typing
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.llm_client.client import Message
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

logger = logging.getLogger("mikai-graphiti-client")


# ── Helpers for scripts living outside the sidecar package ───────────────────


def ensure_sidecar_on_path() -> None:
    """Add `infra/graphiti/` to sys.path so `from sidecar.client import ...` works.

    Scripts in `infra/graphiti/scripts/` and the top-level `mcp_ingest.py` run
    with their own directory on sys.path but not the sidecar parent. This
    helper is idempotent and safe to call from any such script.
    """
    root = Path(__file__).resolve().parent.parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


# ── DeepSeek wrapper ─────────────────────────────────────────────────────────


class DeepSeekClient(OpenAIGenericClient):
    """DeepSeek-compatible client that uses json_object mode instead of json_schema.

    DeepSeek supports structured JSON output but not OpenAI's json_schema
    response_format type. This client puts the schema in the system prompt
    and uses json_object mode instead.
    """

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        from openai.types.chat import ChatCompletionMessageParam

        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == "user":
                openai_messages.append({"role": "user", "content": m.content})
            elif m.role == "system":
                openai_messages.append({"role": "system", "content": m.content})

        if response_model is not None:
            schema = response_model.model_json_schema()
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(schema, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            injected = False
            for i, msg in enumerate(openai_messages):
                if msg["role"] == "system":
                    openai_messages[i] = {
                        "role": "system",
                        "content": str(msg["content"]) + schema_instruction,
                    }
                    injected = True
                    break
            if not injected:
                openai_messages.insert(
                    0, {"role": "system", "content": schema_instruction}
                )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            result = response.choices[0].message.content or "{}"
            return json.loads(result)
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            raise


# ── Reranker ─────────────────────────────────────────────────────────────────


class PassthroughReranker(CrossEncoderClient):
    """No-op reranker — avoids a separate OpenAI cross-encoder dependency."""

    async def rank(
        self, query: str, passages: list[str]
    ) -> list[tuple[str, float]]:
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


# ── Graphiti factory ─────────────────────────────────────────────────────────


def _require_env(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        raise RuntimeError(f"{var} required")
    return val


def build_graphiti(
    *,
    neo4j_uri: str | None = None,
    neo4j_user: str | None = None,
    neo4j_password: str | None = None,
    deepseek_key: str | None = None,
    voyage_key: str | None = None,
    deepseek_model: str = "deepseek-chat",
    voyage_model: str = "voyage-3",
    max_tokens: int = 8192,
) -> Graphiti:
    """Construct (but do not initialize) a Graphiti client with MIKAI defaults."""
    neo4j_uri = neo4j_uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = neo4j_user or os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = (
        neo4j_password
        or os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")
    )
    deepseek_key = deepseek_key or _require_env("DEEPSEEK_API_KEY")
    voyage_key = voyage_key or _require_env("VOYAGE_API_KEY")

    llm_client = DeepSeekClient(
        config=LLMConfig(
            api_key=deepseek_key,
            model=deepseek_model,
            small_model=deepseek_model,
            base_url="https://api.deepseek.com",
        ),
        max_tokens=max_tokens,
    )

    embedder = VoyageAIEmbedder(
        config=VoyageAIEmbedderConfig(
            api_key=voyage_key,
            model=voyage_model,
        )
    )

    return Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=PassthroughReranker(),
    )


async def init_graphiti(*, build_indices: bool = True, **kwargs) -> Graphiti:
    """Construct a Graphiti client and optionally build indices/constraints.

    Returns the initialized client. The caller is responsible for awaiting
    `graphiti.close()` at shutdown.
    """
    g = build_graphiti(**kwargs)
    if build_indices:
        await g.build_indices_and_constraints()
    logger.info("Graphiti initialized")
    return g


# ── Neo4j helpers ────────────────────────────────────────────────────────────


async def run_cypher(graphiti: Graphiti, query: str, **params) -> list[dict]:
    """Execute a raw Cypher query and return records as dicts.

    Graphiti wraps the neo4j AsyncDriver; when the underlying driver is exposed
    at `.driver` we reach through to it, otherwise we use graphiti.driver
    directly.
    """
    driver = getattr(graphiti.driver, "driver", graphiti.driver)
    async with driver.session() as session:
        result = await session.run(query, **params)
        return [record.data() async for record in result]


def iso_or_none(v) -> str | None:
    """Convert a Neo4j datetime/string/None to ISO format."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return v.isoformat()
    except AttributeError:
        return str(v)


def iso_or_empty(v) -> str:
    """Like iso_or_none but returns '' for None (for string-required contexts)."""
    return iso_or_none(v) or ""
