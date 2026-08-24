import { isCmdbInstUuid } from '@/app/cmdb/utils/instUuid';

export const FOLLOWED_ASSETS_CONFIG_KEY = 'cmdb_followed_assets';
export const MAX_FOLLOWED_ASSETS = 100;

export interface FollowedAssetItem {
  model_id: string;
  inst_uuid: string;
  followed_at: string;
}

/** 兼容读取旧配置中的 inst_id 字段；仅当其本身已是 UUIDv4 时才接受。 */
type FollowedAssetItemRaw = Partial<FollowedAssetItem> & {
  inst_id?: string | number;
};

export interface FollowedAssetsConfig {
  items: FollowedAssetItem[];
}

export interface FollowedAssetInstance {
  inst_uuid: string;
  model_id: string;
}

export interface ResolvedFollowedAsset<T extends FollowedAssetInstance> {
  item: FollowedAssetItem;
  detail: T;
}

const resolveInstUuid = (item: FollowedAssetItemRaw): string | null => {
  const value = item.inst_uuid ?? item.inst_id;
  if (!isCmdbInstUuid(value)) return null;
  return String(value).trim().toLowerCase();
};

const isSameAsset = (
  item: FollowedAssetItem,
  modelId: string,
  instUuid: string
) => item.model_id === modelId && String(item.inst_uuid) === String(instUuid);

export const normalizeFollowedAssetsConfig = (
  config?: Partial<FollowedAssetsConfig> | null
): FollowedAssetsConfig => ({
  items: sortFollowedAssets(
    Array.isArray(config?.items)
      ? config.items
        .map((raw): FollowedAssetItem | null => {
          if (!raw || typeof raw.model_id !== 'string' || !raw.model_id) {
            return null;
          }
          const instUuid = resolveInstUuid(raw as FollowedAssetItemRaw);
          if (!instUuid) return null;
          return {
            model_id: raw.model_id,
            inst_uuid: instUuid,
            followed_at:
                typeof raw.followed_at === 'string'
                  ? raw.followed_at
                  : new Date(0).toISOString(),
          };
        })
        .filter((item): item is FollowedAssetItem => item !== null)
      : []
  ).slice(0, MAX_FOLLOWED_ASSETS),
});

export const sortFollowedAssets = (items: FollowedAssetItem[]) =>
  [...items].sort(
    (a, b) =>
      new Date(b.followed_at || 0).getTime() -
      new Date(a.followed_at || 0).getTime()
  );

export const isFollowedAsset = (
  config: FollowedAssetsConfig,
  modelId: string,
  instUuid: string
) => config.items.some((item) => isSameAsset(item, modelId, instUuid));

export const addFollowedAsset = (
  config: FollowedAssetsConfig,
  asset: Pick<FollowedAssetItem, 'model_id' | 'inst_uuid'>,
  followedAt = new Date().toISOString()
): FollowedAssetsConfig => {
  const nextItem: FollowedAssetItem = {
    model_id: asset.model_id,
    inst_uuid: asset.inst_uuid,
    followed_at: followedAt,
  };
  const restItems = config.items.filter(
    (item) => !isSameAsset(item, asset.model_id, asset.inst_uuid)
  );
  return {
    items: sortFollowedAssets([nextItem, ...restItems]).slice(
      0,
      MAX_FOLLOWED_ASSETS
    ),
  };
};

export const removeFollowedAsset = (
  config: FollowedAssetsConfig,
  modelId: string,
  instUuid: string
): FollowedAssetsConfig => ({
  items: config.items.filter((item) => !isSameAsset(item, modelId, instUuid)),
});

export const resolveVisibleFollowedAssets = async <
  T extends FollowedAssetInstance,
>(
  items: FollowedAssetItem[],
  fetchInstances: (
    modelId: string,
    instanceUuids: string[]
  ) => Promise<T[]>,
  limit: number
): Promise<Array<ResolvedFollowedAsset<T>>> => {
  if (limit <= 0 || items.length === 0) return [];

  const itemsByModel = new Map<string, FollowedAssetItem[]>();
  items.forEach((item) => {
    const modelItems = itemsByModel.get(item.model_id) || [];
    modelItems.push(item);
    itemsByModel.set(item.model_id, modelItems);
  });

  const settled = await Promise.allSettled(
    Array.from(itemsByModel.entries()).map(async ([modelId, modelItems]) => ({
      modelId,
      instances: await fetchInstances(
        modelId,
        modelItems.map((item) => item.inst_uuid)
      ),
    }))
  );
  const instanceByAsset = new Map<string, T>();
  settled.forEach((result) => {
    if (result.status !== 'fulfilled') return;
    result.value.instances.forEach((instance) => {
      instanceByAsset.set(
        `${result.value.modelId}:${String(instance.inst_uuid)}`,
        instance
      );
    });
  });

  const resolved: Array<ResolvedFollowedAsset<T>> = [];
  for (const item of items) {
    const detail = instanceByAsset.get(
      `${item.model_id}:${String(item.inst_uuid)}`
    );
    if (!detail) continue;
    resolved.push({ item, detail });
    if (resolved.length === limit) break;
  }
  return resolved;
};
