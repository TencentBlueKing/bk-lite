'use client';

import React from 'react';
import { DashboardSidebar } from './dashboard-sidebar';
import styles from './dashboard-sidebar.module.scss';

interface DashboardLayoutProps {
  objectKey: string;
  children: React.ReactNode;
}

export const DashboardLayout = ({ objectKey, children }: DashboardLayoutProps) => {
  return (
    <div className={styles.layout}>
      <div className={styles.sidebar}>
        <DashboardSidebar currentObjectKey={objectKey} />
      </div>
      <div className={styles.content}>
        {children}
      </div>
    </div>
  );
};
