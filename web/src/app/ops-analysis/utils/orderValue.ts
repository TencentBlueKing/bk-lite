export interface ParsedOrder {
  field: string;
  descending: boolean;
}

export const parseOrderValue = (raw: unknown): ParsedOrder => {
  const text = raw === undefined || raw === null ? '' : String(raw).trim();
  if (!text) return { field: '', descending: false };
  if (text.startsWith('-')) return { field: text.slice(1), descending: true };
  return { field: text, descending: false };
};

export const serializeOrderValue = (field: string, descending: boolean): string => {
  const trimmed = field.trim();
  if (!trimmed) return '';
  return descending ? `-${trimmed}` : trimmed;
};
