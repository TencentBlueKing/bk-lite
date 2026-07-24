'use client';

import { useRouter } from 'next/navigation';
import { AppstoreOutline, UserOutline } from 'antd-mobile-icons';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.css';

export type MobileTabKey = 'apps' | 'profile';

interface MobileTabShellProps {
  activeTab: MobileTabKey;
  children: React.ReactNode;
}

const tabRoutes: Record<MobileTabKey, string> = {
  apps: '/workbench',
  profile: '/profile',
};

export default function MobileTabShell({ activeTab, children }: MobileTabShellProps) {
  const router = useRouter();
  const { t } = useTranslation();

  const tabs = [
    { key: 'apps' as const, icon: <AppstoreOutline />, label: t('navigation.apps') },
    { key: 'profile' as const, icon: <UserOutline />, label: t('navigation.profile') },
  ];

  const navigateToTab = (tab: MobileTabKey) => {
    if (tab === activeTab) return;
    router.replace(tabRoutes[tab]);
  };

  return (
    <div className={styles.shell}>
      <div className={styles.content}>{children}</div>
      <nav className={styles.bottomNav} aria-label={t('navigation.primaryNavigation')}>
        {tabs.map((tab) => {
          const active = tab.key === activeTab;
          return (
            <button
              type="button"
              key={tab.key}
              className={`${styles.navItem} ${active ? styles.navItemActive : ''}`}
              aria-current={active ? 'page' : undefined}
              onClick={() => navigateToTab(tab.key)}
            >
              <span className={styles.navIcon}>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
