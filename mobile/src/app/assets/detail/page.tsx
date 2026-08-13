'use client';

import { Fragment, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SpinLoading, Toast } from 'antd-mobile';
import { AppstoreOutline, RightOutline, StarFill, StarOutline } from 'antd-mobile-icons';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import {
  addFollowedAsset,
  assetRequestErrorKind,
  assetValueText,
  isAssetFollowed,
  removeFollowedAsset,
  type AssetFieldGroup,
  type AssetInstance,
  type FollowedAssetsConfig,
} from '@/features/assets/model';
import { getAssetFieldGroups, getAssetInstance, getAssetModel, getFollowedConfig, updateFollowedConfig } from '@/features/assets/adapter';
import { resolveAssetModelIconUrl } from '@/features/assets/model-icon';
import AssetStructuredField from '@/features/assets/asset-structured-field';
import { useAuth } from '@/context/auth';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import { invalidateMobileViewSnapshot, readMobileViewSnapshot, writeMobileViewSnapshot } from '@/navigation/mobile-view-cache';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/assets/assets.module.css';

function AssetDetailContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const params = useSearchParams();
  const modelId = params.get('modelId') || '';
  const modelName = params.get('modelName') || modelId;
  const instanceId = params.get('instanceId') || '';
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const [asset, setAsset] = useState<AssetInstance | null>(null);
  const [groups, setGroups] = useState<AssetFieldGroup[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [config, setConfig] = useState<FollowedAssetsConfig>({ items: [] });
  const [followStatus, setFollowStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [resolvedModelId, setResolvedModelId] = useState(modelId);
  const [resolvedModelName, setResolvedModelName] = useState(modelName);
  const [modelIcon, setModelIcon] = useState('');
  const [iconFailed, setIconFailed] = useState(false);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'forbidden' | 'missing'>('loading');
  const [saving, setSaving] = useState(false);
  const requestId = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!instanceId || !modelId) {
      setStatus('error');
      return;
    }
    const currentId = ++requestId.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setStatus('loading');
    setFollowStatus('loading');
    try {
      const detail = await getAssetInstance(instanceId, controller.signal);
      const actualModelId = detail.modelId || modelId;
      const [fieldResult, followedResult, modelResult] = await Promise.allSettled([
        getAssetFieldGroups(actualModelId, controller.signal),
        getFollowedConfig(controller.signal),
        getAssetModel(actualModelId, controller.signal),
      ]);
      if (currentId !== requestId.current) return;
      if (fieldResult.status === 'rejected') throw fieldResult.reason;
      setAsset(detail);
      setGroups(fieldResult.value.groups);
      setExpandedGroups(new Set(fieldResult.value.groups.filter((group) => !group.collapsed).map((group) => String(group.id))));
      setResolvedModelId(fieldResult.value.modelId || actualModelId);
      setResolvedModelName(fieldResult.value.modelName || modelName);
      // 图标读取失败不阻塞详情；回退由 resolveAssetModelIconUrl 按内置模型与默认图处理
      if (modelResult.status === 'fulfilled' && modelResult.value) {
        setModelIcon(modelResult.value.icon);
      }
      if (followedResult.status === 'fulfilled') {
        setConfig(followedResult.value);
        setFollowStatus('ready');
      } else {
        setFollowStatus('error');
      }
      setStatus('ready');
    } catch (error) {
      if (controller.signal.aborted || currentId !== requestId.current) return;
      setStatus(assetRequestErrorKind(error));
    }
  }, [instanceId, modelId, modelName]);

  useEffect(() => {
    void load();
    return () => {
      requestId.current += 1;
      requestController.current?.abort();
    };
  }, [load]);

  const followed = useMemo(() => asset ? isAssetFollowed(config, resolvedModelId, asset.id) : false, [asset, config, resolvedModelId]);
  const toggleFollow = async () => {
    if (!asset || saving || followStatus !== 'ready') return;
    setSaving(true);
    try {
      const latest = await getFollowedConfig();
      const next = isAssetFollowed(latest, resolvedModelId, asset.id)
        ? removeFollowedAsset(latest, resolvedModelId, asset.id)
        : addFollowedAsset(latest, resolvedModelId, asset.id);
      await updateFollowedConfig(next);
      setConfig(next);
      const nowFollowed = isAssetFollowed(next, resolvedModelId, asset.id);
      const rootSnapshot = readMobileViewSnapshot<{
        activeTab: string;
        catalog: unknown;
        followed: AssetInstance[];
      }>(cacheScope, 'assets-root');
      if (rootSnapshot) {
        const remaining = rootSnapshot.data.followed.filter((item) => !(item.modelId === resolvedModelId && String(item.id) === String(asset.id)));
        writeMobileViewSnapshot(cacheScope, 'assets-root', {
          ...rootSnapshot.data,
          followed: nowFollowed ? [asset, ...remaining] : remaining,
        }, rootSnapshot.scrollTop);
      }
      invalidateMobileViewSnapshot(cacheScope, 'assets-root');
      Toast.show({ icon: 'success', content: nowFollowed ? t('assets.followSuccess') : t('assets.unfollowSuccess') });
    } catch {
      Toast.show({ icon: 'fail', content: t('assets.followFailed') });
    } finally {
      setSaving(false);
    }
  };

  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };
  const time = (value: string) => formatAccountDateTime(value, preferences);
  const followLabel = followStatus === 'error'
    ? t('assets.followUnavailable')
    : followed ? t('assets.unfollow') : t('assets.follow');
  const heroIconSrc = resolveAssetModelIconUrl(modelIcon, resolvedModelId);

  const backParams = new URLSearchParams();
  const classificationId = params.get('classificationId') || '';
  const classificationName = params.get('classificationName') || '';
  if (classificationId) backParams.set('classificationId', classificationId);
  if (classificationName) backParams.set('classificationName', classificationName);
  if (resolvedModelId || modelId) {
    backParams.set('modelId', resolvedModelId || modelId);
    backParams.set('modelName', resolvedModelName || modelName);
  }
  const backHref = backParams.toString() ? `/assets?${backParams.toString()}` : '/assets';

  if (status === 'loading') {
    return <main className={styles.page}><MobilePageHeader title={t('assets.detailTitle')} backHref={backHref} /><MobileSkeleton label={t('common.loading')} variant="detail" rows={5} /></main>;
  }
  if (status !== 'ready' || !asset) {
    const recoverable = status === 'error';
    return (
      <main className={styles.page}>
        <MobilePageHeader title={t('assets.detailTitle')} backHref={backHref} />
        <MobileResult
          kind={recoverable ? 'error' : 'permission'}
          title={status === 'forbidden' ? t('assets.detailForbidden') : status === 'missing' ? t('assets.detailMissing') : t('assets.detailLoadFailed')}
          description={recoverable ? t('assets.retryHint') : ''}
          actionLabel={recoverable ? t('common.retry') : undefined}
          onAction={recoverable ? () => void load() : undefined}
          action={!recoverable ? <Link className={styles.retry} href={backHref}>{t('assets.backToAssets')}</Link> : undefined}
        />
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <MobilePageHeader title={t('assets.detailTitle')} backHref={backHref} />
      <div className={styles.scroll}>
        <section className={styles.hero}>
          <div className={styles.heroTop}>
            <span className={styles.heroIcon}>
              {heroIconSrc && !iconFailed ? (
                <img
                  key={heroIconSrc}
                  className={styles.heroIconImage}
                  src={heroIconSrc}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  onError={() => setIconFailed(true)}
                />
              ) : (
                <AppstoreOutline aria-hidden="true" />
              )}
            </span>
            <div className={styles.heroCopy}>
              <span className={styles.heroModel}>{resolvedModelName}</span>
              <h1 className={styles.heroTitle}>{asset.name}</h1>
            </div>
            <button
              className={`${styles.followButton} ${followed ? styles.followButtonActive : ''}`}
              type="button"
              aria-label={followLabel}
              title={followLabel}
              disabled={saving || followStatus !== 'ready'}
              onClick={() => void toggleFollow()}
            >
              {saving
                ? <SpinLoading color="currentColor" style={{ '--size': '20px' }} />
                : followed ? <StarFill aria-hidden="true" /> : <StarOutline aria-hidden="true" />}
            </button>
          </div>
        </section>
        {groups.length === 0 ? (
          <MobileResult kind="empty" title={t('assets.noFieldGroups')} />
        ) : groups.map((group) => {
          const open = expandedGroups.has(String(group.id));
          return (
            <section className={styles.fieldGroup} key={group.id}>
              <button
                type="button"
                className={styles.groupToggle}
                aria-expanded={open}
                onClick={() => setExpandedGroups((current) => {
                  const next = new Set(current);
                  const key = String(group.id);
                  if (next.has(key)) next.delete(key);
                  else next.add(key);
                  return next;
                })}
              >
                <span>{group.name}</span>
                <RightOutline className={`${styles.groupChevron} ${open ? styles.groupChevronOpen : ''}`} aria-hidden="true" />
              </button>
              {open && (
                <div className={styles.fieldGrid}>
                  {group.fields.map((field) => {
                    const structured = field.type === 'table' || field.type === 'attachment' || field.type === 'image';
                    if (structured) {
                      return (
                        <div className={styles.structuredField} key={field.id}>
                          <span className={styles.structuredFieldLabel}>{field.name}</span>
                          <AssetStructuredField field={field} value={asset.values[field.id]} />
                        </div>
                      );
                    }
                    return (
                      <Fragment key={field.id}>
                        <span className={styles.fieldLabel}>{field.name}</span>
                        <span className={styles.fieldValue}>
                          {assetValueText(
                            field,
                            asset.values[field.id],
                            t('assets.yes'),
                            t('assets.no'),
                            time,
                            asset.values[`${field.id}_display`],
                          )}
                        </span>
                      </Fragment>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}

export default function AssetDetailPage() {
  const { t } = useTranslation();
  return <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="detail" rows={5} />}><AssetDetailContent /></Suspense>;
}
