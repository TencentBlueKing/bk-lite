export const DEFAULT_RELATIONSHIP_TAB = 'list';

export type RelationshipWidgetStatus = 'unavailable' | 'loading' | 'ready';

interface SearchParamsLike {
  toString: () => string;
}

export function relationshipGatesSettled(input: {
  themesReady: boolean;
  widgetStatus: RelationshipWidgetStatus;
}): boolean {
  return input.themesReady && input.widgetStatus !== 'loading';
}

export function normalizeRelationshipTab(input: {
  requestedTab: string;
  allowedTabs: readonly string[];
  gatesSettled: boolean;
  fallback?: string;
}): { tab: string; shouldRewrite: boolean } {
  const fallback = input.fallback ?? DEFAULT_RELATIONSHIP_TAB;
  const requested = String(input.requestedTab || '').trim() || fallback;
  if (input.allowedTabs.includes(requested)) {
    return { tab: requested, shouldRewrite: false };
  }
  if (!input.gatesSettled) {
    return { tab: requested, shouldRewrite: false };
  }
  return {
    tab: fallback,
    shouldRewrite: requested !== fallback,
  };
}

export function isAllowedRelationshipTab(
  tab: string,
  allowedTabs: readonly string[],
): boolean {
  return allowedTabs.includes(tab);
}

export const buildRelationshipTabHref = (
  path: string,
  searchParams: SearchParamsLike,
  tab: string
): string => {
  const params = new URLSearchParams(searchParams.toString());
  params.set('tab', tab);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
};

export const isRelationshipMenuActive = (
  pathMatches: boolean,
  currentTab: string,
  shortcutTabs: string[]
): boolean => pathMatches && !shortcutTabs.includes(currentTab);
