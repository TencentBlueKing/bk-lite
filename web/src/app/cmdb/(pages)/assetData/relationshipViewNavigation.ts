export const DEFAULT_RELATIONSHIP_TAB = 'list';

interface SearchParamsLike {
  toString: () => string;
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
