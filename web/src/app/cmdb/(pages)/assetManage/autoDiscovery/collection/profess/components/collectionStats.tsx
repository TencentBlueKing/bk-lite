'use client';

import React, { useState, useCallback, useEffect } from 'react';
import dayjs from 'dayjs';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DownOutlined,
  DoubleRightOutlined,
  ExclamationCircleOutlined,
  ProfileOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCollectApi } from '@/app/cmdb/api';

const AppstoreIcon = AppstoreOutlined as any;
const CheckCircleIcon = CheckCircleOutlined as any;
const ClockCircleIcon = ClockCircleOutlined as any;
const DownIcon = DownOutlined as any;
const DoubleRightIcon = DoubleRightOutlined as any;
const ExclamationCircleIcon = ExclamationCircleOutlined as any;
const ProfileIcon = ProfileOutlined as any;
const WarningIcon = WarningOutlined as any;

interface TaskOverview {
  total: number;
  normal: number;
  error: number;
  partial: number;
  recent_sync_at: string | null;
  covered_models: number;
}

const COLLAPSE_KEY = 'cmdb_collection_overview_collapsed';
const REFRESH_INTERVAL_MS = 30 * 1000;

const readCollapsed = (): boolean => {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) !== 'true';
  } catch {
    return true;
  }
};

const formatRelative = (iso: string | null, t: (k: string, d?: string, v?: Record<string, unknown>) => string): string => {
  if (!iso) return t('Collection.stats.never');
  const target = dayjs(iso);
  if (!target.isValid()) return t('Collection.stats.never');
  const diffSec = dayjs().diff(target, 'second');
  if (diffSec < 60) return t('Collection.stats.justNow');
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return t('Collection.stats.minutesAgo', '', { n: diffMin });
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return t('Collection.stats.hoursAgo', '', { n: diffHour });
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return t('Collection.stats.daysAgo', '', { n: diffDay });
  return target.format('YYYY-MM-DD');
};

const CollectionStats: React.FC = () => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const [expanded, setExpanded] = useState<boolean>(readCollapsed);
  const [overview, setOverview] = useState<TaskOverview | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchOverview = async () => {
      try {
        const data = (await collectApi.getTaskOverview()) as TaskOverview;
        if (!cancelled) setOverview(data || null);
      } catch (err) {
        console.error('Failed to fetch task overview:', err);
      }
    };
    fetchOverview();
    const timer = setInterval(fetchOverview, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // collectApi 由 hook 在每次渲染返回新引用，这里只在挂载时启动一次轮询
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? 'false' : 'true');
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const o: TaskOverview = overview || {
    total: 0,
    normal: 0,
    error: 0,
    partial: 0,
    recent_sync_at: null,
    covered_models: 0,
  };

  const cards: Array<{
    key: string;
    label: string;
    value: number | string;
    iconBg: string;
    iconColor: string;
    icon: React.ReactNode;
    valueClassName?: string;
  }> = [
    {
      key: 'total',
      label: t('Collection.stats.totalTasks'),
      value: o.total,
      iconBg: '#E8F0FF',
      iconColor: '#155AEF',
      icon: <ProfileIcon />,
    },
    {
      key: 'normal',
      label: t('Collection.stats.normalTasks'),
      value: o.normal,
      iconBg: '#E8FFEA',
      iconColor: '#00B42A',
      icon: <CheckCircleIcon />,
    },
    {
      key: 'error',
      label: t('Collection.stats.errorTasks'),
      value: o.error,
      iconBg: '#FFECE8',
      iconColor: '#F53F3F',
      icon: <ExclamationCircleIcon />,
    },
    {
      key: 'partial',
      label: t('Collection.stats.partialTasks'),
      value: o.partial,
      iconBg: '#FFF7E6',
      iconColor: '#F7BA1E',
      icon: <WarningIcon />,
    },
    {
      key: 'coveredModels',
      label: t('Collection.stats.coveredModels'),
      value: o.covered_models,
      iconBg: '#E8FFEA',
      iconColor: '#00B42A',
      icon: <AppstoreIcon />,
    },
    {
      key: 'recent',
      label: t('Collection.stats.recentSync'),
      value: formatRelative(o.recent_sync_at, t),
      iconBg: '#E8F0FF',
      iconColor: '#155AEF',
      valueClassName: 'text-[22px] xl:text-[24px] 2xl:text-[26px]',
      icon: <ClockCircleIcon />,
    },
  ];

  const toggleLabel = expanded
    ? t('Collection.stats.collapse')
    : t('Collection.stats.expand');

  return (
    <div className="shrink-0 px-2">
      {expanded && (
        <div className="relative pb-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {cards.map((c) => (
              <div
                key={c.key}
                className="flex min-h-[78px] items-center gap-2.5 rounded-md border border-[#d6deea] bg-white px-3 py-3 transition-colors hover:border-[#c5d0df] xl:gap-3.5 xl:px-4"
              >
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-[16px] xl:h-10 xl:w-10 xl:text-[18px]"
                  style={{ background: c.iconBg, color: c.iconColor }}
                >
                  {c.icon}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-[#5f6f86]">{c.label}</div>
                  <div className={`mt-1 whitespace-nowrap font-bold leading-none tracking-tight tabular-nums text-[#0f172a] ${c.valueClassName || 'text-[26px]'}`}>
                    {c.value}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Tooltip title={toggleLabel}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-label={toggleLabel}
              onClick={toggleExpanded}
              className="absolute bottom-[-6px] left-1/2 flex h-5 w-8 -translate-x-1/2 cursor-pointer items-center justify-center rounded-md bg-white/60 text-blue-400 transition-colors hover:bg-blue-50/70 hover:text-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              <DoubleRightIcon aria-hidden="true" className="-rotate-90 text-xs" />
            </button>
          </Tooltip>
        </div>
      )}
      {!expanded && (
        <div className="flex items-center pb-0 pt-1">
          <div className="h-px flex-1 bg-slate-200/50" />
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={toggleLabel}
            onClick={toggleExpanded}
            className="mx-3 flex h-6 cursor-pointer items-center gap-1.5 rounded-full border border-slate-200/60 bg-white/75 px-2.5 text-[11px] font-normal text-slate-400 transition-colors hover:border-blue-200 hover:bg-blue-50/80 hover:text-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
          >
            <AppstoreIcon aria-hidden="true" className="text-xs" />
            <span>{toggleLabel}</span>
            <DownIcon aria-hidden="true" className="text-[9px]" />
          </button>
          <div className="h-px flex-1 bg-slate-200/50" />
        </div>
      )}
    </div>
  );
};

export default CollectionStats;
