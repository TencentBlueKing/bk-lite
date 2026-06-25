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
