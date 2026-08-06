'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AppstoreOutline } from 'antd-mobile-icons';
import type { AssetInstance } from '@/features/assets/model';
import { resolveAssetModelIconUrl } from '@/features/assets/model-icon';
import { getStableTypeStyle } from '@/features/assets/type-style';
import styles from '@/features/assets/assets.module.css';

interface AssetListCardProps {
  asset: AssetInstance;
  modelName: string;
  modelIcon?: string;
  classificationId?: string;
  classificationName?: string;
  showModel?: boolean;
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
}: AssetListCardProps) {
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

  return (
    <Link className={styles.assetRow} href={`/assets/detail?${params.toString()}`}>
      <AssetLead modelIcon={modelIcon} modelId={asset.modelId} modelName={modelName} />
      <span className={styles.assetIdentity}>
        <span className={styles.assetName}>{asset.name}</span>
        {(showModel || organization) ? (
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
            {showModel && organization ? <span className={styles.assetMetaDot} aria-hidden="true">·</span> : null}
            {organization ? <span className={styles.assetMetaOrg}>{organization}</span> : null}
          </span>
        ) : null}
      </span>
      <span className={styles.assetTrailing}>
        {ipAddress ? <span className={styles.assetIp}>{ipAddress}</span> : <span className={styles.assetIpEmpty}>—</span>}
      </span>
    </Link>
  );
}
