export function parseEnumValues(raw: unknown): string[] {
  const parts = Array.isArray(raw)
    ? raw.map((part) => (part == null ? '' : String(part)))
    : String(raw ?? '').split(',');
  const tokens: string[] = [];
  for (const part of parts) {
    const token = part.trim();
    if (token && !tokens.includes(token)) {
      tokens.push(token);
    }
  }
  return tokens;
}
