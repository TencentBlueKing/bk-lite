'use client';

import React, { useState } from 'react';
import { Input } from 'antd';
import { LeftOutlined, RightOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { PROFESSIONAL_DASHBOARDS } from '../registry';
import { normalizeDashboardKey } from '../utils';
import styles from './dashboard-sidebar.module.scss';

interface DashboardSidebarProps {
  currentObjectKey: string;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  mysql: <DatabaseOutlined style={{ color: '#3E6D9C' }} />,
  redis: <DatabaseOutlined style={{ color: '#D12B1F' }} />,
  mongodb: <DatabaseOutlined style={{ color: '#4FAA41' }} />
};

export const DashboardSidebar = ({ currentObjectKey }: DashboardSidebarProps) => {
  const [collapsed, setCollapsed] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const router = useRouter();

  const items = PROFESSIONAL_DASHBOARDS.map((item) => ({
    key: item.key,
    label: item.objectDisplayName || item.objectName,
    icon: ICON_MAP[item.key] || <DatabaseOutlined />
  }));

  const filteredItems = searchValue
    ? items.filter((item) => item.label.toLowerCase().includes(searchValue.toLowerCase()))
    : items;

  const handleSelect = (key: string) => {
    router.push(`/monitor/view/dashboard/${key}`);
  };

  const normalizedCurrent = normalizeDashboardKey(currentObjectKey);

  return (
    <div className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`}>
      <div className={styles.searchBox}>
        <Input.Search
          placeholder="搜索..."
          size="small"
          className={styles.searchInput}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          allowClear
        />
      </div>
      <div className={styles.list}>
        {filteredItems.map((item) => (
          <div
            key={item.key}
            className={`${styles.item} ${normalizeDashboardKey(item.key) === normalizedCurrent ? styles.active : ''}`}
            onClick={() => handleSelect(item.key)}
          >
            <span className={styles.itemIcon}>{item.icon}</span>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
      <div className={styles.toggleBtn} onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? <RightOutlined /> : <LeftOutlined />}
      </div>
    </div>
  );
};
