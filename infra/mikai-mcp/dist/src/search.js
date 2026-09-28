// search.ts — semantic kNN over the vault's embedding cache.
// Reuses the SAME cache format as bridge/dedup_embed.py + pre_extract_topk.py
// (sha256(model + "\n" + text) → raw list of floats).
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
const DEFAULT_OLLAMA_HOST = process.env.OLLAMA_HOST ?? "http://localhost:11434";
const DEFAULT_MODEL = "nomic-embed-text";
const CACHE_DIR_NAME = ".embed-cache";
function cacheKey(text, model) {
    const h = crypto.createHash("sha256");
    h.update(model, "utf8");
    h.update("\n", "utf8");
    h.update(text, "utf8");
    return h.digest("hex");
}
async function loadCached(cacheDir, key) {
    const p = path.join(cacheDir, `${key}.json`);
    try {
        const text = await fs.readFile(p, "utf-8");
        const obj = JSON.parse(text);
        if (Array.isArray(obj))
            return obj;
        if (obj && Array.isArray(obj.embedding))
            return obj.embedding;
        return null;
    }
    catch {
        return null;
    }
}
async function saveCached(cacheDir, key, embedding) {
    await fs.mkdir(cacheDir, { recursive: true });
    await fs.writeFile(path.join(cacheDir, `${key}.json`), JSON.stringify(embedding), "utf-8");
}
async function embedViaOllama(text, host, model) {
    const resp = await fetch(`${host.replace(/\/$/, "")}/api/embeddings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, prompt: text }),
    });
    if (!resp.ok) {
        throw new Error(`Ollama embed HTTP ${resp.status}: ${await resp.text()}`);
    }
    const obj = await resp.json();
    return obj.embedding;
}
async function loadOrEmbed(cacheDir, host, model, text) {
    const key = cacheKey(text, model);
    const cached = await loadCached(cacheDir, key);
    if (cached)
        return cached;
    const vec = await embedViaOllama(text, host, model);
    await saveCached(cacheDir, key, vec);
    return vec;
}
function normalize(vec) {
    let s = 0;
    for (const x of vec)
        s += x * x;
    const n = Math.sqrt(s);
    if (n === 0)
        return vec;
    return vec.map(x => x / n);
}
function dot(a, b) {
    let s = 0;
    for (let i = 0; i < a.length; i++)
        s += a[i] * b[i];
    return s;
}
/**
 * Semantic search: embed the query, cosine against all canonical pages' cached
 * embeddings, return top-N. Falls back to lexical search if Ollama unreachable.
 */
export async function semanticSearch(vault, query, options = {}) {
    const host = options.ollamaHost ?? DEFAULT_OLLAMA_HOST;
    const model = options.model ?? DEFAULT_MODEL;
    const limit = options.limit ?? 10;
    const cacheDir = path.join(vault.vaultRoot, CACHE_DIR_NAME);
    const kinds = options.kinds ?? ["concepts", "entities", "wisdom"];
    let queryVec;
    try {
        queryVec = normalize(await loadOrEmbed(cacheDir, host, model, query));
    }
    catch (e) {
        // Fall back to lexical
        const lex = await vault.lexicalSearch(query, { limit, kinds });
        return lex.map(r => ({ ...r, cosine: 0 }));
    }
    const scores = [];
    for (const kind of kinds) {
        const pages = await vault.listPages(kind, { includeRetired: false });
        for (const meta of pages) {
            try {
                const text = await fs.readFile(meta.path, "utf-8");
                // strip frontmatter
                const bodyStart = text.startsWith("---\n") ? text.indexOf("\n---\n", 4) + 5 : 0;
                const body = text.slice(bodyStart);
                if (body.trim().length < 100)
                    continue;
                // CHANGE-012 (2026-09-28): live-embed on cache miss instead of silent-skip.
                // Cache is keyed by SHA of exact body text — any edit (canonicalization
                // merge, CANON-8 wrap, alias-add) invalidates it. Skipping stale pages
                // was biasing search against the most-worked-on pages. loadOrEmbed
                // mirrors the pattern from dedup_embed.py / pre_extract_topk.py: embed
                // fresh via Ollama on miss, cache the result, use it.
                let vec;
                try {
                    vec = await loadOrEmbed(cacheDir, host, model, body);
                }
                catch {
                    continue; // Ollama unreachable for this page — skip and let query fall through to lexical
                }
                const cosine = dot(queryVec, normalize(vec));
                scores.push({ meta, cosine, body });
            }
            catch {
                continue;
            }
        }
    }
    scores.sort((a, b) => b.cosine - a.cosine);
    return scores.slice(0, limit).map(({ meta, cosine, body }) => ({
        slug: meta.slug,
        kind: meta.kind,
        title: meta.title,
        cosine: Math.round(cosine * 10000) / 10000,
        snippet: body.slice(0, 300).replace(/\s+/g, " ").trim(),
    }));
}
