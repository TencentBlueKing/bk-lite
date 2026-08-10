'use client';

import type { ReactNode } from 'react';
import { ErrorBlock, SpinLoading } from 'antd-mobile';
import styles from './index.module.css';

type ResultKind = 'empty' | 'error' | 'permission';
type SkeletonVariant = 'list' | 'tree' | 'detail' | 'metrics';

interface MobileResultProps {
  kind: ResultKind;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  action?: ReactNode;
  compact?: boolean;
}

interface MobileSkeletonProps {
  label: string;
  variant?: SkeletonVariant;
  rows?: number;
  compact?: boolean;
}

export function MobileResult({
  kind,
  title,
  description = '',
  actionLabel,
  onAction,
  action,
  compact = false,
}: MobileResultProps) {
  const error = kind === 'error';
  const content = action ?? (actionLabel && onAction ? (
    <button type="button" className={styles.action} onClick={onAction}>
      {actionLabel}
    </button>
  ) : null);

  return (
    <div
      className={`${styles.result} ${compact ? styles.resultCompact : ''}`}
      role={error ? 'alert' : 'status'}
    >
      <ErrorBlock
        status={kind === 'empty' ? 'empty' : error ? 'disconnected' : 'default'}
        title={title}
        description={description}
      >
        {content}
      </ErrorBlock>
    </div>
  );
}

function SkeletonRows({ rows }: { rows: number }) {
  return Array.from({ length: rows }, (_, index) => (
    <div className={styles.skeletonRow} key={index}>
      <span className={`${styles.skeletonBlock} ${styles.skeletonIcon}`} />
      <span className={styles.skeletonCopy}>
        <i className={`${styles.skeletonBlock} ${styles.skeletonTitle}`} />
        <i className={`${styles.skeletonBlock} ${styles.skeletonMeta}`} />
      </span>
    </div>
  ));
}

export function MobileSkeleton({
  label,
  variant = 'list',
  rows = 4,
  compact = false,
}: MobileSkeletonProps) {
  return (
    <div
      className={`${styles.skeleton} ${styles[`skeleton-${variant}`]} ${compact ? styles.skeletonCompact : ''}`}
      role="status"
      aria-busy="true"
      aria-label={label}
    >
      <span className={styles.srOnly}>{label}</span>
      {variant === 'detail' ? (
        <>
          <div className={styles.detailHero}>
            <i className={`${styles.skeletonBlock} ${styles.detailEyebrow}`} />
            <i className={`${styles.skeletonBlock} ${styles.detailTitle}`} />
            <i className={`${styles.skeletonBlock} ${styles.detailMeta}`} />
          </div>
          <SkeletonRows rows={Math.max(rows, 3)} />
        </>
      ) : variant === 'metrics' ? (
        Array.from({ length: rows }, (_, index) => (
          <div className={styles.metricSkeleton} key={index}>
            <i className={`${styles.skeletonBlock} ${styles.metricLabel}`} />
            <i className={`${styles.skeletonBlock} ${styles.metricValue}`} />
            <i className={`${styles.skeletonBlock} ${styles.metricChart}`} />
          </div>
        ))
      ) : (
        <SkeletonRows rows={rows} />
      )}
    </div>
  );
}

export function MobileAppLoading({ label }: { label: string }) {
  return (
    <div className={styles.appLoading} role="status" aria-live="polite" aria-label={label}>
      <span className={styles.loadingMark} aria-hidden="true">
        <SpinLoading color="primary" style={{ '--size': '26px' }} />
      </span>
      <span className={styles.loadingText}>{label}</span>
    </div>
  );
}
