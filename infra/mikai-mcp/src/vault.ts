// vault.ts — direct filesystem operations against a MIKAI wiki vault.
// No Desktop app dependency; reads on-disk markdown + frontmatter directly.

import fs from "node:fs/promises"
import path from "node:path"

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---\n/

export interface PageMetadata {
  slug: string
  kind: string            // "concepts" | "entities" | "wisdom" | "sources"
  path: string            // absolute
  title: string
  aliases: string[]
  retiredTo: string | null
  sources: string[]       // from frontmatter
  tags: string[]
}

export interface PageContent extends PageMetadata {
  body: string
  wikilinks: string[]     // outgoing wikilink targets
}

const KINDS = ["concepts", "entities", "wisdom", "sources"] as const
type Kind = typeof KINDS[number]

export function parseFrontmatter(text: string): { fields: Record<string, string | string[]>, end: number } {
  const m = text.match(FRONTMATTER_RE)
  if (!m) return { fields: {}, end: 0 }
  const fields: Record<string, string | string[]> = {}
  for (const line of m[1].split("\n")) {
    if (!line.trim() || line.startsWith("#") || !line.includes(":") || line.startsWith(" ")) continue
    const idx = line.indexOf(":")
    const key = line.slice(0, idx).trim()
    let val = line.slice(idx + 1).trim()
    if (val.length >= 2 && val[0] === val[val.length - 1] && (val[0] === '"' || val[0] === "'")) {
      val = val.slice(1, -1)
    }
    if (val.startsWith("[") && val.endsWith("]")) {
      const inner = val.slice(1, -1)
      fields[key] = inner.split(",").map(s => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean)
    } else {
      fields[key] = val
    }
  }
  return { fields, end: m[0].length }
}

export function stringList(v: string | string[] | undefined): string[] {
  if (!v) return []
  return Array.isArray(v) ? v : [v]
}

export class Vault {
  constructor(private root: string) {}

  static fromEnv(): Vault {
    const root = process.env.MIKAI_WIKI_ROOT
    if (!root) {
      throw new Error("MIKAI_WIKI_ROOT env var not set. Point it at a vault root, e.g. ~/.mikai/wiki-mikai-parallel-test")
    }
    const resolved = root.startsWith("~") ? path.join(process.env.HOME || "", root.slice(1)) : root
    return new Vault(resolved)
  }

  get vaultRoot(): string {
    return this.root
  }

  private wikiDir(kind: Kind): string {
    return path.join(this.root, "wiki", kind)
  }

  async readPage(kind: string, slug: string, followRedirects = true): Promise<PageContent | null> {
    if (!KINDS.includes(kind as Kind)) return null
    const filePath = path.join(this.wikiDir(kind as Kind), `${slug}.md`)
    let text: string
    try {
      text = await fs.readFile(filePath, "utf-8")
    } catch {
      return null
    }
    const { fields, end } = parseFrontmatter(text)
    const body = text.slice(end)
    const title = typeof fields.title === "string" ? fields.title : slug
    const aliases = stringList(fields.aliases as string | string[] | undefined)
    const retiredTo = typeof fields.retired_to === "string" ? fields.retired_to : null
    const sources = stringList(fields.sources as string | string[] | undefined)
    const tags = stringList(fields.tags as string | string[] | undefined)
    // Extract wikilinks
    const wikilinks: string[] = []
    for (const m of body.matchAll(/\[\[([^\]]+)\]\]/g)) {
      const t = m[1].split("|", 1)[0].trim()
      if (t) wikilinks.push(t)
    }

    // Follow retire redirect
    if (followRedirects && retiredTo) {
      const followed = await this.readPage(kind, retiredTo, false)
      if (followed) {
        return { ...followed, aliases: [...followed.aliases, slug, ...aliases] }
      }
    }

    return {
      slug,
      kind,
      path: filePath,
      title,
      aliases,
      retiredTo,
      sources,
      tags,
      body,
      wikilinks,
    }
  }

  async listPages(kind: string, options: { limit?: number; includeRetired?: boolean } = {}): Promise<PageMetadata[]> {
    if (!KINDS.includes(kind as Kind)) return []
    const dir = this.wikiDir(kind as Kind)
    let entries: string[]
    try {
      entries = await fs.readdir(dir)
    } catch {
      return []
    }
    const out: PageMetadata[] = []
    for (const name of entries) {
      if (!name.endsWith(".md")) continue
      if (out.length >= (options.limit ?? Infinity)) break
      const slug = name.slice(0, -3)
      const filePath = path.join(dir, name)
      try {
        const text = await fs.readFile(filePath, "utf-8")
        const { fields } = parseFrontmatter(text)
        const retiredTo = typeof fields.retired_to === "string" ? fields.retired_to : null
        if (retiredTo && !options.includeRetired) continue
        out.push({
          slug,
          kind,
          path: filePath,
          title: typeof fields.title === "string" ? fields.title : slug,
          aliases: stringList(fields.aliases as string | string[] | undefined),
          retiredTo,
          sources: stringList(fields.sources as string | string[] | undefined),
          tags: stringList(fields.tags as string | string[] | undefined),
        })
      } catch {
        continue
      }
    }
    return out
  }

  async loadAliasesIndex(): Promise<Record<string, string>> {
    const p = path.join(this.root, "wiki", ".aliases-index.json")
    try {
      const text = await fs.readFile(p, "utf-8")
      return JSON.parse(text) as Record<string, string>
    } catch {
      return {}
    }
  }

  /**
   * Given a slug, find pages that wikilink TO it (inbound edges).
   * Also returns the outbound edges of the page itself.
   */
  async graph(kind: string, slug: string, maxInbound = 50): Promise<{
    slug: string
    kind: string
    outbound: string[]
    inbound: Array<{ slug: string; kind: string; title: string }>
  } | null> {
    const page = await this.readPage(kind, slug, false)
    if (!page) return null
    const outbound = page.wikilinks

    const inbound: Array<{ slug: string; kind: string; title: string }> = []
    const targetForms = new Set<string>()
    targetForms.add(`${kind}/${slug}`)
    targetForms.add(slug)
    for (const a of page.aliases) {
      targetForms.add(a)
      targetForms.add(`${kind}/${a}`)
    }

    outer:
    for (const otherKind of KINDS) {
      const otherPages = await this.listPages(otherKind, { includeRetired: false })
      for (const meta of otherPages) {
        try {
          const text = await fs.readFile(meta.path, "utf-8")
          const body = text.slice(parseFrontmatter(text).end)
          for (const m of body.matchAll(/\[\[([^\]]+)\]\]/g)) {
            const t = m[1].split("|", 1)[0].trim()
            if (targetForms.has(t)) {
              inbound.push({ slug: meta.slug, kind: meta.kind, title: meta.title })
              break
            }
          }
          if (inbound.length >= maxInbound) break outer
        } catch {
          continue
        }
      }
    }
    return { slug, kind, outbound, inbound }
  }

  /**
   * Cheap lexical search: whole-word match across page titles + bodies.
   * Returns top-N pages by hit count.
   */
  async lexicalSearch(query: string, options: { limit?: number; kinds?: string[] } = {}): Promise<Array<{
    slug: string
    kind: string
    title: string
    hits: number
    snippet: string
  }>> {
    const kinds = (options.kinds ?? KINDS.slice()) as Kind[]
    const limit = options.limit ?? 10
    const q = query.toLowerCase().trim()
    if (!q) return []
    const terms = q.split(/\s+/).filter(t => t.length >= 2)
    const results: Array<{ slug: string; kind: string; title: string; hits: number; snippet: string }> = []

    for (const kind of kinds) {
      const pages = await this.listPages(kind, { includeRetired: false })
      for (const meta of pages) {
        try {
          const text = (await fs.readFile(meta.path, "utf-8")).toLowerCase()
          let hits = 0
          for (const t of terms) {
            const rx = new RegExp("\\b" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "g")
            hits += (text.match(rx) || []).length
          }
          if (hits === 0) continue
          // find first hit snippet
          const firstIdx = text.indexOf(terms[0])
          const rawText = await fs.readFile(meta.path, "utf-8")
          const snippet = firstIdx >= 0 ? rawText.slice(Math.max(0, firstIdx - 50), firstIdx + 200).replace(/\s+/g, " ") : ""
          results.push({ slug: meta.slug, kind: meta.kind, title: meta.title, hits, snippet })
        } catch {
          continue
        }
      }
    }
    results.sort((a, b) => b.hits - a.hits)
    return results.slice(0, limit)
  }
}
