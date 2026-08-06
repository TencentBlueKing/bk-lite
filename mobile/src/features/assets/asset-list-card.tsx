'use client';

import { useState } from 'react';
import Link from 'next/link';
import { SpinLoading } from 'antd-mobile';
import { AppstoreOutline, StarFill, StarOutline } from 'antd-mobile-icons';
import type { AssetInstance } from '@/features/assets/model';
import { resolveAssetModelIconUrl } from '@/features/assets/model-icon';
import { getStableTypeStyle } from '@/features/assets/type-style';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/assets/assets.module.css';

interface AssetListCardProps {
  asset: AssetInstance;
  modelName: string;
  modelIcon?: string;
  classificationId?: string;
  classificationName?: string;
  showModel?: boolean;
  followed?: boolean;
  followPending?: boolean;
  followStatus?: 'loading' | 'ready' | 'error';
  onToggleFollow?: (asset: AssetInstance) => void;
}

function AssetLead({
  modelIcon,
  modelId,
  modelName,
}: {
  modelIcon?: string;
  modelId: string;
  modelName: string;
}) {
  const src = resolveAssetModelIconUrl(modelIcon, modelId);
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return (
      <span className={styles.assetLead}>
        <img
          className={styles.assetLeadImage}
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }
  return (
    <span className={styles.assetLead} aria-hidden="true" title={modelName}>
      <AppstoreOutline />
    </span>
  );
}

export default function AssetListCard({
  asset,
  modelName,
  modelIcon,
  classificationId,
  classificationName,
  showModel = true,
  followed = false,
  followPending = false,
  followStatus = 'ready',
  onToggleFollow,
}: AssetListCardProps) {
  const { t } = useTranslation();
  const params = new URLSearchParams({
    modelId: asset.modelId,
    modelName,
    instanceId: String(asset.id),
  });
  if (classificationId) params.set('classificationId', classificationId);
  if (classificationName) params.set('classificationName', classificationName);
  const ipAddress = typeof asset.values.ip_addr === 'string' ? asset.values.ip_addr.trim() : '';
  const organization = asset.organizationName.trim();
  const typeStyle = getStableTypeStyle(modelName);
  const followLabel = followStatus === 'error'
    ? t('assets.followUnavailable')
    : followed ? t('assets.unfollow') : t('assets.follow');

  return (
    <Link className={styles.assetRow} href={`/assets/detail?${params.toString()}`}>
      <AssetLead modelIcon={modelIcon} modelId={asset.modelId} modelName={modelName} />
      <span className={styles.assetIdentity}>
        <span className={styles.assetName}>{asset.name}</span>
        {(showModel || organization || ipAddress) ? (
          <span className={styles.assetMetaRow}>
            {showModel ? (
              <>
                <span
                  className={styles.assetMetaSwatch}
                  style={{ background: typeStyle.color }}
                  aria-hidden="true"
                />
                <span className={styles.assetMetaModel}>{modelName}</span>
              </>
            ) : null}
            {showModel && (organization || ipAddress) ? <span className={styles.assetMetaDot} aria-hidden="true">·</span> : null}
            {organization ? <span className={styles.assetMetaOrg}>{organization}</span> : null}
            {organization && ipAddress ? <span className={styles.assetMetaDot} aria-hidden="true">·</span> : null}
            {ipAddress ? <span className={styles.assetMetaIp}>{ipAddress}</span> : null}
          </span>
        ) : null}
      </span>
      <span className={styles.assetTrailing}>
        {onToggleFollow ? (
          <button
            type="button"
            className={`${styles.followButton} ${styles.cardFollow}${followed ? ` ${styles.followButtonActive}` : ''}`}
            aria-label={followLabel}
            title={followLabel}
            disabled={followPending || followStatus !== 'ready'}
            onClick={(event) => {
              // 星标在整卡 Link 内部，必须阻断冒泡与默认跳转
              event.preventDefault();
              event.stopPropagation();
              onToggleFollow(asset);
            }}
          >
            {followPending
              ? <SpinLoading color="currentColor" style={{ '--size': '16px' }} />
              : followed ? <StarFill aria-hidden="true" /> : <StarOutline aria-hidden="true" />}
          </button>
        ) : null}
      </span>
    </Link>
  );
}
