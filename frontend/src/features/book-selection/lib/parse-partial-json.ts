import type { PartialRecommendationItem } from '../types';

// ── Partial JSON parser ────────────────────────────────────────
//
// When the LLM streams JSON token-by-token, we need to extract
// structured data from an *incomplete* JSON string so the UI can
// render progressive cards instead of raw text.

/**
 * Attempt to parse a partial JSON string by closing open
 * strings, removing dangling commas/keys, and closing unmatched
 * braces and brackets.  Returns `null` when repair fails.
 */
export function parsePartialJson(text: string): unknown | null {
  const s = text.trim();
  if (!s) return null;

  // Fast path — already valid JSON
  try {
    return JSON.parse(s);
  } catch {
    // needs repair
  }

  // Walk the string to determine open state
  let inStr = false;
  let esc = false;
  const stack: string[] = []; // expected closers: } or ]

  for (const ch of s) {
    if (esc) {
      esc = false;
      continue;
    }
    if (ch === '\\' && inStr) {
      esc = true;
      continue;
    }
    if (ch === '"') {
      inStr = !inStr;
      continue;
    }
    if (inStr) continue;
    if (ch === '{') stack.push('}');
    else if (ch === '[') stack.push(']');
    else if ((ch === '}' || ch === ']') && stack.length) stack.pop();
  }

  let r = s;

  // Close an open string literal
  if (inStr) r += '"';

  // Strip trailing whitespace and dangling commas
  r = r.replace(/[\s,]+$/, '');

  // A trailing colon means we have a key with no value yet — add null
  if (r.endsWith(':')) r += 'null';

  // Close every open brace / bracket
  const closers = [...stack].reverse().join('');
  r += closers;

  // Attempt 1 — direct parse after repair
  try {
    return JSON.parse(r);
  } catch {
    // Likely a dangling object key (e.g. {"a":"b","c"})
  }

  // Attempt 2 — strip last comma-separated token and retry
  const body = r.slice(0, r.length - closers.length);
  const lastComma = findLastUnquotedComma(body);
  if (lastComma >= 0) {
    try {
      return JSON.parse(body.slice(0, lastComma) + closers);
    } catch {
      // give up
    }
  }

  return null;
}

/** Find the index of the last `,` that is not inside a string. */
function findLastUnquotedComma(s: string): number {
  let inStr = false;
  let esc = false;
  let last = -1;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (esc) {
      esc = false;
      continue;
    }
    if (ch === '\\' && inStr) {
      esc = true;
      continue;
    }
    if (ch === '"') {
      inStr = !inStr;
      continue;
    }
    if (inStr) continue;
    if (ch === ',') last = i;
  }
  return last;
}

// ── High-level extraction ──────────────────────────────────────

export interface StreamingParsed {
  summary: string | null;
  items: PartialRecommendationItem[];
}

/**
 * Parse an incomplete JSON string from the streaming LLM and
 * extract partially-available recommendation data.
 */
export function extractStreamingRecommendations(
  text: string,
): StreamingParsed | null {
  const json = parsePartialJson(text);
  if (!json || typeof json !== 'object') return null;

  const obj = json as Record<string, unknown>;

  return {
    summary: typeof obj.summary === 'string' ? obj.summary : null,
    items: Array.isArray(obj.recommendations)
      ? (obj.recommendations
          .map(toPartialItem)
          .filter(Boolean) as PartialRecommendationItem[])
      : [],
  };
}

function toPartialItem(raw: unknown): PartialRecommendationItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;

  const evidence = r.book_evidence;
  let bookEvidence: PartialRecommendationItem['book_evidence'];
  if (evidence && typeof evidence === 'object') {
    const e = evidence as Record<string, unknown>;
    bookEvidence = {
      chapter_title:
        typeof e.chapter_title === 'string' ? e.chapter_title : null,
      section_title:
        typeof e.section_title === 'string' ? e.section_title : null,
      text_evidence:
        typeof e.text_evidence === 'string' ? e.text_evidence : null,
    };
  }

  return {
    category: typeof r.category === 'string' ? r.category : undefined,
    priority: typeof r.priority === 'string' ? r.priority : undefined,
    title: typeof r.title === 'string' ? r.title : undefined,
    description: typeof r.description === 'string' ? r.description : undefined,
    rationale: typeof r.rationale === 'string' ? r.rationale : undefined,
    book_evidence: bookEvidence,
    affected_teacher_document:
      typeof r.affected_teacher_document === 'string'
        ? r.affected_teacher_document
        : undefined,
    suggested_action:
      typeof r.suggested_action === 'string' ? r.suggested_action : undefined,
  };
}
