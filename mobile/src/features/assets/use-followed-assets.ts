'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Toast } from 'antd-mobile';
import {
  addFollowedAsset,
  isAssetFollowed,
  removeFollowedAsset,
  type AssetInstance,
  type FollowedAssetsConfig,
} from '@/features/assets/model';
import { getFollowedConfig, updateFollowedConfig } from '@/features/assets/adapter';
import { readMobileViewSnapshot, writeMobileViewSnapshot, invalidateMobileViewSnapshot } from '@/navigation/mobile-view-cache';
import { useAuth } from '@/context/auth';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';

export type FollowedConfigStatus = 'loading' | 'ready' | 'error';

export function followKey(modelId: string, instanceId: string | number) {
  return `${modelId}:${String(instanceId)}`;
}

/** 关注状态变化后同步根页快照并标记脏，返回时先渲染再静默刷新 */
function patchRootSnapshot(cacheScope: string, modelId: string, asset: AssetInstance, nowFollowed: boolean) {
  const snapshot = readMobileViewSnapshot<{ followed?: AssetInstance[] }>(cacheScope, 'assets-root');
  if (snapshot && Array.isArray(snapshot.data.followed)) {
    const remaining = snapshot.data.followed.filter(
      (item) => !(item.modelId === modelId && String(item.id) === String(asset.id)),
    );
    writeMobileViewSnapshot(cacheScope, 'assets-root', {
      ...snapshot.data,
      followed: nowFollowed ? [asset, ...remaining] : remaining,
    }, snapshot.scrollTop);
  }
  invalidateMobileViewSnapshot(cacheScope, 'assets-root');
}

export function useFollowedAssets() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const [config, setConfig] = useState<FollowedAssetsConfig>({ items: [] });
  const [status, setStatus] = useState<FollowedConfigStatus>('loading');
  const [pendingKeys, setPendingKeys] = useState<ReadonlySet<string>>(new Set());
  const pendingRef = useRef(new Set<string>());
  const requestId = useRef(0);

  const reload = useCallback(async (signal?: AbortSignal) => {
    const current = ++requestId.current;
    setStatus('loading');
    try {
      const next = await getFollowedConfig(signal);
      if (current !== requestId.current) return;
      setConfig(next);
      setStatus('ready');
    } catch (error) {
      if (current !== requestId.current || signal?.aborted) return;
      setStatus('error');
      throw error;
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal).catch(() => undefined);
    return () => {
      requestId.current += 1;
      controller.abort();
    };
  }, [reload]);

  const isFollowed = useCallback(
    (modelId: string, instanceId: string | number) => isAssetFollowed(config, modelId, instanceId),
    [config],
  );

  const isPending = useCallback(
    (modelId: string, instanceId: string | number) => pendingKeys.has(followKey(modelId, instanceId)),
    [pendingKeys],
  );

  /** 返回新的关注状态；未执行（无权限/进行中）或失败时返回 null */
  const toggleFollow = useCallback(async (asset: AssetInstance, modelId = asset.modelId): Promise<boolean | null> => {
    const key = followKey(modelId, asset.id);
    if (status !== 'ready' || pendingRef.current.has(key)) return null;
    pendingRef.current.add(key);
    setPendingKeys(new Set(pendingRef.current));
    try {
      const latest = await getFollowedConfig();
      const next = isAssetFollowed(latest, modelId, asset.id)
        ? removeFollowedAsset(latest, modelId, asset.id)
        : addFollowedAsset(latest, modelId, asset.id);
      await updateFollowedConfig(next);
      setConfig(next);
      const nowFollowed = isAssetFollowed(next, modelId, asset.id);
      patchRootSnapshot(cacheScope, modelId, asset, nowFollowed);
      Toast.show({ icon: 'success', content: nowFollowed ? t('assets.followSuccess') : t('assets.unfollowSuccess') });
      return nowFollowed;
    } catch {
      Toast.show({ icon: 'fail', content: t('assets.followFailed') });
      return null;
    } finally {
      pendingRef.current.delete(key);
      setPendingKeys(new Set(pendingRef.current));
    }
  }, [cacheScope, status, t]);

  return { status, reload, isFollowed, isPending, toggleFollow };
}
