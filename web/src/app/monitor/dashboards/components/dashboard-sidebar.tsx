'use client';

import React, { useState } from 'react';
import { Input } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { PROFESSIONAL_DASHBOARDS } from '../registry';
import { normalizeDashboardKey } from '../shared/utils';
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
  postgres: 'mm-postgresql_Postgresql',
  postgresql: 'mm-postgresql_Postgresql',
  elasticsearch: 'mm-elasticsearch_Elasticsearch',
  kafka: 'mm-kafka_Kafka',
  rabbitmq: 'mm-rabbitmq_Rabbitmq',
  zookeeper: 'mm-zookeeper_Zookeeper',
  activemq: 'mm-activemq_ActiveMQ',
  influxdb: 'mm-datastorage_数据存储',
  minio: 'mm-minio_Minio',
  consul: 'mm-middleware_中间件',
  etcd: 'mm-middleware_中间件',
  apache: 'mm-apache_Apache'
};

const DEFAULT_ICON = 'mm-middleware_中间件';

const ObjectIcon = ({ iconKey }: { iconKey: string }) => {
  const src = `/assets/icons/${iconKey}.svg`;
  return (
    <Image
      src={src}
      alt={iconKey}
      width={16}
      height={16}
      style={{ flexShrink: 0 }}
      onError={(e) => {
        (e.target as HTMLImageElement).src = `/assets/icons/${DEFAULT_ICON}.svg`;
      }}
    />
  );
};

export const DashboardSidebar = ({ currentObjectKey }: DashboardSidebarProps) => {
  const [collapsed, setCollapsed] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const router = useRouter();

  const items = PROFESSIONAL_DASHBOARDS.map((item) => ({
    key: item.key,
    label: item.objectDisplayName || item.objectName,
    iconKey: ICON_MAP[item.key] || DEFAULT_ICON
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
      <div className={styles.sidebarInner}>
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
              <span className={styles.itemIcon}><ObjectIcon iconKey={item.iconKey} /></span>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className={styles.toggleBtn} onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? <RightOutlined /> : <LeftOutlined />}
      </div>
    </div>
  );
};
