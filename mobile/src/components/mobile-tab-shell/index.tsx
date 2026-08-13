'use client';

import { useRouter } from 'next/navigation';
import {
  AppstoreOutline,
  FolderOutline,
  HistogramOutline,
  UnorderedListOutline,
  UserOutline,
} from 'antd-mobile-icons';
import { useTranslation } from '@/utils/i18n';
import { useMobileAvailability } from '@/platform/availability/context';
import {
  MOBILE_MODULE_ORDER,
  MODULE_ROOTS,
  type MobileModuleKey,
} from '@/platform/availability/model';
import styles from './index.module.css';

export type MobileTabKey = MobileModuleKey;

interface MobileTabShellProps {
  activeTab: MobileTabKey;
  children: React.ReactNode;
}

export default function MobileTabShell({ activeTab, children }: MobileTabShellProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const { visibleModules, rememberModule } = useMobileAvailability();

  const tabDefinitions: Record<MobileTabKey, { icon: React.ReactNode; label: string }> = {
    todo: { icon: <UnorderedListOutline />, label: t('navigation.todo') },
    monitor: { icon: <HistogramOutline />, label: t('navigation.monitor') },
    assets: { icon: <FolderOutline />, label: t('navigation.assets') },
    apps: { icon: <AppstoreOutline />, label: t('navigation.apps') },
    profile: { icon: <UserOutline />, label: t('navigation.profile') },
  };
  const tabs = MOBILE_MODULE_ORDER
    .filter((key) => visibleModules.includes(key))
    .map((key) => ({ key, ...tabDefinitions[key] }));

  const navigateToTab = (tab: MobileTabKey) => {
    if (tab === activeTab) return;
    rememberModule(tab);
    router.replace(MODULE_ROOTS[tab]);
  };

  return (
    <div className={styles.shell}>
      <div className={styles.content}>{children}</div>
      <nav
        className={styles.bottomNav}
        aria-label={t('navigation.primaryNavigation')}
        style={{ '--mobile-tab-count': tabs.length } as React.CSSProperties}
      >
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
              <span className={styles.navItemInner}>
                <span className={styles.navIcon}>{tab.icon}</span>
                <span className={styles.navLabel}>{tab.label}</span>
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
