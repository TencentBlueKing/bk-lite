'use client';

import React, { useCallback } from 'react';
import { LinkOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';

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
  const { link, surface, open } = useOpenInteractionLink(config);
  const active = link?.kind === 'data' && surface !== 'share';
  const openPoint = useCallback((point?: ChartLinkPoint) => {
    if (!active || !point) return;
    open(point);
  }, [active, open]);
  const onChartClick = useCallback((params: ChartClickParams) => {
    openPoint(readChartClickPoint(params));
  }, [openPoint]);
  return { active, link, openPoint, onChartClick, surface };
};

interface InteractionTitleIconProps {
  config?: ValueConfig | null;
  floating?: boolean;
  variant?: 'default' | 'screen';
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
  const layoutClass = variant === 'screen'
    ? 'screen-widget-frame__title-link'
    : `inline-flex shrink-0 items-center justify-center text-(--color-text-2) hover:text-(--color-text-1) ${
      floating
        ? 'absolute right-2 top-2 z-20 h-6 w-6 rounded-full bg-(--color-bg-1)/80 shadow-sm'
        : 'h-5 w-5'
    }`;

  return (
    <button
      type="button"
      data-export-hidden="true"
      aria-label={label}
      title={label}
      className={`no-drag ${layoutClass}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        open();
      }}
    >
      <LinkOutlined aria-hidden />
    </button>
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
  if (!shouldRenderInteractionActionButton(link, surface, isFirst)) {
    return <>-</>;
  }
  return (
    <Button type="link" size="small" className="p-0" onClick={onOpen}>
      {label}
    </Button>
  );
};

export default InteractionTitleIcon;
