'use client';

import { useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import { DASHBOARD_TEXT_IDS } from './dashboard-text-map.generated';
import { getDashboardReturnContext, type SearchParamsLike } from './return-navigation';

type TranslateValues = Record<string, string | number>;
type Translate = (id: string, defaultMessage?: string, values?: TranslateValues) => string;

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

export const localizeDashboardReturnLabel = (t: Translate, params: SearchParamsLike): string => {
  const { objectName, source } = getDashboardReturnContext(params);
  if (source === 'integration') {
    return objectName
      ? t(
        'monitor.dashboards.common.backToObjectIntegrationAssets',
        '返回{objectName}集成资产列表',
        { objectName }
      )
      : tDashboardText(t, '返回集成资产列表');
  }
  return objectName
    ? t(
      'monitor.dashboards.common.backToObjectViewList',
      '返回{objectName}视图列表',
      { objectName }
    )
    : tDashboardText(t, '返回监控视图');
};

export const useDashboardText = () => {
  const { t } = useTranslation();
  const dt = useCallback((text: string) => tDashboardText(t, text), [t]);
  const common = useCallback(
    (key: string, fallback: string, values?: TranslateValues) =>
      t(`monitor.dashboards.common.${key}`, fallback, values),
    [t]
  );
  return { t, dt, common };
};
