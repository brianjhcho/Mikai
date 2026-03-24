/**
 * engine/ingestion/preprocess.ts
 *
 * Format-specific content cleaning for all source connectors.
 * Call cleanContent(rawContent, sourceType) before POSTing to /api/ingest/batch.
 * Claude should never receive raw HTML, timestamps, or boilerplate.
 */

export type PreprocessSourceType = 'apple-notes' | 'whatsapp' | 'browser' | 'markdown' | 'claude-export' | 'imessage' | 'gmail' | 'plain';

/**
 * Clean raw content from a specific source before sending to the ingestion pipeline.
 * Returns plain text suitable for chunking and embedding.
 */
export function cleanContent(rawContent: string, sourceType: string): string {
  switch (sourceType) {
    case 'apple-notes':
      return cleanAppleNotes(rawContent);
    case 'whatsapp':
      return cleanWhatsApp(rawContent);
    case 'browser':
      return cleanBrowser(rawContent);
    case 'markdown':
      return cleanMarkdown(rawContent);
    case 'claude-export':
      return cleanClaudeExport(rawContent);
    case 'imessage':
      return cleanImessage(rawContent);
    case 'gmail':
      return cleanGmail(rawContent);
    default:
      return cleanPlain(rawContent);
  }
}

// ── Source-specific cleaners ──────────────────────────────────────────────────

/**
 * Apple Notes HTML export.
 * Strips HTML tags, unescapes entities, normalizes whitespace.
 */
function cleanAppleNotes(raw: string): string {
  return raw
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/\r\n/g, '\n')
    // Apple Notes exports encode backslash-escaped line breaks as literal "\"
    .replace(/\\\s*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * WhatsApp chat export.
 * Strips timestamps (e.g. "12/31/24, 9:41 AM - ") and sender prefixes ("Name: ").
 * Preserves the message content.
 */
function cleanWhatsApp(raw: string): string {
  return raw
    // Timestamp + sender prefix: "12/31/24, 9:41 AM - Name: "
    .replace(/^\d{1,2}\/\d{1,2}\/\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*-\s*[^:]+:\s*/gim, '')
    // ISO-style timestamps: "[2024-12-31, 09:41:00] Name: "
    .replace(/^\[\d{4}-\d{2}-\d{2},\s*\d{2}:\d{2}:\d{2}\]\s*[^:]+:\s*/gim, '')
    // System messages like "<Media omitted>", "Messages and calls are end-to-end encrypted"
    .replace(/^<[^>]+>$/gim, '')
    .replace(/^(Messages and calls are end-to-end encrypted.*|This message was deleted.*)$/gim, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Browser-sourced HTML (web clips, saved pages).
 * Strips nav, footer, script, style, and common boilerplate before tag removal.
 */
function cleanBrowser(raw: string): string {
  return raw
    // Remove entire non-content blocks
    .replace(/<(script|style|nav|header|footer|aside|noscript)[^>]*>[\s\S]*?<\/\1>/gi, '')
    // Common boilerplate class/id patterns (cookie banners, ads, etc.)
    .replace(/<[^>]*(class|id)="[^"]*?(cookie|banner|ad-|sidebar|popup|modal|newsletter)[^"]*?"[^>]*>[\s\S]*?<\/[^>]+>/gi, '')
    // Then standard HTML → text
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Markdown files (project docs, Perplexity exports).
 * Strips YAML frontmatter, image syntax, bare URLs, and header markers.
 * Keeps heading text, list content, and body prose.
 */
function cleanMarkdown(raw: string): string {
  return raw
    // Strip YAML frontmatter block at top of file
    .replace(/^---[\s\S]*?---\n?/, '')
    // Strip markdown images — keep alt text, drop URL
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    // Strip inline links — keep link text, drop URL
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    // Strip bare URLs on their own line
    .replace(/^https?:\/\/\S+$/gim, '')
    // Strip header markers but keep the text
    .replace(/^#{1,6}\s+/gim, '')
    // Strip horizontal rules
    .replace(/^[-*_]{3,}\s*$/gim, '')
    // Strip bold/italic markers
    .replace(/\*{1,3}([^*]+)\*{1,3}/g, '$1')
    .replace(/_{1,3}([^_]+)_{1,3}/g, '$1')
    // Strip inline code backticks — keep the content
    .replace(/`([^`]+)`/g, '$1')
    // Strip fenced code blocks — keep the code content
    .replace(/^```[^\n]*\n([\s\S]*?)```$/gim, '$1')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Claude conversation JSON export.
 * Extracts user and assistant text turns from the messages array.
 * Skips tool_use, tool_result, and binary content blocks.
 */
function cleanClaudeExport(raw: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // Not valid JSON — treat as plain text
    return cleanPlain(raw);
  }

  const data = parsed as Record<string, unknown>;

  // Support both Anthropic export format ({ messages: [...] })
  // and Claude.ai export format ({ chat_messages: [...] })
  const messages =
    (Array.isArray(data.messages) ? data.messages :
     Array.isArray(data.chat_messages) ? data.chat_messages :
     []) as Array<Record<string, unknown>>;

  if (messages.length === 0) return cleanPlain(raw);

  const turns: string[] = [];

  for (const msg of messages) {
    // Support both Anthropic API format (role: 'user'/'assistant')
    // and Claude.ai export format (sender: 'human'/'assistant')
    const role = (msg.role ?? msg.sender) as string;
    const isUser = role === 'user' || role === 'human';
    const isAssistant = role === 'assistant';
    if (!isUser && !isAssistant) continue;

    const prefix = isUser ? '[User]' : '[Assistant]';
    let text = '';

    // Claude.ai export uses top-level `text` field
    if (typeof msg.text === 'string' && msg.text.trim().length > 0) {
      text = msg.text.trim();
    } else if (typeof msg.content === 'string') {
      text = msg.content.trim();
    } else if (Array.isArray(msg.content)) {
      // Content blocks — extract text blocks only
      const textParts = (msg.content as Array<Record<string, unknown>>)
        .filter((block) => block.type === 'text')
        .map((block) => String(block.text ?? '').trim())
        .filter((t) => t.length > 0);
      text = textParts.join('\n');
    }

    if (text.length > 0) {
      turns.push(`${prefix}: ${text}`);
    }
  }

  return turns.join('\n\n').replace(/\n{3,}/g, '\n\n').trim();
}

/**
 * iMessage export.
 * Strips Apple timestamp formats [HH:MM] or bubble timestamps,
 * normalizes line breaks, redacts phone numbers and emails.
 */
function cleanImessage(raw: string): string {
  return raw
    // Strip timestamp markers like [9:41 AM] or [09:41]
    .replace(/\[\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\]/gi, '')
    // Redact phone numbers: +1 (555) 123-4567, 555-123-4567, +15551234567, etc.
    .replace(/\+?[\d\s\-().]{10,}/g, '[contact]')
    // Redact email addresses
    .replace(/\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b/gi, '[contact]')
    // Normalize line breaks
    .replace(/\r\n/g, '\n')
    // Collapse excess whitespace
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

/**
 * Gmail email content.
 * Strips HTML tags, quoted reply blocks (On ... wrote:), and email headers.
 * Normalizes whitespace.
 */
function cleanGmail(raw: string): string {
  return raw
    // Strip quoted reply blocks: "On Mon, Jan 1, 2024 at 9:41 AM Name <email> wrote:"
    .replace(/^On\s.+wrote:\s*$/gim, '')
    // Strip > quoted lines
    .replace(/^>.*$/gm, '')
    // Strip HTML tags if present
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    // Unescape HTML entities
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    // Strip email header patterns like "From: ...", "To: ...", "Subject: ...", "Date: ..."
    .replace(/^(From|To|Cc|Bcc|Subject|Date|Reply-To|Message-ID):\s*.+$/gim, '')
    // Normalize whitespace
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

/**
 * Plain text (already clean).
 * Normalizes line endings and collapses excess whitespace only.
 */
function cleanPlain(raw: string): string {
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
