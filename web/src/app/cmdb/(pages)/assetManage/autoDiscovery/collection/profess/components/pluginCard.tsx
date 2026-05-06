'use client';

import React from 'react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';

const DEFAULT_COLLECTION_ICON = '/assets/icons/cc-default_默认.svg';

const COLLECTION_ICON_MAP: Array<{ keywords: string[]; src: string }> = [
  {
    keywords: ['k8s', 'kubernetes'],
    src: '/assets/icons/cc-k8s-cluster_K8S集群.svg',
  },
  {
    keywords: ['docker'],
    src: '/assets/icons/cc-docker_Docker.svg',
  },
  {
    keywords: ['vcenter', 'vmware', 'esxi'],
    src: '/assets/icons/cc-esxi-host_ESXi.svg',
  },
  {
    keywords: ['network', 'snmp', 'switch', 'router'],
    src: '/assets/icons/cc-router_路由器.svg',
  },
  {
    keywords: ['mssql', 'sql_server', 'sql server'],
    src: '/assets/icons/cc-sql-server_MSSQL.svg',
  },
  {
    keywords: ['mysql'],
    src: '/assets/icons/cc-mysql_MySQL.svg',
  },
  {
    keywords: ['postgresql', 'postgres'],
    src: '/assets/icons/cc-postgresql_PostgreSQL.svg',
  },
  {
    keywords: ['redis'],
    src: '/assets/icons/cc-redis_REDIS.svg',
  },
  {
    keywords: ['mongodb', 'mongo'],
    src: '/assets/icons/cc-mongodb_MongoDB.svg',
  },
  {
    keywords: ['rabbitmq'],
    src: '/assets/icons/cc-rabbitmq_RabbitMQ.svg',
  },
  {
    keywords: ['kafka'],
    src: '/assets/icons/cc-kafka_Kafka.svg',
  },
  {
    keywords: ['nginx'],
    src: '/assets/icons/cc-nginx_Nginx.svg',
  },
  {
    keywords: ['oracle'],
    src: '/assets/icons/cc-oracle_Oracle.svg',
  },
  {
    keywords: ['tidb'],
    src: '/assets/icons/cc-tidb_TiDB.svg',
  },
  {
    keywords: ['cloud'],
    src: '/assets/icons/cc-cloud_云.svg',
  },
  {
    keywords: ['host', 'linux', 'windows'],
    src: '/assets/icons/cc-host_主机.svg',
  },
];

const getCollectionIconSrc = (tab: TreeNode) => {
  const searchText = [tab.model_id, tab.id, tab.name, tab.type, tab.task_type]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return (
    COLLECTION_ICON_MAP.find(({ keywords }) =>
      keywords.some((keyword) => searchText.includes(keyword)),
    )?.src || DEFAULT_COLLECTION_ICON
  );
};

interface ExpandableTextProps {
  text?: string;
  collapsedLines?: 2 | 3;
}

interface PluginCardProps {
  tab: TreeNode;
  isActive: boolean;
  onSelect: (pluginId: string) => void;
  runningLabel: string;
  successLabel: string;
  failedLabel: string;
  runningCount: number;
  successCount: number;
  failedCount: number;
}

const ExpandableText: React.FC<ExpandableTextProps> = ({
  text,
  collapsedLines = 3,
}) => {
  if (!text) {
    return null;
  }

  return (
    <div
      className={`mt-1.5 text-xs leading-5 text-slate-500 ${collapsedLines === 3 ? 'line-clamp-3' : 'line-clamp-2'}`}
    >
      {text}
    </div>
  );
};

const PluginCard: React.FC<PluginCardProps> = React.memo(
  ({
    tab,
    isActive,
    onSelect,
    runningLabel,
    successLabel,
    failedLabel,
    runningCount,
    successCount,
    failedCount,
  }) => {
    const tags = tab.tag || [];
    const description = tab.desc || '';
    const iconSrc = getCollectionIconSrc(tab);

    const statusItems = [
      {
        dotClass: 'bg-blue-500',
        label: runningLabel,
        value: runningCount,
      },
      {
        dotClass: 'bg-green-500',
        label: successLabel,
        value: successCount,
      },
      {
        dotClass: 'bg-rose-500',
        label: failedLabel,
        value: failedCount,
      },
    ];

    return (
      <div
        role="button"
        tabIndex={0}
        className={`group relative w-full shrink-0 cursor-pointer overflow-hidden rounded-2xl border transition-all duration-200 ${
          isActive
            ? 'border-slate-200 bg-white shadow-[0_14px_30px_rgba(59,130,246,0.12),0_4px_12px_rgba(15,23,42,0.05)]'
            : 'border-slate-200 bg-white hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_12px_24px_rgba(15,23,42,0.08)]'
        } p-3 text-left`}
        onClick={() => onSelect(tab.id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect(tab.id);
          }
        }}
      >
        <div
          className={`pointer-events-none absolute inset-0 transition-opacity ${
            isActive
              ? 'bg-[radial-gradient(circle_at_top_left,rgba(147,197,253,0.24),transparent_44%),radial-gradient(circle_at_92%_100%,rgba(186,230,253,0.18),transparent_36%)] opacity-100'
              : 'bg-[radial-gradient(circle_at_top_left,rgba(226,232,240,0.28),transparent_42%)] opacity-0 group-hover:opacity-100'
          }`}
        />

        <div className="relative z-10 flex items-start gap-2.5">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-sm transition-colors ${
              isActive
                ? 'border-sky-200 bg-sky-50/70 shadow-[0_8px_18px_rgba(59,130,246,0.12)]'
                : 'border-slate-200 bg-slate-50 group-hover:border-blue-100 group-hover:bg-blue-50'
            }`}
          >
            <Image
              src={iconSrc}
              alt={tab.name}
              width={26}
              height={26}
              unoptimized
              className={`${isActive ? 'opacity-100' : 'opacity-80 group-hover:opacity-100'}`}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div
                  className={`text-sm font-semibold leading-5 tracking-[0.01em] wrap-break-word ${isActive ? 'text-blue-700' : 'text-slate-900'}`}
                >
                  {tab.name}
                </div>
                <ExpandableText text={description} collapsedLines={2} />
              </div>
              <div
                className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${isActive ? 'bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.12)]' : 'bg-slate-200 group-hover:bg-blue-300'}`}
              />
            </div>

            {tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[11px] leading-4 text-slate-500">
                {tags.map((tag: string) => (
                  <span
                    key={tag}
                    className={`inline-flex items-center wrap-break-word ${isActive ? 'text-blue-700/85' : 'text-slate-500'}`}
                  >
                    <span
                      className={`mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-blue-300' : 'bg-slate-300'}`}
                    />
                    <span className="break-keep">{tag}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <Tooltip
          placement="left"
          title={
            <div className="flex flex-col gap-1.5">
              {statusItems.map(({ dotClass, value, label }) => (
                <div
                  key={label}
                  className="flex items-center gap-2 text-xs text-white/95"
                >
                  <div
                    className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`}
                  />
                  <span>
                    {label}：{value}
                  </span>
                </div>
              ))}
            </div>
          }
        >
          <div
            className="mt-3 border-t pt-2"
            style={{ borderColor: 'var(--color-border-2)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center">
              {statusItems.map(({ dotClass, value, label }, index) => (
                <div
                  key={label}
                  className={`flex flex-1 items-center justify-center ${index < statusItems.length - 1 ? 'border-r border-slate-200/70' : ''}`}
                >
                  <div
                    className={`flex min-w-10.5 items-center justify-center gap-1.5 rounded-lg px-1.5 py-0.5 transition-colors ${isActive ? 'hover:bg-blue-50/80' : 'hover:bg-slate-100/80'}`}
                    aria-label={`${label}：${value}`}
                  >
                    <div
                      className={`h-2 w-2 shrink-0 rounded-full ${dotClass} ring-2 ring-white shadow-sm`}
                    />
                    <span className="text-sm font-semibold leading-none tabular-nums text-slate-800">
                      {value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Tooltip>
      </div>
    );
  },
);

PluginCard.displayName = 'PluginCard';

export default PluginCard;
