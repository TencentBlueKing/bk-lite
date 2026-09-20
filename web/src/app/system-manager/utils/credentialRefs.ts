export interface CredentialRefChip {
  module: string;
  count: number;
}

export type CredentialRefsDisplay =
  | { kind: 'unknown' }
  | { kind: 'zero' }
  | { kind: 'chips'; items: CredentialRefChip[] }
  | { kind: 'text'; value: string };

function asRefChip(item: unknown): CredentialRefChip | null {
  if (!item || typeof item !== 'object') {
    return null;
  }
  const moduleName = 'module' in item ? String(item.module || '') : '';
  const count = 'count' in item ? Number(item.count) : 0;
  if (!moduleName || !count) {
    return null;
  }
  return { module: moduleName, count };
}

export function classifyCredentialRefs(refs: unknown): CredentialRefsDisplay {
  if (refs == null || refs === '') {
    return { kind: 'unknown' };
  }
  if (!Array.isArray(refs)) {
    return { kind: 'text', value: String(refs) };
  }
  const items = refs.flatMap((item) => {
    const chip = asRefChip(item);
    return chip ? [chip] : [];
  });
  return items.length === 0 ? { kind: 'zero' } : { kind: 'chips', items };
}
