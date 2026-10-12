'use client';

import React, { useState, useCallback, useEffect } from 'react';
import dayjs from 'dayjs';
import {
  AppstoreOutlined,
  DownOutlined,
  DoubleRightOutlined,
} from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCollectApi } from '@/app/cmdb/api';

const AppstoreIcon = AppstoreOutlined as any;
const DownIcon = DownOutlined as any;
const DoubleRightIcon = DoubleRightOutlined as any;

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
    hue: string;
    valueClassName: string;
  }> = [
    {
      key: 'total',
      label: t('Collection.stats.totalTasks'),
      value: o.total,
      hue: 'var(--color-primary)',
      valueClassName: 'text-[var(--color-text-1)]',
    },
    {
      key: 'normal',
      label: t('Collection.stats.normalTasks'),
      value: o.normal,
      hue: 'var(--color-success)',
      valueClassName: 'text-[var(--color-success)]',
    },
    {
      key: 'error',
      label: t('Collection.stats.errorTasks'),
      value: o.error,
      hue: 'var(--color-fail)',
      valueClassName: 'text-[var(--color-fail)]',
    },
    {
      key: 'partial',
      label: t('Collection.stats.partialTasks'),
      value: o.partial,
      hue: 'var(--color-warning)',
      valueClassName: 'text-[var(--color-warning)]',
    },
    {
      key: 'coveredModels',
      label: t('Collection.stats.coveredModels'),
      value: o.covered_models,
      hue: 'var(--color-success)',
      valueClassName: 'text-[var(--color-success)]',
    },
    {
      key: 'recent',
      label: t('Collection.stats.recentSync'),
      value: formatRelative(o.recent_sync_at, t),
      hue: 'var(--color-primary)',
      valueClassName: 'text-[var(--color-text-1)]',
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
            {cards.map((c) => {
              const isLong = typeof c.value === 'string' && c.value.length > 8;
              return (
                <div
                  key={c.key}
                  className="min-w-0 cursor-default rounded-lg border border-[var(--color-border-1)] p-3 shadow-[0_1px_3px_rgba(0,0,0,0.03)] sm:px-3.5 sm:py-3"
                  style={{
                    background: `linear-gradient(180deg, color-mix(in srgb, ${c.hue} 1.5%, var(--color-bg)) 0%, var(--color-bg) 32%)`,
                  }}
                >
                  <div className="flex h-full flex-col justify-between gap-1.5">
                    <span className="truncate text-xs font-medium text-[var(--color-text-3)]">
                      {c.label}
                    </span>
                    <div
                      className={`font-mono tracking-tight tabular-nums ${
                        isLong
                          ? `whitespace-normal break-words text-sm font-medium leading-snug sm:text-base ${c.valueClassName}`
                          : `truncate text-xl font-bold sm:text-2xl ${c.valueClassName}`
                      }`}
                    >
                      {c.value}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <Tooltip title={toggleLabel}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-label={toggleLabel}
              onClick={toggleExpanded}
              className="absolute bottom-[-6px] left-1/2 flex h-5 w-8 -translate-x-1/2 cursor-pointer items-center justify-center rounded-md bg-[var(--color-bg)] text-[var(--color-primary)] transition-colors hover:bg-[var(--color-primary-bg-active)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            >
              <DoubleRightIcon aria-hidden="true" className="-rotate-90 text-xs" />
            </button>
          </Tooltip>
        </div>
      )}
      {!expanded && (
        <div className="flex items-center pb-0 pt-1">
          <div className="h-px flex-1 bg-[var(--color-border)]" />
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={toggleLabel}
            onClick={toggleExpanded}
            className="mx-3 flex h-6 cursor-pointer items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 text-xs font-normal text-[var(--color-text-3)] transition-colors hover:border-[var(--color-primary)] hover:bg-[var(--color-primary-bg-active)] hover:text-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            <AppstoreIcon aria-hidden="true" className="text-xs" />
            <span>{toggleLabel}</span>
            <DownIcon aria-hidden="true" className="text-xs" />
          </button>
          <div className="h-px flex-1 bg-[var(--color-border)]" />
        </div>
      )}
    </div>
  );
};

export default CollectionStats;
