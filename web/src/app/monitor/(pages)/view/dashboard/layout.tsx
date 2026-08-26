'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { DashboardSidebar } from '@/app/monitor/dashboards/components/dashboard-sidebar';
import styles from '@/app/monitor/dashboards/components/dashboard-sidebar.module.scss';

/**
 * 侧栏放在 [objectKey] 之上，切换仪表盘时只换右侧内容，左侧对象树不重挂、不重新拉数。
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
    <div className={styles.layout}>
      <div className={styles.sidebar}>
        <DashboardSidebar currentObjectKey={objectKey} />
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
