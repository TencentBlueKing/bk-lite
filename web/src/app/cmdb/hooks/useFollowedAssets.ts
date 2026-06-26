'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { useUserConfigApi } from '@/app/cmdb/api';
import {
  addFollowedAsset,
  FOLLOWED_ASSETS_CONFIG_KEY,
  FollowedAssetItem,
  FollowedAssetsConfig,
  isFollowedAsset,
  normalizeFollowedAssetsConfig,
  removeFollowedAsset,
} from '@/app/cmdb/utils/followedAssets';

export const useFollowedAssets = () => {
  const { getConfigByKey, updateConfig } = useUserConfigApi();
  const [config, setConfig] = useState<FollowedAssetsConfig>({ items: [] });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getConfigByKey<Partial<FollowedAssetsConfig>>(
        FOLLOWED_ASSETS_CONFIG_KEY
      );
      const nextConfig = normalizeFollowedAssetsConfig(data);
      setConfig(nextConfig);
      return nextConfig;
    } finally {
      setLoading(false);
    }
  }, [getConfigByKey]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const followAsset = useCallback(
    async (asset: Pick<FollowedAssetItem, 'model_id' | 'inst_id'>) => {
      setSubmitting(true);
      try {
        const nextConfig = addFollowedAsset(config, asset);
        setConfig(nextConfig);
        try {
          await updateConfig(FOLLOWED_ASSETS_CONFIG_KEY, nextConfig);
        } catch (error) {
          setConfig(config);
          throw error;
        }
        return nextConfig;
      } finally {
        setSubmitting(false);
      }
    },
    [config, updateConfig]
  );

  const unfollowAsset = useCallback(
    async (modelId: string, instId: string | number) => {
      setSubmitting(true);
      try {
        const nextConfig = removeFollowedAsset(config, modelId, instId);
        setConfig(nextConfig);
        try {
          await updateConfig(FOLLOWED_ASSETS_CONFIG_KEY, nextConfig);
        } catch (error) {
          setConfig(config);
          throw error;
        }
        return nextConfig;
      } finally {
        setSubmitting(false);
      }
    },
    [config, updateConfig]
  );

  const isFollowed = useCallback(
    (modelId: string, instId: string | number) =>
      isFollowedAsset(config, modelId, instId),
    [config]
  );

  const items = useMemo(() => config.items, [config.items]);

  return {
    items,
    loading,
    submitting,
    refresh,
    isFollowed,
    followAsset,
    unfollowAsset,
  };
};
