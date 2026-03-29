/**
 * engine/graph/smart-split.js
 *
 * Source-type-aware content splitting — ZERO LLM calls.
 * Each source type gets the splitting strategy that matches its natural structure.
 *
 * All functions return Array<{ topic_label: string, condensed_content: string }>
 * — same shape as the old LLM output so downstream code doesn't change.
 */

// ── Utilities ─────────────────────────────────────────────────────────────────

function wordCount(text) {
  return text.split(/\s+/).filter(Boolean).length;
}

function firstChars(text, limit = 60) {
  const trimmed = text.trim().replace(/^["'""''`]+/, '').replace(/["'""''`]+$/, '');
  return trimmed.length <= limit ? trimmed : trimmed.slice(0, limit).trimEnd();
}

// ── Main entry ─────────────────────────────────────────────────────────────────

/**
 * Split content based on source type.
 * Returns array of { topic_label: string, condensed_content: string }
 * (same shape as the old LLM output so downstream code doesn't change).
 *
 * @param {string} content      - Cleaned source text (from preprocess.ts cleanContent)
 * @param {string} sourceOrigin - Source type: 'claude-thread' | 'perplexity' | 'apple-notes' | 'manual' | ...
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function smartSplit(content, sourceOrigin) {
  switch (sourceOrigin) {
    case 'claude-thread':
      return splitClaudeThread(content);
    case 'perplexity':
      return splitPerplexityThread(content);
    case 'apple-notes':
      return splitAppleNote(content);
    case 'gmail':
      return splitGmail(content);
    case 'imessage':
      return splitIMessage(content);
    case 'manual':
      return splitMarkdown(content);
    default:
      return splitGeneric(content);
  }
}

// ── Claude thread splitter ────────────────────────────────────────────────────

/**
 * Content has [User]: ... and [Assistant]: ... turns (from preprocess.ts cleanClaudeExport).
 * Split at each [User]: boundary. Each segment = one [User] turn + following [Assistant] turn.
 * Filters out logistics / short queries (< 15 words in the [User] text).
 *
 * @param {string} content
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function splitClaudeThread(content) {
  // Split on [User]: boundaries, keeping the delimiter
  const parts = content.split(/(?=\[User\]:)/);
  const segments = [];

  for (const part of parts) {
    if (!part.trim().startsWith('[User]:')) continue;

    // Separate [User] and [Assistant] blocks within this turn
    const userMatch = part.match(/^\[User\]:\s*([\s\S]*?)(?=\[Assistant\]:|$)/);
    const assistantMatch = part.match(/\[Assistant\]:\s*([\s\S]*?)$/);

    const userText = userMatch ? userMatch[1].trim() : '';
    const assistantText = assistantMatch ? assistantMatch[1].trim() : '';

    // Skip segments where [User] text is < 15 words (logistics, "continue", etc.)
    if (wordCount(userText) < 15) continue;

    const condensed_content = [
      `[User]: ${userText}`,
      assistantText ? `[Assistant]: ${assistantText}` : '',
    ].filter(Boolean).join('\n\n');

    segments.push({
      topic_label: firstChars(userText),
      condensed_content,
    });
  }

  return segments;
}

// ── Perplexity thread splitter ────────────────────────────────────────────────

/**
 * Same format as Claude thread: [User]: ... and [Assistant]: ... turns.
 * Split at [User] boundaries; each segment = full query + response pair.
 * Filters out pairs where total text < 30 words.
 *
 * @param {string} content
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function splitPerplexityThread(content) {
  // ── Try JSON steps format first (from browser API export) ────────────────
  // Content looks like: [Assistant]: [{"step_type": "INITIAL_QUERY", ...}, ...]
  const jsonMatch = content.match(/\[Assistant\]:\s*(\[[\s\S]*\])/);
  if (jsonMatch) {
    try {
      const steps = JSON.parse(jsonMatch[1]);
      if (Array.isArray(steps)) {
        return parsePerplexitySteps(steps);
      }
    } catch { /* not valid JSON, fall through */ }
  }

  // Also try: content IS the JSON array directly (no [Assistant]: prefix)
  if (content.trim().startsWith('[{"step_type"')) {
    try {
      const steps = JSON.parse(content.trim());
      if (Array.isArray(steps)) {
        return parsePerplexitySteps(steps);
      }
    } catch { /* fall through */ }
  }

  // ── Fall back to [User]:/[Assistant]: text format ────────────────────────
  const parts = content.split(/(?=\[User\]:)/);
  const segments = [];

  for (const part of parts) {
    if (!part.trim().startsWith('[User]:')) continue;

    const userMatch = part.match(/^\[User\]:\s*([\s\S]*?)(?=\[Assistant\]:|$)/);
    const assistantMatch = part.match(/\[Assistant\]:\s*([\s\S]*?)$/);

    const userText = userMatch ? userMatch[1].trim() : '';
    const assistantText = assistantMatch ? assistantMatch[1].trim() : '';

    const condensed_content = [
      `[User]: ${userText}`,
      assistantText ? `[Assistant]: ${assistantText}` : '',
    ].filter(Boolean).join('\n\n');

    if (wordCount(condensed_content) < 30) continue;

    segments.push({
      topic_label: firstChars(userText),
      condensed_content,
    });
  }

  // If no [User]: markers found, treat as journal-style
  if (segments.length === 0 && wordCount(content) >= 50) {
    return splitJournal(content);
  }

  return segments;
}

/**
 * Parse Perplexity JSON steps format into segments.
 * Extracts queries and answer text from the nested step structure.
 * The JSON format varies — use regex extraction as a robust fallback.
 */
function parsePerplexitySteps(steps) {
  const segments = [];
  let currentQuery = '';
  let answerParts = [];

  for (const step of steps) {
    const type = step.step_type || '';

    // Extract queries
    if (type === 'INITIAL_QUERY' || type === 'FOLLOWUP_QUERY') {
      // Flush previous QA pair
      if (currentQuery && answerParts.length > 0) {
        const answer = answerParts.join('\n').trim();
        if (wordCount(answer) >= 20) {
          segments.push({
            topic_label: firstChars(currentQuery),
            condensed_content: `${currentQuery}\n\n${answer}`,
          });
        }
      }
      currentQuery = step.content?.query || step.content?.text || '';
      answerParts = [];
    }

    // Extract answer text from various step types
    const c = step.content;
    if (c && typeof c === 'object') {
      // Direct text/answer fields
      if (typeof c.answer === 'string' && c.answer.length > 10) answerParts.push(c.answer);
      if (typeof c.text === 'string' && c.text.length > 10 && type !== 'INITIAL_QUERY') answerParts.push(c.text);
      // Nested result/response fields
      if (typeof c.result === 'string' && c.result.length > 10) answerParts.push(c.result);
      if (typeof c.response === 'string' && c.response.length > 10) answerParts.push(c.response);
      // Web search results may have snippets
      if (Array.isArray(c.results)) {
        for (const r of c.results) {
          if (typeof r.snippet === 'string' && r.snippet.length > 20) answerParts.push(r.snippet);
          if (typeof r.text === 'string' && r.text.length > 20) answerParts.push(r.text);
        }
      }
    } else if (typeof c === 'string' && c.length > 20) {
      answerParts.push(c);
    }
  }

  // Flush last pair
  if (currentQuery && answerParts.length > 0) {
    const answer = answerParts.join('\n').trim();
    if (wordCount(answer) >= 20) {
      segments.push({
        topic_label: firstChars(currentQuery),
        condensed_content: `${currentQuery}\n\n${answer}`,
      });
    }
  }

  // If no structured extraction worked, try regex on the raw JSON string
  if (segments.length === 0) {
    const jsonStr = JSON.stringify(steps);
    // Extract all query strings
    const queries = [...jsonStr.matchAll(/"query"\s*:\s*"([^"]{10,})"/g)].map(m => m[1]);
    // Extract all answer/text strings > 50 chars
    const answers = [...jsonStr.matchAll(/"(?:answer|text|snippet)"\s*:\s*"([^"]{50,})"/g)].map(m => m[1]);

    if (queries.length > 0 && answers.length > 0) {
      // Pair queries with answers
      for (let i = 0; i < queries.length; i++) {
        const answer = answers[i] || answers[answers.length - 1] || '';
        if (wordCount(answer) >= 20) {
          segments.push({
            topic_label: firstChars(queries[i]),
            condensed_content: `${queries[i]}\n\n${answer.replace(/\\n/g, '\n').replace(/\\"/g, '"')}`,
          });
        }
      }
    }
  }

  return segments;
}

// ── Journal / Apple Notes splitter ────────────────────────────────────────────

/**
 * Content is mixed: one-liners, quotes, multi-paragraph reflections.
 * Split on single newlines to get individual lines, then merge into blocks
 * until blocks reach 50+ words. Standalone long lines (> 80 words) stand alone.
 * Filters out blocks < 20 words after merging.
 *
 * @param {string} content
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function splitJournal(content) {
  // Split on single newlines; filter empties and < 5 char lines
  const lines = content.split('\n').map(l => l.trim()).filter(l => l.length >= 5);

  if (lines.length === 0) return [];

  const blocks = [];
  let current = [];
  let currentWords = 0;

  for (const line of lines) {
    const lw = wordCount(line);

    // Long standalone lines become their own segment
    if (lw > 80) {
      // Flush current block first
      if (current.length > 0 && currentWords >= 20) {
        blocks.push(current.join('\n'));
      }
      current = [];
      currentWords = 0;
      blocks.push(line);
      continue;
    }

    current.push(line);
    currentWords += lw;

    // Flush once block reaches 50+ words
    if (currentWords >= 50) {
      blocks.push(current.join('\n'));
      current = [];
      currentWords = 0;
    }
  }

  // Flush remaining
  if (current.length > 0 && currentWords >= 20) {
    blocks.push(current.join('\n'));
  }

  return blocks
    .filter(block => wordCount(block) >= 20)
    .map(block => ({
      topic_label: firstChars(block.split(/[.!?]/)[0] || block),
      condensed_content: block,
    }));
}

// ── Markdown / manual splitter ────────────────────────────────────────────────

/**
 * Check for heading markers (##, ###, #). If headings exist: split at heading
 * boundaries using heading text as topic_label. If no headings: fall back to
 * splitGeneric. Filters sections < 20 words.
 *
 * @param {string} content
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function splitMarkdown(content) {
  const hasHeadings = /^#{1,3}\s+.+/m.test(content);

  if (!hasHeadings) {
    // Detect journal-style content: many short lines separated by single newlines
    const singleLines = content.split('\n').map(l => l.trim()).filter(l => l.length >= 5);
    const doubleParas = content.split(/\n\n+/).map(p => p.trim()).filter(p => p.length >= 10);

    // If single-newline lines outnumber double-newline paragraphs by 3x+, it's journal-style
    if (singleLines.length > doubleParas.length * 3 || doubleParas.length <= 1) {
      return splitJournal(content);
    }

    return splitGeneric(content);
  }

  // Split at heading lines — capture the heading marker + text
  const lines = content.split('\n');
  const sections = [];
  let currentHeading = null;
  let currentLines = [];

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      // Flush previous section
      if (currentHeading !== null) {
        const body = currentLines.join('\n').trim();
        if (wordCount(body) >= 20) {
          sections.push({ topic_label: firstChars(currentHeading), condensed_content: body });
        }
      }
      currentHeading = headingMatch[2].trim();
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }

  // Flush last section
  if (currentHeading !== null) {
    const body = currentLines.join('\n').trim();
    if (wordCount(body) >= 20) {
      sections.push({ topic_label: firstChars(currentHeading), condensed_content: body });
    }
  }

  return sections;
}

// ── Generic splitter ──────────────────────────────────────────────────────────

/**
 * Split on double newlines to get paragraphs. Filter paragraphs < 10 chars.
 * Merge consecutive paragraphs until block reaches 50+ words.
 * Filters blocks < 20 words.
 *
 * @param {string} content
 * @returns {Array<{ topic_label: string, condensed_content: string }>}
 */
export function splitGeneric(content) {
  const paragraphs = content.split(/\n\n+/).map(p => p.trim()).filter(p => p.length >= 10);

  if (paragraphs.length === 0) return [];

  const blocks = [];
  let current = [];
  let currentWords = 0;

  for (const para of paragraphs) {
    const pw = wordCount(para);
    current.push(para);
    currentWords += pw;

    if (currentWords >= 50) {
      blocks.push(current.join('\n\n'));
      current = [];
      currentWords = 0;
    }
  }

  // Flush remaining
  if (current.length > 0 && currentWords >= 20) {
    blocks.push(current.join('\n\n'));
  }

  return blocks
    .filter(block => wordCount(block) >= 20)
    .map(block => ({
      topic_label: firstChars(block),
      condensed_content: block,
    }));
}

// ── Gmail splitter ────────────────────────────────────────────────────────────

/**
 * Gmail splitter — one email = one segment, metadata-enriched.
 * Emails are atomic units. Don't split them — enrich them.
 * Extracts subject/from/date from content patterns and prepends as metadata.
 * Minimum 15 words (filters truly empty emails like "OK" or "Thanks").
 */
export function splitGmail(content) {
  // Try to extract email metadata from common patterns
  let subject = '';
  let from = '';
  let date = '';

  // Common email header patterns in cleaned content
  const subjectMatch = content.match(/Subject:\s*(.+?)(?:\n|$)/i);
  if (subjectMatch) subject = subjectMatch[1].trim().slice(0, 120);

  const fromMatch = content.match(/From:\s*(.+?)(?:\n|$)/i);
  if (fromMatch) from = fromMatch[1].trim().slice(0, 80);

  const dateMatch = content.match(/Date:\s*(.+?)(?:\n|$)/i);
  if (dateMatch) date = dateMatch[1].trim().slice(0, 40);

  // Clean the body (remove header lines if extracted)
  let body = content;
  if (subjectMatch) body = body.replace(subjectMatch[0], '');
  if (fromMatch) body = body.replace(fromMatch[0], '');
  if (dateMatch) body = body.replace(dateMatch[0], '');
  body = body.trim();

  if (wordCount(body) < 15) return [];

  // Build metadata-enriched content for embedding
  const metaParts = ['[Email]'];
  if (subject) metaParts.push(`Subject: ${subject}`);
  if (from) metaParts.push(`From: ${from}`);
  if (date) metaParts.push(`Date: ${date}`);
  const metaPrefix = metaParts.join(' | ');

  const enriched = `${metaPrefix}\n${body}`;

  // If email is long enough to split, use generic splitting on the body
  if (wordCount(body) >= 200) {
    const subSegments = splitGeneric(body);
    return subSegments.map(seg => ({
      topic_label: subject || firstChars(seg.condensed_content),
      condensed_content: `${metaPrefix}\n${seg.condensed_content}`,
    }));
  }

  return [{
    topic_label: subject || firstChars(body),
    condensed_content: enriched,
  }];
}

// ── Apple Notes splitter ──────────────────────────────────────────────────────

/**
 * Apple Notes splitter — one note = one segment, metadata-enriched.
 * Notes are reflective fragments, typically 50-120 words. Don't discard them.
 * Minimum 10 words.
 */
export function splitAppleNote(content) {
  const cleaned = content
    .replace(/\\\\/g, '')           // strip escaped backslashes from export
    .replace(/\\$/gm, '')           // strip trailing backslashes
    .replace(/\n{3,}/g, '\n\n')    // normalize multiple newlines
    .trim();

  if (wordCount(cleaned) < 10) return [];

  // If the note is long enough, use journal-style splitting
  if (wordCount(cleaned) >= 100) {
    const subSegments = splitJournal(cleaned);
    return subSegments.map(seg => ({
      topic_label: seg.topic_label,
      condensed_content: `[Note] ${seg.condensed_content}`,
    }));
  }

  // Short note — emit as single metadata-enriched segment
  return [{
    topic_label: firstChars(cleaned.split(/[.!?\n]/)[0] || cleaned),
    condensed_content: `[Note] ${cleaned}`,
  }];
}

// ── iMessage splitter ─────────────────────────────────────────────────────────

/**
 * iMessage splitter — split by conversation windows.
 * The sync script groups all messages into one document.
 * Split into conversation windows: messages within 2 hours = one segment.
 * Minimum 2 messages / 20 words per window.
 */
export function splitIMessage(content) {
  // Messages are typically formatted as "YYYY-MM-DD HH:MM - [contact]: message"
  // or just line-by-line with timestamps
  const lines = content.split('\n').map(l => l.trim()).filter(l => l.length >= 3);

  if (lines.length === 0) return [];

  // If content doesn't have clear message structure, fall back to journal splitting
  const hasTimestamps = lines.some(l => /\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}/.test(l));

  if (!hasTimestamps) {
    const segments = splitJournal(content);
    return segments.map(seg => ({
      topic_label: seg.topic_label,
      condensed_content: `[Message] ${seg.condensed_content}`,
    }));
  }

  // Group into conversation windows
  const windows = [];
  let currentWindow = [];
  let currentWords = 0;

  for (const line of lines) {
    currentWindow.push(line);
    currentWords += wordCount(line);

    // Simple window boundary: accumulate until we have enough content
    if (currentWords >= 50) {
      windows.push(currentWindow.join('\n'));
      currentWindow = [];
      currentWords = 0;
    }
  }

  // Flush remaining
  if (currentWindow.length >= 2 && currentWords >= 20) {
    windows.push(currentWindow.join('\n'));
  }

  return windows
    .filter(w => wordCount(w) >= 20)
    .map(w => ({
      topic_label: firstChars(w.split(/[.!?\n]/)[0] || w),
      condensed_content: `[Message] ${w}`,
    }));
}
