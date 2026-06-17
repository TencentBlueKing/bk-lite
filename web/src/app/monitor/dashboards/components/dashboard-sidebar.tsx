'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { PROFESSIONAL_DASHBOARDS, PROFESSIONAL_DASHBOARD_GROUPS } from '../registry';
import { normalizeDashboardKey } from '../shared/utils';
import ObjectIcon from '@/app/monitor/components/objectIcon';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import styles from './dashboard-sidebar.module.scss';

interface DashboardSidebarProps {
  currentObjectKey: string;
}

const ICON_MAP: Record<string, string> = {
  mysql: 'mm-mysql_Mysql',
  redis: 'mm-redis_Redis',
  mongodb: 'mm-mongodb_Mongodb',
  mssql: 'mm-mssql_Mssql',
  nginx: 'mm-nginx_Nginx',
  docker: 'mm-docker_Docker',
  activemq: 'mm-activemq_ActiveMQ',
  apache: 'mm-apache_Apache',
  rabbitmq: 'mm-rabbitmq_Rabbitmq',
  tomcat: 'mm-tomcat_Tomcat',
  zookeeper: 'mm-zookeeper_Zookeeper',
  postgres: 'mm-postgresql_Postgresql',
  postgresql: 'mm-postgresql_Postgresql',
  elasticsearch: 'mm-elasticsearch_Elasticsearch',
  host: 'mm-host_主机',
  website: 'mm-website_网站',
  ping: 'mm-router_路由器'
};

const DEFAULT_ICON = 'mm-middleware_中间件';

export const DashboardSidebar = ({ currentObjectKey }: DashboardSidebarProps) => {
  const [searchValue, setSearchValue] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const router = useRouter();

  const normalizedSearch = searchValue.trim().toLowerCase();

  const groups = useMemo(() => {
    const grouped = Object.entries(PROFESSIONAL_DASHBOARD_GROUPS)
      .map(([groupKey, meta]) => {
        const items = PROFESSIONAL_DASHBOARDS.filter((item) => item.groupKey === groupKey);
        const groupMatched = meta.label.toLowerCase().includes(normalizedSearch);
        const filteredItems = !normalizedSearch
          ? items
          : items.filter((item) => {
            const searchableText = [
              item.key,
              item.objectName,
              item.objectDisplayName,
              ...(item.aliases || [])
            ]
              .filter(Boolean)
              .join(' ')
              .toLowerCase();
            return groupMatched || searchableText.includes(normalizedSearch);
          });

        return {
          key: groupKey,
          label: meta.label,
          order: meta.order,
          items: filteredItems.map((item) => ({
            key: item.key,
            label: item.objectDisplayName || item.objectName,
            iconKey: ICON_MAP[item.key] || DEFAULT_ICON
          }))
        };
      })
      .filter((group) => group.items.length > 0)
      .sort((a, b) => a.order - b.order);

    return grouped;
  }, [normalizedSearch]);

  useEffect(() => {
    setExpandedGroups((prev) => {
      const next = { ...prev };
      groups.forEach((group) => {
        if (!(group.key in next)) {
          next[group.key] = true;
        }
      });
      return next;
    });
  }, [groups]);

  const handleSelect = (key: string) => {
    router.push(`/monitor/view/dashboard/${key}`);
  };

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey]
    }));
  };

  const normalizedCurrent = normalizeDashboardKey(currentObjectKey);

  return (
    <ResizableSidebar collapseStorageKey="monitor.dashboard.sidebarCollapsed">
      <div className={styles.sidebarInner}>
        <div className={styles.searchBox}>
          <Input.Search
            placeholder="搜索..."
            className={styles.searchInput}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            allowClear
          />
        </div>
        <div className={styles.list}>
          {groups.map((group) => {
            const expanded = normalizedSearch ? true : expandedGroups[group.key];
            return (
              <div key={group.key} className={styles.group}>
                <button
                  type="button"
                  className={styles.groupHeader}
                  onClick={() => toggleGroup(group.key)}
                >
                  <span className={`${styles.groupArrow} ${expanded ? styles.groupArrowExpanded : ''}`}>
                    <DownOutlined />
                  </span>
                  <span className={styles.groupLabel}>{group.label}</span>
                </button>
                {expanded ? (
                  <div className={styles.groupItems}>
                    {group.items.map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        className={`${styles.item} ${normalizeDashboardKey(item.key) === normalizedCurrent ? styles.active : ''}`}
                        onClick={() => handleSelect(item.key)}
                      >
                        <span className={styles.itemBranch} />
                        <span className={styles.itemIcon}>
                          <ObjectIcon icon={item.iconKey} fallback={DEFAULT_ICON} />
                        </span>
                        <span className={styles.itemLabel}>{item.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </ResizableSidebar>
  );
};
