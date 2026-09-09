'use client';

import { useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import { DASHBOARD_TEXT_IDS } from './dashboard-text-map.generated';

type Translate = (id: string, defaultMessage?: string) => string;

export const dashboardTextKey = (text: string): string | undefined => DASHBOARD_TEXT_IDS[text];

export const tDashboardText = (t: Translate, text: string | null | undefined): string => {
  const value = text ?? '';
  if (!value) return value;
  const id = DASHBOARD_TEXT_IDS[value];
  return id ? t(`monitor.dashboards.text.${id}`, value) : value;
};

export const tDashboardTemplate = (t: Translate, text: string, fallback: string): string => {
  return t(`monitor.dashboards.common.${text}`, fallback);
};

export const localizeGuideItems = <T extends { label: string; detail: string }>(t: Translate, items: T[] | undefined): T[] => {
  if (!items?.length) return items || [];
  return items.map((item) => ({
    ...item,
    label: tDashboardText(t, item.label),
    detail: tDashboardText(t, item.detail),
  }));
};

export const useDashboardText = () => {
  const { t } = useTranslation();
  const dt = useCallback((text: string) => tDashboardText(t, text), [t]);
  const common = useCallback((key: string, fallback: string) => t(`monitor.dashboards.common.${key}`, fallback), [t]);
  return { t, dt, common };
};
