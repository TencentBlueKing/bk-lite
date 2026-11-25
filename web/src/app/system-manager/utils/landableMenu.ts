import type { LandableMenuNode } from '@/app/system-manager/types/menu';

/** A page a user can open: a non-empty URL that is not a directory or a hidden item. */
export function hasLandableMenuPage(menus: LandableMenuNode[] | null | undefined): boolean {
  if (!menus?.length) return false;
  return menus.some((node) => {
    const url = typeof node.url === 'string' ? node.url.trim() : '';
    if (url && !node.isNotMenuItem && !node.isDirectory) return true;
    return hasLandableMenuPage(node.children);
  });
}

/** Enable stays blocked when the saved tree has no page, including a tree of empty directories. */
export function customMenuLacksLandablePage(record: {
  menus?: LandableMenuNode[];
  menu_count?: number;
}): boolean {
  if (Array.isArray(record.menus)) return !hasLandableMenuPage(record.menus);
  return (record.menu_count ?? 0) === 0;
}
