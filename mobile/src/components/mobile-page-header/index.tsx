'use client';

import type { ReactNode } from 'react';
import { SearchOutline } from 'antd-mobile-icons';
import { LeftOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import MobileSafeHeader from '@/components/mobile-safe-header';
import { useMobileBack } from '@/navigation/mobile-back';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.css';

type SearchType = 'ConversationList' | 'WorkbenchPage';

interface MobilePageHeaderProps {
  title: string;
  searchType?: SearchType;
  backHref?: string;
  actions?: Array<{
    href: string;
    icon: ReactNode;
    label: string;
  }>;
}

export default function MobilePageHeader({
  title,
  searchType,
  backHref,
  actions = [],
}: MobilePageHeaderProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const handleBack = useMobileBack({ fallbackHref: backHref || '/workbench' });

  return (
    <MobileSafeHeader contentClassName={styles.headerContent}>
      <div className={styles.leading}>
        {backHref && (
          <button
            type="button"
            className={styles.backButton}
            aria-label={t('common.back')}
            onClick={handleBack}
          >
            <LeftOutline aria-hidden="true" />
          </button>
        )}
      </div>

      <div className={styles.titleGroup}>
        <h1>{title}</h1>
      </div>

      <div className={styles.actions}>
        {actions.map((action) => (
          <button
            type="button"
            className={styles.actionButton}
            key={action.href}
            aria-label={action.label}
            title={action.label}
            onClick={() => router.push(action.href)}
          >
            {action.icon}
            <span className={styles.actionLabel}>{action.label}</span>
          </button>
        ))}
        {searchType && (
          <button
            type="button"
            className={styles.actionButton}
            aria-label={t('common.search')}
            title={t('common.search')}
            onClick={() => router.push(`/search?type=${searchType}`)}
          >
            <SearchOutline aria-hidden="true" />
            <span className={styles.actionLabel}>{t('common.search')}</span>
          </button>
        )}
      </div>
    </MobileSafeHeader>
  );
}
