import type { AuthSource } from '../types/security';

export function replaceAuthSource(authSources: AuthSource[], updatedSource: AuthSource): AuthSource[] {
  return authSources.map(item => item.id === updatedSource.id ? updatedSource : item);
}
