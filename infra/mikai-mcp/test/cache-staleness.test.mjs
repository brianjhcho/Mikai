// Regression test for CHANGE-012: semanticSearch must live-embed on cache miss,
// not silently skip stale-cache pages. Uses node's built-in test runner + a
// local HTTP server that impersonates Ollama /api/embeddings — no external deps.
//
// Run: npm run build && node --test test/cache-staleness.test.mjs
//
// The bug this covers: search.ts previously did `const cached = await loadCached(...);
// if (!cached) continue;` which invisibly excluded any page whose body had been
// modified since the last embed pass (SHA-keyed cache miss → skip). Canonicalization
// and CANON-8 wrap modify page bodies, so the most-worked-on pages became least
// findable. The fix replaced the silent skip with loadOrEmbed(). This test proves
// the fix works and blocks a regression.

import { test } from "node:test"
import assert from "node:assert/strict"
import http from "node:http"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"

import { Vault } from "../dist/src/vault.js"
import { semanticSearch } from "../dist/src/search.js"

// Deterministic 4-dim embedding — real Ollama returns 768-dim, but the search
// code only cares about cosine similarity and vector shape. A tiny hash-based
// vector is enough to prove the code path executes and produces a scored result.
function fakeEmbedding(text) {
  const buckets = [0, 0, 0, 0]
  for (let i = 0; i < text.length; i++) {
    buckets[i % 4] += text.charCodeAt(i)
  }
  const norm = Math.sqrt(buckets.reduce((s, x) => s + x * x, 0))
  return norm === 0 ? [1, 0, 0, 0] : buckets.map(x => x / norm)
}

async function withMockOllama(fn) {
  const embedCalls = []
  const server = http.createServer((req, res) => {
    if (req.method !== "POST" || !req.url.endsWith("/api/embeddings")) {
      res.writeHead(404).end()
      return
    }
    let body = ""
    req.on("data", chunk => (body += chunk))
    req.on("end", () => {
      const { prompt } = JSON.parse(body)
      embedCalls.push(prompt)
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({ embedding: fakeEmbedding(prompt) }))
    })
  })
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
  const port = server.address().port
  try {
    return await fn({ host: `http://127.0.0.1:${port}`, embedCalls })
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}

async function makeVault() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "mikai-mcp-test-"))
  await fs.mkdir(path.join(root, "wiki", "concepts"), { recursive: true })
  return root
}

test("semanticSearch live-embeds on cache miss (CHANGE-012 regression)", async (t) => {
  const root = await makeVault()
  t.after(() => fs.rm(root, { recursive: true, force: true }))

  const slug = "personal-intent-graph"
  const pagePath = path.join(root, "wiki", "concepts", `${slug}.md`)

  // Original body — long enough to pass the 100-char gate in search.ts.
  const originalBody = "This is the personal intent graph, a canonical page about " +
    "MIKAI's L4 layer for surfacing the user's active intent across threads. " +
    "It tracks what the user is trying to do before they articulate it."

  const frontmatter = `---\ntitle: Personal Intent Graph\n---\n`
  await fs.writeFile(pagePath, frontmatter + originalBody)

  await withMockOllama(async ({ host, embedCalls }) => {
    const vault = new Vault(root)

    // First search — nothing cached yet. Should embed the query + the page,
    // find the page, and cache both.
    const first = await semanticSearch(vault, "intent tracking", {
      ollamaHost: host,
      kinds: ["concepts"],
    })
    assert.equal(first.length, 1, "first search must return the page")
    assert.equal(first[0].slug, slug)
    const firstEmbedCount = embedCalls.length
    assert.ok(firstEmbedCount >= 2, "must have embedded at least query + page")

    // Modify the page — this invalidates the SHA-keyed cache entry for the page
    // body (canonicalization/CANON-8 wrap does this in production).
    const modifiedBody = originalBody + "\n\nAdditionally, wrapped by CANON-8: " +
      "[[intent]] is now a wikilink, changing the body SHA and invalidating cache."
    await fs.writeFile(pagePath, frontmatter + modifiedBody)

    // Second search — page's cached embedding is now stale (SHA changed).
    // Pre-CHANGE-012: silent skip → page missing from results.
    // Post-CHANGE-012: loadOrEmbed live-embeds → page still in results.
    const second = await semanticSearch(vault, "intent tracking", {
      ollamaHost: host,
      kinds: ["concepts"],
    })

    assert.equal(second.length, 1,
      "second search must return the page — silent-skip regression would return 0")
    assert.equal(second[0].slug, slug)
    assert.ok(embedCalls.length > firstEmbedCount,
      "must have made a live embed call for the modified page (not silent-skipped)")
  })
})

test("semanticSearch falls back to lexical when Ollama unreachable", async (t) => {
  const root = await makeVault()
  t.after(() => fs.rm(root, { recursive: true, force: true }))

  const slug = "ollama-unreachable-fallback"
  const body = "This page contains the phrase deterministic-fallback-marker " +
    "which lexical search will match on exact substring, proving that when the " +
    "embedding service is down the search still returns results via the fallback."
  await fs.writeFile(
    path.join(root, "wiki", "concepts", `${slug}.md`),
    `---\ntitle: Fallback Test\n---\n${body}`,
  )

  const vault = new Vault(root)
  // Point at a port that isn't listening — the query embed will throw, and
  // search.ts's catch block should fall through to vault.lexicalSearch.
  const results = await semanticSearch(vault, "deterministic-fallback-marker", {
    ollamaHost: "http://127.0.0.1:1",
    kinds: ["concepts"],
  })
  assert.ok(results.length >= 1, "lexical fallback must return the matching page")
  assert.equal(results[0].slug, slug)
})
