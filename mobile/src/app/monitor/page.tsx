'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import MobileSegmentTabs from '@/components/mobile-segment-tabs';
import MobileTabShell from '@/components/mobile-tab-shell';
import { MobileSkeleton } from '@/components/mobile-feedback';
import { useAuth } from '@/context/auth';
import MonitorInstancesPanel from '@/features/monitor/instances-panel';
import MonitorRecentViewsPanel from '@/features/monitor/recent-views-panel';
import {
  readMobileViewSnapshot,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/monitor/monitor.module.css';

interface MonitorRootViewState {
  activeTab: string;
}

function MonitorPageContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const params = useSearchParams();
  const objectId = Number(params.get('objectId')) || 0;
  const objectName = params.get('objectName') || '';
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const initialSnapshot = useRef(readMobileViewSnapshot<MonitorRootViewState>(cacheScope, 'monitor-root'));
  const [activeTab, setActiveTab] = useState(initialSnapshot.current?.data.activeTab || 'recent');

  useEffect(() => {
    writeMobileViewSnapshot<MonitorRootViewState>(cacheScope, 'monitor-root', { activeTab }, 0);
  }, [activeTab, cacheScope]);

  return (
    <MobileTabShell activeTab="monitor">
      <main className={styles.page}>
        <MobilePageHeader title={t('navigation.monitor')} />
        <MobileSegmentTabs activeKey={activeTab} onChange={setActiveTab}>
          <MobileSegmentTabs.Tab key="recent" title={t('monitor.tabs.recent')} />
          <MobileSegmentTabs.Tab key="all" title={t('monitor.tabs.all')} />
        </MobileSegmentTabs>
        {activeTab === 'recent' ? (
          <MonitorRecentViewsPanel />
        ) : (
          <MonitorInstancesPanel objectId={objectId} objectName={objectName} />
        )}
      </main>
    </MobileTabShell>
  );
}

export default function MonitorPage() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="list" rows={5} />}>
      <MonitorPageContent />
    </Suspense>
  );
}
