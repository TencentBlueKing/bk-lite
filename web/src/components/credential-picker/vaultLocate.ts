import { CREDENTIAL_CATEGORIES, CREDENTIAL_MENU_PATH } from './types';

export function buildCredentialVaultUrl(category?: string, type?: string): string {
  const params = new URLSearchParams();
  if (category) {
    params.set('category', category);
    if (type) {
      params.set('type', type);
    }
  }
  const query = params.toString();
  return query ? `${CREDENTIAL_MENU_PATH}?${query}` : CREDENTIAL_MENU_PATH;
}

export function resolveCredentialLocate(
  query: { category?: string | null; type?: string | null },
  types: { key: string; categories: string[] }[],
): { category: string; type?: string } {
  const defaultCategory = CREDENTIAL_CATEGORIES[0];
  const requestedCategory = query.category?.trim() || '';
  if (!requestedCategory) {
    return { category: defaultCategory };
  }

  const knownCategories = new Set<string>([
    ...CREDENTIAL_CATEGORIES,
    ...types.flatMap((item) => item.categories),
  ]);
  if (!knownCategories.has(requestedCategory)) {
    return { category: defaultCategory };
  }

  const requestedType = query.type?.trim() || '';
  if (!requestedType) {
    return { category: requestedCategory };
  }

  const typeOk = types.some(
    (item) => item.key === requestedType && item.categories.includes(requestedCategory),
  );
  return {
    category: requestedCategory,
    type: typeOk ? requestedType : undefined,
  };
}
