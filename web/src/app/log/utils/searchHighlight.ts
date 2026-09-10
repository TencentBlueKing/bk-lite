const QUERY_OPERATORS = new Set(['and', 'or', 'not', '|', '*']);
const LOG_CONTENT_FIELDS = new Set(['_msg', 'message']);

const unescapeQuotedTerm = (value: string) =>
  value.replace(/\\"/g, '"').replace(/\\\\/g, '\\');

const isContentField = (field: string) => LOG_CONTENT_FIELDS.has(field);

export function isLogContentField(field?: string): boolean {
  return !!field && isContentField(field);
}

const skipSpaces = (query: string, index: number) => {
  while (index < query.length && /\s/.test(query[index])) {
    index += 1;
  }
  return index;
};

const readQuoted = (
  query: string,
  openIndex: number
): { value: string; next: number } => {
  let value = '';
  let index = openIndex + 1;
  while (index < query.length) {
    const char = query[index];
    if (char === '\\' && index + 1 < query.length) {
      value += query[index + 1];
      index += 2;
      continue;
    }
    if (char === '"') {
      return { value: unescapeQuotedTerm(value), next: index + 1 };
    }
    value += char;
    index += 1;
  }
  return { value: unescapeQuotedTerm(value), next: index };
};

const readBareValue = (
  query: string,
  start: number
): { value: string; next: number } => {
  let index = start;
  while (index < query.length && !/[\s|()"]/.test(query[index])) {
    index += 1;
  }
  let value = query.slice(start, index);
  if (value.endsWith('*')) {
    value = value.slice(0, -1);
  }
  return { value, next: index };
};

const readFilterValue = (
  query: string,
  start: number
): { value: string; next: number } => {
  const index = skipSpaces(query, start);
  if (query[index] === '"') {
    return readQuoted(query, index);
  }
  return readBareValue(query, index);
};

export function extractHighlightTerms(query?: string): string[] {
  if (!query) {
    return [];
  }
  const trimmed = query.trim();
  if (!trimmed || trimmed === '*') {
    return [];
  }

  const terms: string[] = [];
  const emit = (term?: string) => {
    if (term && !QUERY_OPERATORS.has(term.toLowerCase())) {
      terms.push(term);
    }
  };

  let index = 0;
  while (index < trimmed.length) {
    index = skipSpaces(trimmed, index);
    if (index >= trimmed.length) {
      break;
    }

    const char = trimmed[index];
    if ('|()'.includes(char)) {
      index += 1;
      continue;
    }

    if (char === '"') {
      const quoted = readQuoted(trimmed, index);
      index = skipSpaces(trimmed, quoted.next);
      if (trimmed[index] === ':') {
        index = skipSpaces(trimmed, index + 1);
        const filterValue = readFilterValue(trimmed, index);
        index = filterValue.next;
        if (isContentField(quoted.value)) {
          emit(filterValue.value);
        }
        continue;
      }
      emit(quoted.value);
      continue;
    }

    if (char === '-' || char === '!') {
      index += 1;
      continue;
    }

    const bare = readBareValue(trimmed, index);
    index = bare.next;
    const colonAt = bare.value.indexOf(':');
    if (colonAt >= 0) {
      const field = bare.value.slice(0, colonAt);
      const inlineValue = bare.value.slice(colonAt + 1);
      if (inlineValue) {
        if (isContentField(field)) {
          emit(inlineValue.endsWith('*') ? inlineValue.slice(0, -1) : inlineValue);
        }
        continue;
      }
      index = skipSpaces(trimmed, index);
      const filterValue = readFilterValue(trimmed, index);
      index = filterValue.next;
      if (isContentField(field)) {
        emit(filterValue.value);
      }
      continue;
    }

    index = skipSpaces(trimmed, index);
    if (trimmed[index] === ':') {
      index = skipSpaces(trimmed, index + 1);
      const filterValue = readFilterValue(trimmed, index);
      index = filterValue.next;
      if (isContentField(bare.value)) {
        emit(filterValue.value);
      }
      continue;
    }

    emit(bare.value);
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
