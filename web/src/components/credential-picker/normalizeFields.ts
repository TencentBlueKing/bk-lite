import type { CredentialFieldSchema } from './types';

export function normalizeCredentialFieldValues(
  schema: CredentialFieldSchema[],
  values: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const incoming = { ...(values || {}) };
  for (const field of schema) {
    if (field.kind !== 'secret' || field.required) {
      continue;
    }
    const raw = incoming[field.id];
    if (raw == null || raw === '') {
      delete incoming[field.id];
    }
  }
  return incoming;
}
