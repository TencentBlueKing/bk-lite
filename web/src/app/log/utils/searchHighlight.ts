const QUERY_OPERATORS = new Set(['and', 'or', 'not', '|', '*']);
const QUOTED_TERM = /"((?:\\.|[^"\\])*)"/g;
const FIELD_PREFIX = /[A-Za-z_][A-Za-z0-9_.]*:/g;

const unescapeQuotedTerm = (value: string) =>
  value.replace(/\\"/g, '"').replace(/\\\\/g, '\\');

export function extractHighlightTerms(query?: string): string[] {
  if (!query) {
    return [];
  }
  const trimmed = query.trim();
  if (!trimmed || trimmed === '*') {
    return [];
  }

  const terms: string[] = [];
  for (const match of trimmed.matchAll(QUOTED_TERM)) {
    const quoted = unescapeQuotedTerm(match[1] || '');
    if (quoted) {
      terms.push(quoted);
    }
  }

  const unquoted = trimmed.replace(QUOTED_TERM, ' ').replace(FIELD_PREFIX, ' ');
  for (const token of unquoted.split(/[\s|()]+/)) {
    if (!token || QUERY_OPERATORS.has(token.toLowerCase())) {
      continue;
    }
    terms.push(token);
  }

  const unique = [...new Set(terms.filter(Boolean))];
  unique.sort((left, right) => right.length - left.length || left.localeCompare(right));
  return unique;
}

export interface HighlightPart {
  text: string;
  match: boolean;
}

export function splitHighlightedText(
  text: string,
  terms: string[]
): HighlightPart[] {
  if (!text || !terms.length) {
    return [{ text, match: false }];
  }

  const lower = text.toLowerCase();
  const ranges: Array<[number, number]> = [];
  for (const term of terms) {
    const needle = term.toLowerCase();
    if (!needle) {
      continue;
    }
    let from = 0;
    while (from <= lower.length - needle.length) {
      const index = lower.indexOf(needle, from);
      if (index < 0) {
        break;
      }
      ranges.push([index, index + needle.length]);
      from = index + needle.length;
    }
  }
  if (!ranges.length) {
    return [{ text, match: false }];
  }

  ranges.sort((left, right) => left[0] - right[0] || right[1] - left[1]);
  const merged: Array<[number, number]> = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) {
      last[1] = Math.max(last[1], range[1]);
    } else {
      merged.push([range[0], range[1]]);
    }
  }

  const parts: HighlightPart[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) {
      parts.push({ text: text.slice(cursor, start), match: false });
    }
    parts.push({ text: text.slice(start, end), match: true });
    cursor = end;
  }
  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor), match: false });
  }
  return parts;
}
