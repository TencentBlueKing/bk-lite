import { MenuItem } from '@/types/index';

/**
 * Find the complete menu path matching the current path (from top to deepest layer)
 * Recursively searches through menu items and their children to find the deepest match
 */
export const findMatchedMenuPath = (
  items: MenuItem[],
  currentPath: string,
  path: MenuItem[] = []
): MenuItem[] | null => {
  for (const item of items) {
    const matchedPath = [...path, item];

    if (item.url) {
      if (item.url === currentPath || currentPath.startsWith(item.url)) {
        if (item.children?.length) {
          const childMatch = findMatchedMenuPath(item.children, currentPath, matchedPath);
          if (childMatch) return childMatch;
        }
        return matchedPath;
      }
    }

    // Search in children even if parent has no url (e.g., directory-only items)
    if (item.children?.length) {
      const found = findMatchedMenuPath(item.children, currentPath, matchedPath);
      if (found) {
        return found;
      }
    }
  }
  return null;
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

/**
 * Get the deepest matched menu items for the current path.
 * Returns the children of the deepest matched item, or an empty array if no match.
 */
export const getDeepestMatchedMenuItems = (
  menus: MenuItem[],
  currentPath: string
): MenuItem[] => {
  const matchedPath = findMatchedMenuPath(menus, currentPath);
  if (!matchedPath || matchedPath.length === 0) return [];

  const deepest = matchedPath[matchedPath.length - 1];
  return deepest.children ?? [];
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

const filterVisibleMenuItems = (items: MenuItem[] = []): MenuItem[] =>
  items.filter((item) => !item.isNotMenuItem && !item.isDirectory);

const findClosestAncestorMenuWithChildren = (
  items: MenuItem[],
  currentPath: string
): MenuItem | null => {
  for (const item of items) {
    if (item.isDirectory && item.children?.length) {
      const found = findClosestAncestorMenuWithChildren(item.children, currentPath);
      if (found) return found;
      continue;
    }

    if (item.url && item.url !== currentPath && currentPath.startsWith(item.url)) {
      if (item.children?.length) {
        return findClosestAncestorMenuWithChildren(item.children, currentPath) || item;
      }
      return item;
    }

    if (item.children?.length) {
      const found = findClosestAncestorMenuWithChildren(item.children, currentPath);
      if (found) return found;
    }
  }
  return null;
};

export const getClosestAncestorMenuItems = (
  items: MenuItem[],
  currentPath: string
): MenuItem[] => {
  const matchedMenu = findClosestAncestorMenuWithChildren(items, currentPath);
  return filterVisibleMenuItems(matchedMenu?.children);
};
