#!/usr/bin/env npx tsx
/**
 * Perplexity Thread Exporter v4 — Headless browser + in-browser API calls
 *
 * Uses Playwright to open one browser page, then makes fetch() calls
 * FROM INSIDE the browser (bypasses Cloudflare). No visible tabs,
 * no page navigation, no rendering. Fast parallel fetches.
 *
 * Usage:
 *   cd /Users/briancho/Desktop/MIKAI
 *   npx tsx scripts/perplexity-playwright.ts
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const OUTPUT_DIR = path.join(ROOT, 'sources/local-files/export/perplexity');
const PARALLEL = 10;
const DELAY_MS = 300;

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function main() {
  console.log('='.repeat(60));
  console.log('PERPLEXITY EXPORTER v4 (headless + in-browser API)');
  console.log('='.repeat(60));
  console.log(`Output: ${OUTPUT_DIR}\n`);

  const profileDir = path.join(os.tmpdir(), 'pplx-export-profile');
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    args: ['--disable-blink-features=AutomationControlled'],
    viewport: { width: 1280, height: 900 },
  });

  const page = context.pages()[0] || await context.newPage();

  // Navigate to library to establish session
  console.log('Opening perplexity.ai/library...');
  await page.goto('https://www.perplexity.ai/library', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Check if logged in
  const hasThreads = await page.$$eval('a[href*="/search/"]', els => els.length);
  if (hasThreads === 0) {
    console.log('\n⚠️  Not logged in. Log in in the browser window, then press Enter here.');
    await new Promise<void>(r => process.stdin.once('data', () => r()));
    await page.goto('https://www.perplexity.ai/library', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);
  }

  console.log('Session established. Discovering thread list API...\n');

  // ── Step 1: Find all thread slugs ─────────────────────────────────────────
  // First try: use the collections API from inside the browser
  const collectionsResult = await page.evaluate(async () => {
    try {
      const res = await fetch('/rest/collections/list_user_collections?limit=100&offset=0&version=2.18&source=default');
      if (res.ok) return await res.json();
    } catch {}
    return null;
  });

  if (collectionsResult) {
    console.log('Collections API works! Inspecting structure...');
    console.log('Keys:', Object.keys(collectionsResult));
    const preview = JSON.stringify(collectionsResult).slice(0, 500);
    console.log('Preview:', preview);
  }

  // Try to find a thread listing endpoint from inside the browser
  const threadListEndpoints = [
    '/rest/library/list_user_threads?limit=50&offset=0&version=2.18&source=default',
    '/rest/user/threads?limit=50&offset=0&version=2.18&source=default',
    '/rest/library/get_threads?limit=50&offset=0&version=2.18&source=default',
    '/rest/thread/list?limit=50&offset=0&version=2.18&source=default',
    '/rest/library/recent?limit=50&offset=0&version=2.18&source=default',
    '/rest/user/recent_threads?limit=50&offset=0&version=2.18&source=default',
    '/rest/library/get_recent_threads?limit=50&offset=0&version=2.18&source=default',
  ];

  let threadListData: any = null;
  let workingEndpoint = '';

  for (const ep of threadListEndpoints) {
    const result = await page.evaluate(async (url: string) => {
      try {
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          return { status: res.status, data };
        }
        return { status: res.status, data: null };
      } catch (e: any) {
        return { status: 0, data: null };
      }
    }, ep);

    console.log(`  ${ep.split('?')[0]} → ${result.status}`);
    if (result.status === 200 && result.data) {
      threadListData = result.data;
      workingEndpoint = ep;
      console.log('  ✓ FOUND! Keys:', Object.keys(result.data));
      break;
    }
  }

  // ── Step 2: If no thread list API, fall back to scroll + DOM ──────────────
  let threadSlugs: string[] = [];

  if (threadListData) {
    // Extract slugs from API response
    console.log('\nExtracting thread slugs from API...');
    const asStr = JSON.stringify(threadListData);
    const slugMatches = asStr.match(/\/search\/[a-zA-Z0-9._-]+/g) || [];
    threadSlugs = [...new Set(slugMatches.map((s: string) => s.replace('/search/', '')))];

    // Paginate if needed
    if (workingEndpoint && threadSlugs.length >= 45) {
      console.log('Paginating to get all threads...');
      let offset = 50;
      while (true) {
        const nextEp = workingEndpoint.replace('offset=0', `offset=${offset}`);
        const next = await page.evaluate(async (url: string) => {
          try {
            const res = await fetch(url);
            if (res.ok) return await res.json();
          } catch {}
          return null;
        }, nextEp);

        if (!next) break;
        const nextStr = JSON.stringify(next);
        const moreSlugs = nextStr.match(/\/search\/[a-zA-Z0-9._-]+/g) || [];
        const newSlugs = [...new Set(moreSlugs.map((s: string) => s.replace('/search/', '')))];
        if (newSlugs.length === 0) break;
        threadSlugs.push(...newSlugs.filter(s => !threadSlugs.includes(s)));
        offset += 50;
        console.log(`  Offset ${offset}: ${threadSlugs.length} total slugs`);
      }
    }
  }

  if (threadSlugs.length === 0) {
    console.log('\nNo thread list API found. Falling back to scroll + DOM...');
    let stableCount = 0;
    const slugSet = new Set<string>();

    for (let attempt = 0; attempt < 500 && stableCount < 10; attempt++) {
      const links = await page.$$eval('a[href*="/search/"]', (els: HTMLAnchorElement[]) =>
        els.map(a => a.getAttribute('href')).filter(Boolean)
      );

      const prev = slugSet.size;
      for (const href of links) {
        const slug = href?.replace('/search/', '');
        if (slug) slugSet.add(slug);
      }

      if (slugSet.size === prev) stableCount++;
      else stableCount = 0;

      // Scroll both window and containers
      await page.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight);
        document.querySelectorAll('[class*="overflow"]').forEach(c => c.scrollTop = c.scrollHeight);
        // Also try scrolling the main content area
        const main = document.querySelector('main') || document.querySelector('[role="main"]');
        if (main) main.scrollTop = main.scrollHeight;
      });

      await page.waitForTimeout(800);

      if (attempt % 25 === 0) {
        console.log(`  Scroll #${attempt}: ${slugSet.size} threads`);
      }
    }

    threadSlugs = [...slugSet];
  }

  console.log(`\n✓ Found ${threadSlugs.length} thread slugs\n`);

  if (threadSlugs.length === 0) {
    console.log('No threads found. Closing.');
    await context.close();
    return;
  }

  // ── Step 3: Fetch each thread via in-browser API calls ────────────────────
  // Load progress for resume
  const progressFile = path.join(OUTPUT_DIR, '.export-progress.json');
  const exported = new Set<string>();
  if (fs.existsSync(progressFile)) {
    const progress = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
    for (const s of progress.exported) exported.add(s);
    console.log(`Resuming: ${exported.size} already exported\n`);
  }

  const remaining = threadSlugs.filter(s => !exported.has(s));
  console.log(`Fetching ${remaining.length} threads (${PARALLEL} parallel)...\n`);

  const allThreads: any[] = [];
  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < remaining.length; i += PARALLEL) {
    const batch = remaining.slice(i, i + PARALLEL);

    const results = await page.evaluate(async (slugs) => {
      return Promise.all(slugs.map(async (slug) => {
        try {
          const res = await fetch('/rest/thread/' + slug + '?version=2.18&source=default&limit=50&offset=0&from_first=true');
          if (!res.ok) return { slug, error: 'HTTP ' + res.status, data: null };
          return { slug, error: null, data: await res.json() };
        } catch (e) {
          return { slug, error: String(e), data: null };
        }
      }));
    }, batch);

    for (const result of results) {
      if (result.error) {
        failCount++;
        continue;
      }

      try {
        const data = result.data;
        // Extract messages from the thread response
        const entries = data?.entries || data?.messages || data?.thread_data?.entries || [];
        const query_pairs = data?.query_answer_pairs || data?.thread_data?.query_answer_pairs || [];

        let messages: Array<{ sender: string; text: string; created_at: string }> = [];

        if (Array.isArray(entries) && entries.length > 0) {
          for (const entry of entries) {
            const query = entry?.query?.text || entry?.query || '';
            const answer = entry?.answer?.text || entry?.answer?.answer || entry?.text || '';

            if (query) messages.push({ sender: 'human', text: String(query), created_at: entry?.created_at || new Date().toISOString() });
            if (answer) messages.push({ sender: 'assistant', text: String(answer), created_at: entry?.created_at || new Date().toISOString() });
          }
        } else if (Array.isArray(query_pairs) && query_pairs.length > 0) {
          for (const pair of query_pairs) {
            if (pair.query) messages.push({ sender: 'human', text: String(pair.query), created_at: new Date().toISOString() });
            if (pair.answer) messages.push({ sender: 'assistant', text: String(pair.answer), created_at: new Date().toISOString() });
          }
        } else {
          // Dump raw data structure for debugging
          const rawStr = JSON.stringify(data).slice(0, 500);
          if (rawStr.length > 50) {
            messages.push({ sender: 'human', text: result.slug.replace(/-[a-f0-9]+$/, '').replace(/-/g, ' '), created_at: new Date().toISOString() });
            messages.push({ sender: 'assistant', text: rawStr, created_at: new Date().toISOString() });
          }
        }

        if (messages.length > 0) {
          const title = data?.title || data?.thread_data?.title || result.slug.replace(/-[a-f0-9]+$/, '').replace(/-/g, ' ');
          const threadData = {
            title,
            source: 'perplexity',
            url: `https://www.perplexity.ai/search/${result.slug}`,
            exported_at: new Date().toISOString(),
            chat_messages: messages,
          };

          allThreads.push(threadData);
          exported.add(result.slug);
          successCount++;

          fs.writeFileSync(
            path.join(OUTPUT_DIR, `${result.slug.slice(0, 80)}.json`),
            JSON.stringify(threadData, null, 2)
          );
        } else {
          failCount++;
        }
      } catch {
        failCount++;
      }
    }

    const total = exported.size;
    console.log(`  ${Math.min(i + PARALLEL, remaining.length)}/${remaining.length} — ${successCount} exported, ${failCount} empty/failed`);

    // Save progress every 50
    if (total % 50 < PARALLEL) {
      fs.writeFileSync(progressFile, JSON.stringify({ exported: [...exported] }));
      fs.writeFileSync(path.join(OUTPUT_DIR, 'perplexity-all-threads.json'), JSON.stringify(allThreads, null, 2));
    }

    if (i + PARALLEL < remaining.length) {
      await page.waitForTimeout(DELAY_MS);
    }
  }

  // Final save
  if (allThreads.length > 0) {
    fs.writeFileSync(path.join(OUTPUT_DIR, 'perplexity-all-threads.json'), JSON.stringify(allThreads, null, 2));
  }
  if (fs.existsSync(progressFile)) fs.unlinkSync(progressFile);

  console.log('\n' + '='.repeat(60));
  console.log(`COMPLETE: ${successCount} exported, ${failCount} failed`);
  console.log(`Files: ${OUTPUT_DIR}`);
  console.log('='.repeat(60));
  console.log('\nNext: npm run sync:local && npm run build-segments -- --sources perplexity');

  await context.close();
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
