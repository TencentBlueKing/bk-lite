'use client';

import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import { Popover, Typography } from 'antd';
import ServiceLanguage from '@/app/apm/components/service-language';
import { useTranslation } from '@/utils/i18n';

export interface ServiceTagItem {
  name: string;
  silent: boolean;
  language?: string;
}

const TAG_GAP = 6;

const chipClassName = (silent: boolean) => (
  `inline-flex max-w-full shrink-0 items-center gap-1 rounded border px-2 py-0.5 text-xs whitespace-nowrap ${
    silent
      ? 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)]'
      : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-1)]'
  }`
);

const overflowChipClassName = (
  'inline-flex min-h-10 shrink-0 cursor-pointer items-center rounded border border-[color-mix(in_srgb,var(--color-primary)_28%,var(--color-border))] '
  + 'bg-[var(--color-primary-bg-active)] px-2 py-0.5 text-xs font-medium tabular-nums text-[var(--color-primary)] '
  + 'transition-colors duration-150 hover:border-[var(--color-primary)] focus-visible:outline-2 '
  + 'focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]'
);

/** 按真实宽度计算一行能放下几个 tag；放不下时预留 +N 徽章宽度。 */
export function computeVisibleServiceTagCount(
  tagWidths: number[],
  containerWidth: number,
  overflowBadgeWidth: number,
  gap = TAG_GAP,
): number {
  if (tagWidths.length === 0 || containerWidth <= 0) return 0;

  let allUsed = 0;
  for (let i = 0; i < tagWidths.length; i += 1) {
    allUsed += tagWidths[i] + (i > 0 ? gap : 0);
  }
  if (allUsed <= containerWidth) return tagWidths.length;

  const reserve = Math.max(overflowBadgeWidth, 0) + (tagWidths.length > 0 ? gap : 0);
  let used = 0;
  let count = 0;
  for (let i = 0; i < tagWidths.length; i += 1) {
    const next = used + (count > 0 ? gap : 0) + tagWidths[i];
    if (next + reserve > containerWidth) break;
    used = next;
    count += 1;
  }
  return count;
}

function ServiceChip({ name, silent, language }: ServiceTagItem) {
  const { t } = useTranslation();
  return (
    <span className={chipClassName(silent)} title={silent ? t('apm.tags.silentName', '{name}（静默）', { name }) : name}>
      <ServiceLanguage language={language} size={12} />
      {name}
    </span>
  );
}

function OverflowList({ services }: { services: ServiceTagItem[] }) {
  const { t } = useTranslation();
  return (
    <div className="flex max-h-56 w-56 flex-col gap-1 overflow-auto py-0.5" role="list">
      {services.map((service) => (
        <div
          key={service.name}
          role="listitem"
          className={`flex items-center justify-between gap-2 rounded px-1.5 py-1 text-xs ${
            service.silent ? 'text-[var(--color-text-3)]' : 'text-[var(--color-text-1)]'
          }`}
        >
          <span className="flex min-w-0 items-center gap-1">
            <ServiceLanguage language={service.language} size={12} />
            <Typography.Text ellipsis className="!mb-0 !text-xs !text-inherit" title={service.name}>
              {service.name}
            </Typography.Text>
          </span>
          {service.silent ? (
            <span className="shrink-0 text-[10px] text-[var(--color-text-4)]">{t('apm.tags.silent', '静默')}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default function ServiceTagOverflow({
  services,
  emptyLabel,
}: {
  services: ServiceTagItem[];
  emptyLabel?: string;
}) {
  const { t } = useTranslation();
  const resolvedEmpty = emptyLabel ?? t('apm.tags.empty', '尚无服务上报');
  const containerRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const badgeMeasureRef = useRef<HTMLSpanElement>(null);
  const [visibleCount, setVisibleCount] = useState(services.length);
  const [open, setOpen] = useState(false);

  const serviceKey = useMemo(
    () => services.map((service) => `${service.name}:${service.language ?? ''}:${service.silent ? 1 : 0}`).join('|'),
    [services],
  );

  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure) return undefined;

    const recalc = () => {
      const tagEls = Array.from(measure.children) as HTMLElement[];
      const widths = tagEls.map((el) => el.getBoundingClientRect().width);
      const badgeWidth = badgeMeasureRef.current?.getBoundingClientRect().width ?? 38;
      const next = computeVisibleServiceTagCount(widths, container.clientWidth, badgeWidth);
      setVisibleCount((prev) => (prev === next ? prev : next));
    };

    recalc();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(recalc);
    observer.observe(container);
    return () => observer.disconnect();
  }, [serviceKey]);

  if (!services.length) {
    return <Typography.Text type="secondary" className="!text-xs">{resolvedEmpty}</Typography.Text>;
  }

  const safeVisible = Math.min(visibleCount, services.length);
  const visibleServices = services.slice(0, safeVisible);
  const hiddenServices = services.slice(safeVisible);
  const overflowCount = hiddenServices.length;

  const stopCardNavigation = (event: MouseEvent | KeyboardEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  let overflowTrigger: ReactNode = null;
  if (overflowCount > 0) {
    overflowTrigger = (
      <Popover
        trigger={['hover', 'focus', 'click']}
        placement="topLeft"
        open={open}
        onOpenChange={setOpen}
        mouseEnterDelay={0.15}
        content={(
          <div onClick={stopCardNavigation} onMouseDown={stopCardNavigation}>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <Typography.Text strong className="!text-xs">{t('apm.tags.list', '服务列表')}</Typography.Text>
              <Typography.Text type="secondary" className="!text-xs tabular-nums">
                {t('apm.common.serviceCount', '共 {count} 个', { count: services.length })}
              </Typography.Text>
            </div>
            <OverflowList services={services} />
          </div>
        )}
      >
        <button
          type="button"
          aria-label={t('apm.tags.overflowAria', '还有 {overflow} 个服务未展示，查看全部 {total} 个服务', { overflow: overflowCount, total: services.length })}
          className={overflowChipClassName}
          onClick={stopCardNavigation}
          onMouseDown={stopCardNavigation}
        >
          +{overflowCount}
        </button>
      </Popover>
    );
  }

  return (
    <div ref={containerRef} className="relative min-w-0">
      <div className="flex flex-nowrap items-center gap-1.5 overflow-hidden">
        {visibleServices.map((service) => (
          <ServiceChip key={service.name} {...service} />
        ))}
        {overflowTrigger}
      </div>

      {/* 测量层：不可见，用于按真实宽度计算可见数量 */}
      <div
        ref={measureRef}
        aria-hidden="true"
        className="pointer-events-none absolute top-0 left-0 flex h-0 gap-1.5 overflow-visible opacity-0"
      >
        {services.map((service) => (
          <ServiceChip key={`measure-${service.name}`} {...service} />
        ))}
      </div>
      <span
        ref={badgeMeasureRef}
        data-service-tag-overflow-badge-measure="true"
        aria-hidden="true"
        className={`${overflowChipClassName} pointer-events-none absolute top-0 left-0 opacity-0`}
      >
        +{services.length}
      </span>
    </div>
  );
}
