'use client';

import React, { useState, useCallback, useEffect } from 'react';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCollectApi } from '@/app/cmdb/api';

interface TaskOverview {
  total: number;
  normal: number;
  error: number;
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
    recent_sync_at: null,
    covered_models: 0,
  };

  const cards: Array<{
    key: string;
    label: string;
    value: number | string;
    iconBg: string;
    icon: React.ReactNode;
  }> = [
    {
      key: 'total',
      label: t('Collection.stats.totalTasks'),
      value: o.total,
      iconBg: '#E8F0FF',
      icon: (
        <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
          <rect x="4" y="5" width="20" height="4" rx="1.5" fill="#155AEF" />
          <rect x="4" y="12" width="20" height="4" rx="1.5" fill="#155AEF" opacity="0.6" />
          <rect x="4" y="19" width="20" height="4" rx="1.5" fill="#155AEF" opacity="0.3" />
        </svg>
      ),
    },
    {
      key: 'normal',
      label: t('Collection.stats.normalTasks'),
      value: o.normal,
      iconBg: '#E8FFEA',
      icon: (
        <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="10" fill="#E8FFEA" />
          <path d="M10 14.5L12.5 17L18 11" stroke="#00B42A" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
      ),
    },
    {
      key: 'error',
      label: t('Collection.stats.errorTasks'),
      value: o.error,
      iconBg: '#FFECE8',
      icon: (
        <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="10" fill="#FFECE8" />
          <path d="M14 9.5V15" stroke="#F53F3F" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="14" cy="18.5" r="1.2" fill="#F53F3F" />
        </svg>
      ),
    },
    {
      key: 'coveredModels',
      label: t('Collection.stats.coveredModels'),
      value: o.covered_models,
      iconBg: '#E8FFEA',
      icon: (
        <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
          <rect x="4" y="4" width="9" height="9" rx="2" fill="#00B42A" opacity="0.85" />
          <rect x="15" y="4" width="9" height="9" rx="2" fill="#00B42A" opacity="0.55" />
          <rect x="4" y="15" width="9" height="9" rx="2" fill="#00B42A" opacity="0.55" />
          <rect x="15" y="15" width="9" height="9" rx="2" fill="#00B42A" opacity="0.85" />
        </svg>
      ),
    },
    {
      key: 'recent',
      label: t('Collection.stats.recentSync'),
      value: formatRelative(o.recent_sync_at, t),
      iconBg: '#E8F0FF',
      icon: (
        <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="10" fill="#E8F0FF" />
          <circle cx="14" cy="14" r="6" stroke="#155AEF" strokeWidth="2" fill="none" />
          <path d="M14 11V14.5L16.5 16" stroke="#155AEF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
      ),
    },
  ];

  const isTimeCard = (key: string) => key === 'recent';

  return (
    <div className="px-2 pt-3 shrink-0">
      {expanded && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {cards.map((c) => (
            <div
              key={c.key}
              className="flex items-center gap-3.5 rounded-xl border border-slate-200 bg-white px-5 py-4 transition-shadow hover:shadow-[0_2px_12px_rgba(0,0,0,0.06)]"
            >
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]"
                style={{ background: c.iconBg }}
              >
                {c.icon}
              </div>
              <div className="min-w-0">
                <div className="text-xs text-slate-500">{c.label}</div>
                <div
                  className={`font-bold leading-tight tracking-tight tabular-nums text-slate-900 ${isTimeCard(c.key) ? 'text-[20px]' : 'text-[26px]'}`}
                >
                  {c.value}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div
        onClick={toggleExpanded}
        className="flex cursor-pointer items-center justify-center gap-1 rounded text-xs text-slate-400 transition-colors hover:text-blue-500"
        style={{ padding: '5px 0', marginTop: expanded ? 8 : 0 }}
      >
        {expanded ? t('Collection.stats.collapse') : t('Collection.stats.expand')}
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          style={{
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform .2s',
          }}
        >
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
      </div>
    </div>
  );
};

export default CollectionStats;
