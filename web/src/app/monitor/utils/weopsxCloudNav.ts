export const WEOPSX_CLOUD_NAV_SOURCE = 'weopsx';
export const WEOPSX_CLOUD_KEY_PREFIX = 'weopsx:';
export const WEOPSX_CLOUD_CATALOG_PATH = '/monitor/api/weopsx/cloud-catalog/';

export interface WeopsxCloudCatalogItem {
  id: string;
  name: string;
  cn_name: string;
  account_obj_id: string;
  children_count: number;
  deep_link: string;
}

export interface WeopsxCloudTreeNode {
  title: string;
  label: string;
  key: string;
  source: typeof WEOPSX_CLOUD_NAV_SOURCE;
  deep_link: string;
  count: number;
  children: WeopsxCloudTreeNode[];
}

type CatalogRequest = (
  url: string,
  config?: { suppressErrorNotification?: boolean; params?: Record<string, string> }
) => Promise<unknown>;

interface TreeNodeLike {
  key?: string | number;
  deep_link?: string;
  source?: string;
  children?: TreeNodeLike[];
}

const asText = (value: unknown): string => {
  if (value == null) return '';
  return String(value).trim();
};

export const weopsxCloudNavKey = (id: string): string =>
  `${WEOPSX_CLOUD_KEY_PREFIX}${id}`;

export const isWeopsxCloudNavKey = (key: unknown): boolean =>
  String(key ?? '').startsWith(WEOPSX_CLOUD_KEY_PREFIX);

const parseCatalogItems = (payload: unknown): WeopsxCloudCatalogItem[] => {
  const root = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray(root.items)
      ? root.items
      : [];
  const items: WeopsxCloudCatalogItem[] = [];
  for (const raw of rawItems) {
    if (!raw || typeof raw !== 'object') continue;
    const row = raw as Record<string, unknown>;
    const id = asText(row.id || row.name);
    if (!id) continue;
    const name = asText(row.name) || id;
    const cnName = asText(row.cn_name) || name;
    const deepLink = asText(row.deep_link);
    if (!deepLink) continue;
    const childrenCount = Number(row.children_count);
    items.push({
      id,
      name,
      cn_name: cnName,
      account_obj_id: asText(row.account_obj_id) || `${id}_account`,
      children_count: Number.isFinite(childrenCount) ? childrenCount : 0,
      deep_link: deepLink
    });
  }
  return items;
};

export const toWeopsxCloudTreeNodes = (
  items: WeopsxCloudCatalogItem[]
): WeopsxCloudTreeNode[] =>
  items.map((item) => ({
    title: item.cn_name,
    label: item.cn_name,
    key: weopsxCloudNavKey(item.id),
    source: WEOPSX_CLOUD_NAV_SOURCE,
    deep_link: item.deep_link,
    count: item.children_count,
    children: []
  }));

export const fetchWeopsxCloudCatalog = async (
  request: CatalogRequest
): Promise<WeopsxCloudCatalogItem[]> => {
  try {
    const payload = await request(WEOPSX_CLOUD_CATALOG_PATH, {
      suppressErrorNotification: true
    });
    const items = parseCatalogItems(payload);
    if (
      payload &&
      typeof payload === 'object' &&
      (payload as { degraded?: boolean }).degraded
    ) {
      console.warn('[monitor] WeOpsX cloud catalog degraded; sidebar keeps bk-lite cloud nodes');
    }
    return items;
  } catch (error) {
    console.warn(
      '[monitor] WeOpsX cloud catalog unavailable; sidebar keeps bk-lite cloud nodes',
      error
    );
    return [];
  }
};

export const findTreeNodeByKey = <T extends TreeNodeLike>(
  nodes: T[] | undefined,
  key: string
): T | undefined => {
  for (const node of nodes || []) {
    if (String(node.key) === String(key)) return node;
    const nested = findTreeNodeByKey((node.children || []) as T[], key);
    if (nested) return nested;
  }
  return undefined;
};

const weopsxPublicOrigin = (): string => {
  const raw = asText(
    typeof process !== 'undefined'
      ? process.env?.NEXT_PUBLIC_WEOPSX_BASE_URL
      : ''
  );
  return raw.replace(/\/$/, '');
};

export const resolveWeopsxDeepLink = (
  deepLink: string,
  origin = weopsxPublicOrigin()
): string => {
  const link = asText(deepLink);
  if (!link) return '';
  if (/^https?:\/\//i.test(link)) return link;
  const path = link.startsWith('/') ? link : `/${link}`;
  return origin ? `${origin}${path}` : path;
};

export const tryOpenWeopsxCloudNav = (
  key: string | number,
  tree: TreeNodeLike[]
): boolean => {
  if (!isWeopsxCloudNavKey(key)) return false;
  const node = findTreeNodeByKey(tree, String(key));
  const deepLink = resolveWeopsxDeepLink(asText(node?.deep_link));
  if (deepLink && typeof window !== 'undefined') {
    window.open(deepLink, '_blank', 'noopener,noreferrer');
  }
  return true;
};
