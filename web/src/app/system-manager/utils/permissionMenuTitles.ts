import type { Menu } from '@/app/system-manager/types/application';

export interface AppMenuTitleNode {
  name?: string;
  title?: string;
  url?: string;
  children?: AppMenuTitleNode[];
}

const CLIENT_MENU_APP: Record<string, string> = {
  node: 'node-manager',
  patch: 'patch-manager',
};

function menuAppName(clientId: string): string {
  return CLIENT_MENU_APP[clientId] ?? clientId;
}

function belongsToApp(url: string | undefined, clientId: string): boolean {
  if (!url || !clientId) return false;
  const appName = url.split('/').filter(Boolean)[0];
  return appName === menuAppName(clientId);
}

interface MenuTitleEntry {
  title: string;
  groupTitle: string;
}

function collectAppMenuTitles(menus: AppMenuTitleNode[], clientId: string): Map<string, MenuTitleEntry> {
  const titles = new Map<string, MenuTitleEntry>();

  const visit = (nodes: AppMenuTitleNode[] | undefined, groupTitle: string | null) => {
    for (const node of nodes ?? []) {
      if (node.name && node.title && !titles.has(node.name)) {
        titles.set(node.name, {
          title: node.title,
          groupTitle: groupTitle || node.title,
        });
      }
      if (node.children?.length) {
        visit(node.children, node.title || groupTitle);
      }
    }
  };

  for (const root of menus) {
    if (!belongsToApp(root.url, clientId)) continue;
    visit([root], null);
  }

  return titles;
}

function groupTitleForChildren(node: Menu, titles: Map<string, MenuTitleEntry>): string | undefined {
  let selected: string | undefined;
  for (const child of node.children ?? []) {
    const groupTitle = titles.get(child.name)?.groupTitle;
    if (!groupTitle) continue;
    if (!selected) {
      selected = groupTitle;
      continue;
    }
    if (groupTitle !== selected) return undefined;
  }
  return selected;
}

function applyTitle(node: Menu, titles: Map<string, MenuTitleEntry>): Menu {
  const title = titles.get(node.name)?.title || groupTitleForChildren(node, titles);
  return {
    ...node,
    display_name: title || node.display_name,
    children: node.children?.map((child) => applyTitle(child, titles)),
  };
}

export function localizePermissionMenus(
  permissionMenus: Menu[],
  appMenus: AppMenuTitleNode[],
  clientId: string,
): Menu[] {
  const titles = collectAppMenuTitles(appMenus, clientId);
  return permissionMenus.map((node) => applyTitle(node, titles));
}
