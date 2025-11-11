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
  
  console.log('First layer:', firstLayer.name || firstLayer.title, 'hasDetail:', firstLayer.hasDetail);

  // If first layer has hasDetail flag, do NOT render menu (detail mode)
  if (firstLayer.hasDetail) {
    return false;
  }
  
  // Otherwise, render menu
  return true;
};
