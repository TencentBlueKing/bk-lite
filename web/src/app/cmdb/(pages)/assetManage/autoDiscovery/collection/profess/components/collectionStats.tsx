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

export interface CollectionStatsProps {
  activeKey?: string | null;
  onSelectStat?: (key: string) => void;
}

const ACTIVE_CARD_STYLES: Record<string, string> = {
  total: 'border-blue-500 bg-blue-50/25 ring-2 ring-blue-100 shadow-[0_4px_16px_rgba(37,99,235,0.1)]',
  normal: 'border-emerald-500 bg-emerald-50/25 ring-2 ring-emerald-100 shadow-[0_4px_16px_rgba(5,150,105,0.1)]',
  error: 'border-rose-500 bg-rose-50/25 ring-2 ring-rose-100 shadow-[0_4px_16px_rgba(220,38,38,0.1)]',
  partial: 'border-amber-500 bg-amber-50/25 ring-2 ring-amber-100 shadow-[0_4px_16px_rgba(217,119,6,0.1)]',
  coveredModels: 'border-teal-500 bg-teal-50/25 ring-2 ring-teal-100 shadow-[0_4px_16px_rgba(13,148,136,0.1)]',
  recent: 'border-purple-500 bg-purple-50/25 ring-2 ring-purple-100 shadow-[0_4px_16px_rgba(124,58,237,0.1)]',
};

const CollectionStats: React.FC<CollectionStatsProps> = ({
  activeKey,
  onSelectStat,
}) => {
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
    valueColor?: string;
  }> = [
    {
      key: 'total',
      label: t('Collection.stats.totalTasks'),
      value: o.total,
      iconBg: '#EFF6FF',
      iconColor: '#2563EB',
      icon: <ProfileIcon />,
    },
    {
      key: 'normal',
      label: t('Collection.stats.normalTasks'),
      value: o.normal,
      iconBg: '#ECFDF5',
      iconColor: '#059669',
      icon: <CheckCircleIcon />,
      valueColor: o.normal > 0 ? 'text-emerald-600' : undefined,
    },
    {
      key: 'error',
      label: t('Collection.stats.errorTasks'),
      value: o.error,
      iconBg: '#FEF2F2',
      iconColor: '#DC2626',
      icon: <ExclamationCircleIcon />,
      valueColor: o.error > 0 ? 'text-rose-600' : undefined,
    },
    {
      key: 'partial',
      label: t('Collection.stats.partialTasks'),
      value: o.partial,
      iconBg: '#FFFBEB',
      iconColor: '#D97706',
      icon: <WarningIcon />,
      valueColor: o.partial > 0 ? 'text-amber-600' : undefined,
    },
    {
      key: 'coveredModels',
      label: t('Collection.stats.coveredModels'),
      value: o.covered_models,
      iconBg: '#F0FDFA',
      iconColor: '#0D9488',
      icon: <AppstoreIcon />,
    },
    {
      key: 'recent',
      label: t('Collection.stats.recentSync'),
      value: formatRelative(o.recent_sync_at, t),
      iconBg: '#F5F3FF',
      iconColor: '#7C3AED',
      icon: <ClockCircleIcon />,
    },
  ];

  const getTooltipText = (cKey: string, cLabel: string) => {
    if (cKey === 'total' || cKey === 'coveredModels' || cKey === 'recent') {
      return t('Collection.stats.clickToViewAll');
    }
    return t('Collection.stats.clickToFilter', '', { name: cLabel });
  };

  const toggleLabel = expanded
    ? t('Collection.stats.collapse')
    : t('Collection.stats.expand');

  return (
    <div className="shrink-0 px-1">
      {expanded && (
        <div className="relative pb-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {cards.map((c) => {
              const isActive = activeKey === c.key;
              const tooltipText = onSelectStat ? getTooltipText(c.key, c.label) : '';
              const cardElement = (
                <div
                  key={c.key}
                  role={onSelectStat ? 'button' : undefined}
                  tabIndex={onSelectStat ? 0 : undefined}
                  onClick={() => onSelectStat?.(c.key)}
                  onKeyDown={(event) => {
                    if (onSelectStat && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault();
                      onSelectStat(c.key);
                    }
                  }}
                  className={`group flex items-center gap-3 rounded-xl border p-3.5 transition-all duration-200 ${
                    onSelectStat ? 'cursor-pointer hover:-translate-y-0.5 active:scale-[0.99]' : ''
                  } ${
                    isActive
                      ? (ACTIVE_CARD_STYLES[c.key] || 'border-blue-500 ring-2 ring-blue-100 bg-blue-50/25 shadow-sm')
                      : 'border-slate-200/80 bg-white hover:border-slate-300 hover:shadow-md'
                  }`}
                >
                  <div
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[18px] transition-transform duration-200 group-hover:scale-105"
                    style={{ background: c.iconBg, color: c.iconColor }}
                  >
                    {c.icon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-slate-500">
                      {c.label}
                    </div>
                    <div
                      className={`mt-0.5 truncate text-xl font-bold tracking-tight tabular-nums ${
                        c.valueColor || 'text-slate-900'
                      }`}
                    >
                      {c.value}
                    </div>
                  </div>
                </div>
              );

              return tooltipText ? (
                <Tooltip key={c.key} title={tooltipText} placement="bottom">
                  {cardElement}
                </Tooltip>
              ) : (
                cardElement
              );
            })}
          </div>
          <Tooltip title={toggleLabel}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-label={toggleLabel}
              onClick={toggleExpanded}
              className="absolute bottom-[-4px] left-1/2 flex h-4 w-7 -translate-x-1/2 cursor-pointer items-center justify-center rounded-full bg-white/90 text-slate-400 shadow-xs border border-slate-200 transition-colors hover:border-blue-300 hover:text-blue-500 focus:outline-none"
            >
              <DoubleRightIcon aria-hidden="true" className="-rotate-90 text-[10px]" />
            </button>
          </Tooltip>
        </div>
      )}
      {!expanded && (
        <div className="flex items-center pb-1 pt-0.5">
          <div className="h-px flex-1 bg-slate-200/60" />
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={toggleLabel}
            onClick={toggleExpanded}
            className="mx-3 flex h-6 cursor-pointer items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-2.5 text-[11px] font-normal text-slate-400 shadow-xs transition-colors hover:border-blue-200 hover:bg-blue-50/70 hover:text-blue-500 focus:outline-none"
          >
            <AppstoreIcon aria-hidden="true" className="text-xs" />
            <span>{toggleLabel}</span>
            <DownIcon aria-hidden="true" className="text-[9px]" />
          </button>
          <div className="h-px flex-1 bg-slate-200/60" />
        </div>
      )}
    </div>
  );
};

export default CollectionStats;
