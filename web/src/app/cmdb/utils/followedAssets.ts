export const FOLLOWED_ASSETS_CONFIG_KEY = 'cmdb_followed_assets';
export const MAX_FOLLOWED_ASSETS = 100;

export interface FollowedAssetItem {
  model_id: string;
  inst_id: string | number;
  followed_at: string;
}

export interface FollowedAssetsConfig {
  items: FollowedAssetItem[];
}

export interface FollowedAssetInstance {
  _id: string | number;
  model_id: string;
}

export interface ResolvedFollowedAsset<T extends FollowedAssetInstance> {
  item: FollowedAssetItem;
  detail: T;
}

const isSameAsset = (
  item: FollowedAssetItem,
  modelId: string,
  instId: string | number
) => item.model_id === modelId && String(item.inst_id) === String(instId);

export const normalizeFollowedAssetsConfig = (
  config?: Partial<FollowedAssetsConfig> | null
): FollowedAssetsConfig => ({
  items: sortFollowedAssets(
    Array.isArray(config?.items)
      ? config.items.filter(
        (item): item is FollowedAssetItem =>
          !!item &&
          typeof item.model_id === 'string' &&
          item.model_id.length > 0 &&
          item.inst_id !== undefined &&
          item.inst_id !== null
      )
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
  instId: string | number
) => config.items.some((item) => isSameAsset(item, modelId, instId));

export const addFollowedAsset = (
  config: FollowedAssetsConfig,
  asset: Pick<FollowedAssetItem, 'model_id' | 'inst_id'>,
  followedAt = new Date().toISOString()
): FollowedAssetsConfig => {
  const nextItem: FollowedAssetItem = {
    model_id: asset.model_id,
    inst_id: asset.inst_id,
    followed_at: followedAt,
  };
  const restItems = config.items.filter(
    (item) => !isSameAsset(item, asset.model_id, asset.inst_id)
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
  instId: string | number
): FollowedAssetsConfig => ({
  items: config.items.filter((item) => !isSameAsset(item, modelId, instId)),
});

export const resolveVisibleFollowedAssets = async <
  T extends FollowedAssetInstance,
>(
  items: FollowedAssetItem[],
  fetchInstances: (
    modelId: string,
    instanceIds: Array<string | number>
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
        modelItems.map((item) => item.inst_id)
      ),
    }))
  );
  const instanceByAsset = new Map<string, T>();
  settled.forEach((result) => {
    if (result.status !== 'fulfilled') return;
    result.value.instances.forEach((instance) => {
      instanceByAsset.set(
        `${result.value.modelId}:${String(instance._id)}`,
        instance
      );
    });
  });

  const resolved: Array<ResolvedFollowedAsset<T>> = [];
  for (const item of items) {
    const detail = instanceByAsset.get(
      `${item.model_id}:${String(item.inst_id)}`
    );
    if (!detail) continue;
    resolved.push({ item, detail });
    if (resolved.length === limit) break;
  }
  return resolved;
};
