// bk-lite 侧栏不调用 fetchWeopsxCloudCatalog / toWeopsxCloudTreeNodes 挂叶。
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
  name?: string;
  cn_name?: string;
  children: WeopsxCloudTreeNode[];
}

const asText = (value: unknown): string => {
  if (value == null) return '';
  return String(value).trim();
};

export const weopsxCloudNavKey = (id: string): string =>
  `${WEOPSX_CLOUD_KEY_PREFIX}${id}`;

export const isWeopsxCloudNavKey = (key: unknown): boolean =>
  String(key ?? '').startsWith(WEOPSX_CLOUD_KEY_PREFIX);

const MIN_OVERLAP_TOKEN_LEN = 4;

export const foldCloudNavIdentity = (value: unknown): string =>
  asText(value)
    .toLowerCase()
    .replace(/[\s_\-]+/g, '');

export const collectCloudNavIdentityTokens = (...parts: unknown[]): string[] => {
  const tokens = new Set<string>();
  for (const part of parts) {
    const folded = foldCloudNavIdentity(part);
    if (folded) tokens.add(folded);
  }
  return [...tokens];
};

export const cloudNavIdentitiesOverlap = (left: string, right: string): boolean => {
  if (!left || !right) return false;
  if (left === right) return true;
  const [shorter, longer] =
    left.length <= right.length ? [left, right] : [right, left];
  return shorter.length >= MIN_OVERLAP_TOKEN_LEN && longer.includes(shorter);
};

export interface WeopsxCatalogIdentity {
  id?: string;
  name?: string;
  cn_name?: string;
  title?: unknown;
  label?: string;
  key?: string | number;
}

export const weopsxCatalogOverlapsLocalCloud = (
  item: WeopsxCatalogIdentity,
  localIdentities: Iterable<string>
): boolean => {
  const localTokens = [...localIdentities].filter(Boolean);
  if (!localTokens.length) return false;
  const keyText = asText(item.key);
  const idFromKey = isWeopsxCloudNavKey(keyText)
    ? keyText.slice(WEOPSX_CLOUD_KEY_PREFIX.length)
    : '';
  const catalogTokens = collectCloudNavIdentityTokens(
    item.id,
    item.name,
    item.cn_name,
    item.title,
    item.label,
    idFromKey
  );
  return catalogTokens.some((token) =>
    localTokens.some((localToken) => cloudNavIdentitiesOverlap(token, localToken))
  );
};

export const excludeWeopsxCatalogOverlaps = (
  items: WeopsxCloudCatalogItem[],
  localIdentities: Iterable<string>
): WeopsxCloudCatalogItem[] =>
  items.filter((item) => !weopsxCatalogOverlapsLocalCloud(item, localIdentities));

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
  items: WeopsxCloudCatalogItem[],
  localIdentities: Iterable<string> = []
): WeopsxCloudTreeNode[] =>
  excludeWeopsxCatalogOverlaps(items, localIdentities).map((item) => ({
    title: item.cn_name,
    label: item.cn_name,
    key: weopsxCloudNavKey(item.id),
    source: WEOPSX_CLOUD_NAV_SOURCE,
    deep_link: item.deep_link,
    count: item.children_count,
    name: item.name,
    cn_name: item.cn_name,
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

export const resolveWeopsxDeepLink = (deepLink: string): string => {
  const link = asText(deepLink);
  if (!link) return '';
  if (/^https?:\/\//i.test(link)) return link;
  return link.startsWith('/') ? link : `/${link}`;
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
