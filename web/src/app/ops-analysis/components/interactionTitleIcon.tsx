'use client';

import React, { useCallback } from 'react';
import { LinkOutlined } from '@ant-design/icons';
import { Button, Tooltip, message } from 'antd';

import { useFilterTemplateSnapshot } from '@/app/ops-analysis/context/filterTemplate';
import { useInteractionSurface } from '@/app/ops-analysis/context/interactionSurface';
import { useTranslation } from '@/utils/i18n';
import type { ValueConfig, WidgetInteractionLink } from '@/app/ops-analysis/types/dashBoard';
import type { ChartLinkPoint, InteractionSurface } from '@/app/ops-analysis/utils/interactionLink';
import { openPreparedInteractionNavigation } from '@/app/ops-analysis/utils/interactionBehavior';
import {
  prepareInteractionNavigation,
  readChartClickPoint,
  readWidgetInteraction,
  resolveInteractionUrl,
  shouldNavigateInteraction,
  shouldRenderInteractionActionButton,
  shouldShowInteractionEntry,
  type ChartClickParams,
} from '@/app/ops-analysis/utils/interactionLink';
import { shouldShowDataLinkHint } from '@/app/ops-analysis/utils/interactionLinkHint';

export const useOpenInteractionLink = (config?: object | null) => {
  const { t } = useTranslation();
  const surface = useInteractionSurface();
  const filters = useFilterTemplateSnapshot();
  const link = readWidgetInteraction(config as ValueConfig | null | undefined);

  const open = useCallback((point?: ChartLinkPoint) => {
    if (!link || !shouldNavigateInteraction(surface)) return;
    const resolved = resolveInteractionUrl(link.url, {
      definitions: filters.definitions,
      values: filters.values,
      point,
      now: new Date(),
    });
    const prepared = prepareInteractionNavigation(
      resolved,
      link.openMode,
      typeof window === 'undefined' ? '' : window.location.search,
    );
    if (!prepared.ok) {
      if (prepared.reason === 'blocked') {
        message.warning(t('dashboard.interactionUrlBlocked', '链接协议不被允许'));
      }
      return;
    }
    if (typeof window === 'undefined') return;
    openPreparedInteractionNavigation(prepared, window);
  }, [filters.definitions, filters.values, link, surface, t]);

  return { link, surface, open };
};

export const useWidgetDataLink = (config?: object | null) => {
  const { t } = useTranslation();
  const { link, surface, open } = useOpenInteractionLink(config);
  const active = link?.kind === 'data' && surface !== 'share';
  const showDataLinkHint = shouldShowDataLinkHint(surface, link);
  const hintName = link?.name?.trim() || t('dashboard.interactionOpen', '打开链接');
  const chartTooltipHint = showDataLinkHint
    ? t('dashboard.interactionChartTooltipHint', '{name} ↗ 点击打开', { name: hintName })
    : '';
  const hoverHint = showDataLinkHint
    ? t('dashboard.interactionHoverHint', '点击打开：{name}', { name: hintName })
    : undefined;
  const contextHint = showDataLinkHint
    ? t('dashboard.interactionContextHint', '右键打开链接')
    : '';
  const openPoint = useCallback((point?: ChartLinkPoint) => {
    if (!active || !point) return;
    open(point);
  }, [active, open]);
  const onChartClick = useCallback((params: ChartClickParams) => {
    openPoint(readChartClickPoint(params));
  }, [openPoint]);
  return {
    active,
    link,
    openPoint,
    onChartClick,
    surface,
    showDataLinkHint,
    chartTooltipHint,
    hoverHint,
    contextHint,
  };
};

interface InteractionTitleIconProps {
  config?: ValueConfig | null;
  floating?: boolean;
  variant?: 'default' | 'screen' | 'text';
}

const InteractionTitleIcon: React.FC<InteractionTitleIconProps> = ({
  config,
  floating = false,
  variant = 'default',
}) => {
  const { t } = useTranslation();
  const { link, surface, open } = useOpenInteractionLink(config);
  const titleLink = link?.kind === 'title' ? link : undefined;
  if (!shouldShowInteractionEntry(surface, Boolean(titleLink))) return null;
  const label = titleLink?.name || t('dashboard.interactionOpen', '打开链接');
  const hint = shouldNavigateInteraction(surface)
    ? label
    : t('dashboard.interactionViewModeOnly', '查看模式下可跳转');
  const layoutClass = variant === 'screen' || variant === 'text'
    ? `screen-widget-frame__title-link${variant === 'text' ? ' screen-text-item__title-link' : ''}`
    : `inline-flex shrink-0 cursor-pointer items-center justify-center text-(--color-text-3) transition-colors hover:text-(--color-primary) ${
      floating
        ? 'absolute right-2 top-2 z-20 h-6 w-6 rounded-full bg-(--color-bg-1)/80 shadow-sm'
        : 'h-5 w-5 rounded hover:bg-(--color-fill-2)'
    }`;

  return (
    <Tooltip title={hint} mouseEnterDelay={0}>
      <button
        type="button"
        data-export-hidden="true"
        aria-label={label}
        className={`no-drag ${layoutClass}`}
        onClick={(event) => {
          event.preventDefault();
          if (shouldNavigateInteraction(surface)) {
            event.stopPropagation();
            open();
            return;
          }
          if (variant !== 'text') event.stopPropagation();
        }}
      >
        <LinkOutlined aria-hidden />
      </button>
    </Tooltip>
  );
};

export const InteractionActionCell = ({
  link,
  surface,
  isFirst,
  label,
  onOpen,
}: {
  link: WidgetInteractionLink | undefined;
  surface: InteractionSurface;
  isFirst: boolean;
  label: string;
  onOpen: () => void;
}) => {
  const { t } = useTranslation();
  if (!shouldRenderInteractionActionButton(link, surface, isFirst)) {
    return <>-</>;
  }
  const hint = shouldNavigateInteraction(surface)
    ? undefined
    : t('dashboard.interactionViewModeOnly', '查看模式下可跳转');
  return (
    <Tooltip title={hint}>
      <Button type="link" size="small" className="p-0" onClick={onOpen}>
        {label}
      </Button>
    </Tooltip>
  );
};

export default InteractionTitleIcon;
