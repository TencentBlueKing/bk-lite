import type { CredentialFieldSchema } from './types';

export function isCredentialFieldVisible(
  field: CredentialFieldSchema,
  values: Record<string, unknown>,
): boolean {
  const conditions = field.visible_when;
  if (!conditions) {
    return true;
  }
  return Object.entries(conditions).every(([referencedId, condition]) => {
    const actual = values[referencedId];
    if (typeof actual !== 'string') {
      return false;
    }
    if (typeof condition === 'string') {
      return actual === condition;
    }
    if (condition?.op === 'eq') {
      return actual === condition.value;
    }
    if (condition?.op === 'ne') {
      return actual !== condition.value;
    }
    return false;
  });
}

export function formatVisibleWhen(field: CredentialFieldSchema): string {
  const conditions = field.visible_when;
  if (!conditions || !Object.keys(conditions).length) {
    return '';
  }
  return Object.entries(conditions)
    .map(([id, condition]) => {
      if (typeof condition === 'string') {
        return `${id} = ${condition}`;
      }
      return `${id} ${condition.op === 'ne' ? '≠' : '='} ${condition.value}`;
    })
    .join(' and ');
}
