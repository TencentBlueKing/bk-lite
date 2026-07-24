'use client';

import { useState, type ReactNode } from 'react';
import { PullToRefresh, Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.css';

type PullStatus = 'pulling' | 'canRelease' | 'refreshing' | 'complete';

interface MobilePullToRefreshProps {
  children: ReactNode;
  disabled?: boolean;
  onRefresh: () => Promise<unknown>;
}

export default function MobilePullToRefresh({
  children,
  disabled = false,
  onRefresh,
}: MobilePullToRefreshProps) {
  const { t } = useTranslation();
  const [refreshFailed, setRefreshFailed] = useState(false);

  const statusText: Record<PullStatus, string> = {
    pulling: t('refresh.pulling'),
    canRelease: t('refresh.canRelease'),
    refreshing: t('refresh.refreshing'),
    complete: t('refresh.complete'),
  };

  const handleRefresh = async () => {
    setRefreshFailed(false);
    try {
      await onRefresh();
    } catch {
      setRefreshFailed(true);
      Toast.show({ content: t('refresh.failed'), icon: 'fail' });
    }
  };

  return (
    <div className={styles.root}>
      <PullToRefresh
        disabled={disabled}
        onRefresh={handleRefresh}
        renderText={(status) => (
          status === 'complete' && refreshFailed ? t('refresh.failed') : statusText[status]
        )}
      >
        {children}
      </PullToRefresh>
    </div>
  );
}
