import { MenuItem } from '@/types/index';

/**
 * Exact menu path, or a descendant under it (path-segment boundary).
 * Callers that need the active top-level item must still prefer the
 * longest sibling match among directoryized menus.
 */
export const isMenuPathMatch = (menuUrl: string, currentPath: string): boolean => {
  const menu = menuUrl.replace(/\/+$/, '') || '/';
  const path = currentPath.replace(/\/+$/, '') || '/';
  return path === menu || path.startsWith(`${menu}/`);
};

const pathScore = (items: MenuItem[]): [number, number] => {
  const leafUrl = items[items.length - 1]?.url?.replace(/\/+$/, '') || '';
  return [items.length, leafUrl.length];
};

const isBetterMatch = (candidate: MenuItem[], current: MenuItem[]): boolean => {
  const [candDepth, candLen] = pathScore(candidate);
  const [curDepth, curLen] = pathScore(current);
  if (candDepth !== curDepth) return candDepth > curDepth;
  return candLen > curLen;
};

/**
 * Find the complete menu path matching the current path (from top to deepest layer).
 * Among siblings that all prefix-match the path, prefer the longest URL so that
 * shorter directory prefixes do not steal active state from longer children.
 */
export const findMatchedMenuPath = (
  items: MenuItem[],
  currentPath: string,
  path: MenuItem[] = []
): MenuItem[] | null => {
  let bestMatch: MenuItem[] | null = null;

  const consider = (candidate: MenuItem[] | null) => {
    if (!candidate?.length) return;
    if (!bestMatch || isBetterMatch(candidate, bestMatch)) {
      bestMatch = candidate;
    }
  };

  for (const item of items) {
    const matchedPath = [...path, item];

    if (item.url && isMenuPathMatch(item.url, currentPath)) {
      if (item.children?.length) {
        const childMatch = findMatchedMenuPath(item.children, currentPath, matchedPath);
        consider(childMatch ?? matchedPath);
      } else {
        consider(matchedPath);
      }
      continue;
    }

    // Search in children even if parent has no url (e.g., directory-only items)
    if (item.children?.length) {
      consider(findMatchedMenuPath(item.children, currentPath, matchedPath));
    }
  }

  return bestMatch;
};

/**
 * Determine if second layer menu should be rendered in app/layout
 * Logic: Render menu if first layer does NOT have hasDetail flag
 * If hasDetail is true, it means second layer is in detail mode and should not be rendered
 */
export const shouldRenderSecondLayerMenu = (
  currentPath: string | null,
  menuItems: MenuItem[]
): boolean => {
  if (!currentPath) return false;

  const menuPath = findMatchedMenuPath(menuItems, currentPath);
  
  if (!menuPath || menuPath.length < 1) return false;
  
  // Check the first layer
  const firstLayer = menuPath[0];
  
  // If first layer has hasDetail flag, do NOT render menu (detail mode)
  if (firstLayer.hasDetail) {
    return false;
  }
  
  // Otherwise, render menu
  return true;
};

const filterVisibleMenuItems = (items: MenuItem[] = []): MenuItem[] =>
  items.filter((item) => !item.isNotMenuItem && !item.isDirectory);

/**
 * Get secondary menu items for the current path (detail side menus).
 *
 * Uses longest-path matching (so app-root menus like `/apm` do not steal
 * deeper routes). When the deepest match is a leaf page with no children,
 * fall back to the parent's visible children — the previous WithSideMenuLayout
 * behavior needed by opspilot skill/studio detail pages.
 */
export const getDeepestMatchedMenuItems = (
  menus: MenuItem[],
  currentPath: string
): MenuItem[] => {
  const matchedPath = findMatchedMenuPath(menus, currentPath);
  if (!matchedPath || matchedPath.length === 0) return [];

  const deepest = matchedPath[matchedPath.length - 1];
  if (deepest.children?.length) {
    return filterVisibleMenuItems(deepest.children);
  }

  if (matchedPath.length >= 2) {
    const parent = matchedPath[matchedPath.length - 2];
    return filterVisibleMenuItems(parent.children);
  }

  return [];
};

/**
 * Get the first-layer siblings of the matched menu item for the current path.
 * If the matched item is at the first layer, returns its siblings.
 * If the matched item is deeper, returns the children of the first-layer ancestor.
 */
export const getFirstLayerSiblingMenuItems = (
  menus: MenuItem[],
  currentPath: string
): MenuItem[] => {
  const matchedPath = findMatchedMenuPath(menus, currentPath);
  if (!matchedPath || matchedPath.length === 0) return [];

  const firstLayer = matchedPath[0];
  return firstLayer.children ?? [];
};

const findClosestAncestorMenuWithChildren = (
  items: MenuItem[],
  currentPath: string
): MenuItem | null => {
  let best: MenuItem | null = null;

  for (const item of items) {
    if (item.isDirectory && item.children?.length) {
      const found = findClosestAncestorMenuWithChildren(item.children, currentPath);
      if (found) {
        const foundLen = found.url?.replace(/\/+$/, '').length ?? 0;
        const bestLen = best?.url?.replace(/\/+$/, '').length ?? -1;
        if (!best || foundLen > bestLen) best = found;
      }
      continue;
    }

    if (item.url) {
      const menu = item.url.replace(/\/+$/, '') || '/';
      const path = currentPath.replace(/\/+$/, '') || '/';
      if (menu !== path && path.startsWith(`${menu}/`)) {
        if (item.children?.length) {
          const nested = findClosestAncestorMenuWithChildren(item.children, currentPath) || item;
          const nestedLen = nested.url?.replace(/\/+$/, '').length ?? 0;
          const bestLen = best?.url?.replace(/\/+$/, '').length ?? -1;
          if (!best || nestedLen > bestLen) best = nested;
        } else {
          const itemLen = menu.length;
          const bestLen = best?.url?.replace(/\/+$/, '').length ?? -1;
          if (!best || itemLen > bestLen) best = item;
        }
      }
    }

    if (item.children?.length) {
      const found = findClosestAncestorMenuWithChildren(item.children, currentPath);
      if (found) {
        const foundLen = found.url?.replace(/\/+$/, '').length ?? 0;
        const bestLen = best?.url?.replace(/\/+$/, '').length ?? -1;
        if (!best || foundLen > bestLen) best = found;
      }
    }
  }
  return best;
};

export const getClosestAncestorMenuItems = (
  items: MenuItem[],
  currentPath: string
): MenuItem[] => {
  const matchedMenu = findClosestAncestorMenuWithChildren(items, currentPath);
  return filterVisibleMenuItems(matchedMenu?.children);
};

/** Colored `zhishiku` is a card glyph; chrome nav uses the line-style top-menu icon. */
export const resolveMenuIcon = (item: Pick<MenuItem, 'name' | 'icon'>): string => {
  if (item.name === 'wiki_list') {
    return 'zhishiku1';
  }
  return item.icon;
};
