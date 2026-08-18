'use client';

import type { ReactNode } from 'react';
import { SearchOutline } from 'antd-mobile-icons';
import { LeftOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import OrganizationSwitcher from '@/components/organization-switcher';
import MobileSafeHeader from '@/components/mobile-safe-header';
import { useMobileBack } from '@/navigation/mobile-back';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.css';

type SearchType = 'ConversationList' | 'WorkbenchPage';

interface SearchEntry {
  href: string;
  placeholder: string;
  onBeforeNavigate?: () => void;
}

interface MobilePageHeaderProps {
  title: string;
  searchType?: SearchType;
  searchEntry?: SearchEntry;
  backHref?: string;
  onBeforeBack?: () => boolean;
  showOrganization?: boolean;
  actions?: Array<{
    href: string;
    icon: ReactNode;
    label: string;
    onBeforeNavigate?: () => void;
  }>;
}

export default function MobilePageHeader({
  title,
  searchType,
  searchEntry,
  backHref,
  onBeforeBack,
  showOrganization = false,
  actions = [],
}: MobilePageHeaderProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const handleBack = useMobileBack({
    fallbackHref: backHref || '/workbench',
    onBeforeBack,
  });
  const showOrgTrigger = showOrganization && !backHref;
  const hideTitle = showOrgTrigger;
  const showTabSearchEntry = showOrgTrigger && Boolean(searchEntry);
  const headerClassName = [
    styles.headerContent,
    hideTitle ? styles.headerContentTabRoot : '',
    showTabSearchEntry ? styles.headerContentTabRootWithSearch : '',
  ].filter(Boolean).join(' ');

  return (
    <MobileSafeHeader
      contentClassName={headerClassName}
      elevated={showOrgTrigger}
    >
      <div className={`${styles.leading} ${showOrgTrigger ? styles.leadingOrganization : ''} ${showTabSearchEntry ? styles.leadingOrganizationWithSearch : ''}`.trim()}>
        {backHref ? (
          <button
            type="button"
            className={styles.backButton}
            aria-label={t('common.back')}
            onClick={handleBack}
          >
            <LeftOutline aria-hidden="true" />
          </button>
        ) : showOrgTrigger ? (
          <OrganizationSwitcher />
        ) : null}
      </div>

      {showTabSearchEntry && searchEntry ? (
        <button
          type="button"
          className={styles.searchEntry}
          aria-label={searchEntry.placeholder}
          onClick={() => {
            searchEntry.onBeforeNavigate?.();
            router.push(searchEntry.href);
          }}
        >
          <SearchOutline className={styles.searchEntryIcon} aria-hidden />
          <span className={styles.searchEntryPlaceholder}>{searchEntry.placeholder}</span>
        </button>
      ) : null}

      <div className={`${styles.titleGroup} ${hideTitle ? styles.titleGroupSrOnly : ''}`}>
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
            onClick={() => {
              action.onBeforeNavigate?.();
              router.push(action.href);
            }}
          >
            {action.icon}
            <span className={styles.actionLabel}>{action.label}</span>
          </button>
        ))}
        {!showTabSearchEntry && searchType ? (
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
        ) : null}
      </div>
    </MobileSafeHeader>
  );
}
