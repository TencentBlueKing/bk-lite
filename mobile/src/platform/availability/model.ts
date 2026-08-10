export type MobileModuleKey = 'todo' | 'monitor' | 'assets' | 'apps' | 'profile';

export interface MenuNode {
  name: string;
  url?: string;
  operation?: string[];
  children?: MenuNode[];
  isNotMenuItem?: boolean;
  withParentPermission?: boolean;
}

export interface CustomMenuSelection {
  isBuiltIn: boolean;
  menus: MenuNode[];
}

export interface AvailabilityFacts {
  licensedClients: string[];
  staticMenus: MenuNode[];
  userMenusByClient: Partial<Record<BusinessClient, MenuNode[]>>;
  customMenusByClient: Partial<Record<BusinessClient, CustomMenuSelection>>;
}

export interface ResolvedAvailability {
  visibleModules: MobileModuleKey[];
  operations: Record<MobileModuleKey, string[]>;
}

export const BUSINESS_MODULE_ORDER = ['todo', 'monitor', 'assets', 'apps'] as const;
export type BusinessModuleKey = (typeof BUSINESS_MODULE_ORDER)[number];

export const MOBILE_MODULE_ORDER: readonly MobileModuleKey[] = [
  ...BUSINESS_MODULE_ORDER,
  'profile',
];

export const MODULE_ROOTS: Record<MobileModuleKey, string> = {
  todo: '/todo',
  monitor: '/monitor',
  assets: '/assets',
  apps: '/workbench',
  profile: '/profile',
};

export const MODULE_CONFIG = {
  todo: { client: 'alarm', menuName: 'Alarms' },
  monitor: { client: 'monitor', menuName: 'view_list' },
  assets: { client: 'cmdb', menuName: 'asset_info' },
  apps: { client: 'opspilot', menuName: 'bot_list' },
} as const satisfies Record<BusinessModuleKey, { client: string; menuName: string }>;

export type BusinessClient = (typeof MODULE_CONFIG)[BusinessModuleKey]['client'];

function collectPermissionOperations(
  nodes: MenuNode[],
  accumulated = new Map<string, string[]>(),
): Map<string, string[]> {
  for (const node of nodes) {
    accumulated.set(node.name, node.operation || []);
    if (node.children) collectPermissionOperations(node.children, accumulated);
  }
  return accumulated;
}

function filterMenusByPermission(
  permissionMap: Map<string, string[]>,
  nodes: MenuNode[],
  client: string,
  parent?: MenuNode,
): MenuNode[] {
  return nodes.flatMap((node) => {
    const children = node.children || [];

    if (children.length > 0 && !node.url) {
      const hasChildPermission = children.some((child) =>
        permissionMap.has(child.name) || Boolean(child.children?.length),
      );
      if (!hasChildPermission) return [];

      const filteredChildren = filterMenusByPermission(
        permissionMap,
        children,
        client,
        node,
      );
      if (filteredChildren.length === 0) return [];
      return [{ ...node, operation: ['View'], children: filteredChildren }];
    }

    const inheritsParent = Boolean(parent && node.withParentPermission);
    const hasPermittedChild = children.some((child) => permissionMap.has(child.name));
    const permitted = permissionMap.has(node.name)
      || Boolean(node.isNotMenuItem)
      || inheritsParent
      || hasPermittedChild;
    if (!permitted) return [];
    if (node.url && !node.url.includes(`/${client}/`)) return [];

    const filteredChildren = children.length > 0
      ? filterMenusByPermission(permissionMap, children, client, node)
      : [];
    const operation = node.isNotMenuItem
      ? ['View', ...(parent?.operation || [])]
      : permissionMap.get(node.name) || (inheritsParent ? parent?.operation || [] : []);

    return [{ ...node, operation, children: filteredChildren }];
  });
}

function findMenu(nodes: MenuNode[], name: string): MenuNode | undefined {
  for (const node of nodes) {
    if (node.name === name) return node;
    const match = node.children ? findMenu(node.children, name) : undefined;
    if (match) return match;
  }
  return undefined;
}

export function resolveAvailability(facts: AvailabilityFacts): ResolvedAvailability {
  const licensedClients = new Set(facts.licensedClients);
  const operations: Record<MobileModuleKey, string[]> = {
    todo: [],
    monitor: [],
    assets: [],
    apps: [],
    profile: [],
  };
  const visibleModules: MobileModuleKey[] = [];

  for (const moduleKey of BUSINESS_MODULE_ORDER) {
    const { client, menuName } = MODULE_CONFIG[moduleKey];
    if (!licensedClients.has(client)) continue;

    const userMenus = facts.userMenusByClient[client];
    if (!userMenus) continue;
    const permissionMap = collectPermissionOperations(userMenus);
    const customSelection = facts.customMenusByClient[client];
    const menuSource = customSelection && !customSelection.isBuiltIn
      ? customSelection.menus
      : facts.staticMenus;
    const filteredMenus = filterMenusByPermission(permissionMap, menuSource, client);
    const targetMenu = findMenu(filteredMenus, menuName);

    if (!targetMenu) continue;
    visibleModules.push(moduleKey);
    operations[moduleKey] = targetMenu.operation || [];
    if (moduleKey === 'assets' && findMenu(filteredMenus, 'search')) {
      operations[moduleKey] = [...operations[moduleKey], 'Search'];
    }
  }

  visibleModules.push('profile');
  return { visibleModules, operations };
}

export function resolveSafeModule(
  visibleModules: readonly MobileModuleKey[],
  preferred?: MobileModuleKey | null,
): MobileModuleKey {
  if (preferred && visibleModules.includes(preferred)) return preferred;
  return BUSINESS_MODULE_ORDER.find((module) => visibleModules.includes(module)) || 'profile';
}

export function moduleForPath(pathname: string): MobileModuleKey | null {
  if (pathname === '/todo' || pathname.startsWith('/todo/')) return 'todo';
  if (pathname === '/monitor' || pathname.startsWith('/monitor/')) return 'monitor';
  if (pathname === '/assets' || pathname.startsWith('/assets/')) return 'assets';
  if (
    pathname === '/workbench'
    || pathname.startsWith('/workbench/')
    || pathname === '/search'
    || pathname === '/conversations'
    || pathname === '/conversation'
  ) return 'apps';
  if (pathname === '/profile' || pathname.startsWith('/profile/')) return 'profile';
  return null;
}
