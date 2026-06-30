'use client';

import React, { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { PROFESSIONAL_DASHBOARDS, PROFESSIONAL_DASHBOARD_GROUPS } from '../registry';
import { normalizeDashboardKey } from '../shared/utils';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { TreeItem } from '@/app/monitor/types';
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
  const router = useRouter();
  const normalizedCurrent = normalizeDashboardKey(currentObjectKey);

  const groups = useMemo(() => {
    return Object.entries(PROFESSIONAL_DASHBOARD_GROUPS)
      .map(([groupKey, meta]) => {
        const items = PROFESSIONAL_DASHBOARDS.filter((item) => item.groupKey === groupKey);

        return {
          key: groupKey,
          title: meta.label,
          order: meta.order,
          children: items.map((item) => ({
            key: item.key,
            title: item.objectDisplayName || item.objectName,
            label: item.objectName,
            icon: ICON_MAP[item.key] || DEFAULT_ICON,
            children: []
          }))
        };
      })
      .filter((group) => group.children.length > 0)
      .sort((a, b) => a.order - b.order)
      .map((group) => ({
        key: group.key,
        title: group.title,
        children: group.children
      })) as TreeItem[];
  }, []);

  const handleSelect = (key: string) => {
    router.push(`/monitor/view/dashboard/${key}`);
  };

  return (
    <ResizableSidebar collapseStorageKey="monitor.dashboard.sidebarCollapsed">
      <div className={styles.sidebarInner}>
        <TreeSelector
          data={groups}
          defaultSelectedKey={normalizedCurrent}
          onNodeSelect={handleSelect}
        />
      </div>
    </ResizableSidebar>
  );
};
