'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { DashboardSidebar } from '@/app/monitor/dashboards/components/dashboard-sidebar';
import {
  DashboardProtocolBarSlotProvider,
} from '@/app/monitor/dashboards/shared/widgets/dashboard-protocol-bar-slot';
import { DashboardProtocolBarHost } from '@/app/monitor/dashboards/shared/widgets/dashboard-protocol-bar-host';
import styles from '@/app/monitor/dashboards/components/dashboard-sidebar.module.scss';

/**
 * 侧栏放在 [objectKey] 之上，切换仪表盘时只换右侧内容，左侧对象树不重挂、不重新拉数。
 * 采集视图条在 layout 保活，经 portal 挂到各盘实例卡下方 slot。
 */
export default function ProfessionalDashboardLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname() || '';
  const segments = pathname.split('/').filter(Boolean);
  const dashboardIndex = segments.indexOf('dashboard');
  const objectKey =
    dashboardIndex >= 0 ? segments[dashboardIndex + 1] || '' : '';

  return (
    <DashboardProtocolBarSlotProvider>
      <div className={styles.layout}>
        <div className={styles.sidebar}>
          <DashboardSidebar currentObjectKey={objectKey} />
        </div>
        <div className={styles.content}>
          {children}
          <DashboardProtocolBarHost />
        </div>
      </div>
    </DashboardProtocolBarSlotProvider>
  );
}
