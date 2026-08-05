'use client';

import { Tabs } from 'antd-mobile';
import type { ReactNode } from 'react';
import styles from './index.module.css';

interface MobileSegmentTabsProps {
  activeKey: string;
  onChange: (key: string) => void;
  children: ReactNode;
  className?: string;
}

export default function MobileSegmentTabs({
  activeKey,
  onChange,
  children,
  className,
}: MobileSegmentTabsProps) {
  return (
    <Tabs
      className={`${styles.tabs}${className ? ` ${className}` : ''}`}
      activeKey={activeKey}
      onChange={onChange}
    >
      {children}
    </Tabs>
  );
}

MobileSegmentTabs.Tab = Tabs.Tab;
