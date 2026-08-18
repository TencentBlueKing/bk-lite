import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Tag, Tooltip } from 'antd';

import {
  CAPABILITY_TAG_GAP,
  computeVisibleCapabilityTagCount,
} from '@/app/system-manager/utils/integrationCenter';

export interface CapabilityOverflowTag {
  key: string;
  label: string;
  appearance?: 'capability' | 'ready' | 'inactive';
}

interface ProviderCapabilityTagsProps {
  tags: CapabilityOverflowTag[];
  align?: 'start' | 'end';
}

const tagClassName = 'mr-0 mb-0 !flex min-w-0 items-center overflow-hidden font-mini';

function CapabilityTagChip({
  tag,
  className,
  style,
}: {
  tag: CapabilityOverflowTag;
  className?: string;
  style?: React.CSSProperties;
}) {
  const appearance = tag.appearance || 'capability';
  if (appearance === 'capability') {
    return (
      <Tag color="processing" className={className} style={style}>
        <span className="min-w-0 truncate">{tag.label}</span>
      </Tag>
    );
  }

  const ready = appearance === 'ready';
  return (
    <Tag
      bordered
      color={ready ? 'green' : 'default'}
      className={`${className} rounded-md ${
        ready
          ? 'border-[#b7eb8f] bg-[#f6ffed] text-[#389e0d]'
          : 'border-[#d9d9d9] bg-[#fafafa] text-[#8c8c8c]'
      }`}
      style={style}
    >
      <span className="flex min-w-0 items-center gap-1">
        <span className={`h-2 w-2 shrink-0 rounded-full ${ready ? 'bg-[#389e0d]' : 'bg-[#bfbfbf]'}`} />
        <span className="min-w-0 truncate">{tag.label}</span>
      </span>
    </Tag>
  );
}

const ProviderCapabilityTags: React.FC<ProviderCapabilityTagsProps> = ({ tags, align = 'start' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const badgeMeasureRef = useRef<HTMLSpanElement>(null);
  const [visibleCount, setVisibleCount] = useState(tags.length);
  const [containerWidth, setContainerWidth] = useState(0);
  const [badgeWidth, setBadgeWidth] = useState(0);

  const tagKey = useMemo(
    () => tags.map((tag) => `${tag.key}:${tag.label}:${tag.appearance || ''}`).join('|'),
    [tags],
  );

  useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure) {
      return undefined;
    }

    const recalc = () => {
      const tagEls = Array.from(measure.children) as HTMLElement[];
      const widths = tagEls.map((el) => el.getBoundingClientRect().width);
      const nextBadgeWidth = badgeMeasureRef.current?.getBoundingClientRect().width ?? 28;
      const nextVisible = computeVisibleCapabilityTagCount(
        widths,
        container.clientWidth,
        nextBadgeWidth,
      );
      setBadgeWidth((prev) => (prev === nextBadgeWidth ? prev : nextBadgeWidth));
      setContainerWidth((prev) => (prev === container.clientWidth ? prev : container.clientWidth));
      setVisibleCount((prev) => (prev === nextVisible ? prev : nextVisible));
    };

    recalc();
    if (typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver(recalc);
    observer.observe(container);
    return () => observer.disconnect();
  }, [tagKey]);

  if (!tags.length) {
    return null;
  }

  const safeVisible = Math.min(Math.max(visibleCount, 0), tags.length);
  const visibleTags = tags.slice(0, safeVisible);
  const hiddenTags = tags.slice(safeVisible);
  const hiddenCount = hiddenTags.length;
  const shouldTruncateFirstTag = visibleTags.length === 1 && containerWidth > 0;
  const firstTagMaxWidth = hiddenCount > 0
    ? Math.max(containerWidth - CAPABILITY_TAG_GAP - badgeWidth, 0)
    : containerWidth;

  return (
    <div ref={containerRef} className="relative min-w-0 w-full flex-1">
      <div
        className={`flex min-w-0 flex-nowrap items-center gap-1 overflow-hidden ${
          align === 'end' ? 'justify-end' : ''
        }`}
      >
        {visibleTags.map((tag, index) => {
          const shouldTruncate = shouldTruncateFirstTag && index === 0;
          return (
            <Tooltip key={tag.key} title={tag.label}>
              <CapabilityTagChip
                tag={tag}
                className={`${tagClassName} ${shouldTruncate ? '' : 'shrink-0'}`}
                style={shouldTruncate ? { maxWidth: firstTagMaxWidth } : undefined}
              />
            </Tooltip>
          );
        })}
        {hiddenCount > 0 ? (
          <Tooltip
            color="var(--color-bg)"
            title={(
              <div className="flex max-w-[240px] flex-wrap gap-1">
                {hiddenTags.map((tag) => (
                  <CapabilityTagChip
                    key={tag.key}
                    tag={tag}
                    className={`${tagClassName} shrink-0`}
                  />
                ))}
              </div>
            )}
          >
            <Tag
              className="mr-0 mb-0 shrink-0 font-mini"
              onClick={(event) => event.stopPropagation()}
              onMouseDown={(event) => event.stopPropagation()}
            >
              +{hiddenCount}
            </Tag>
          </Tooltip>
        ) : null}
      </div>

      <div
        ref={measureRef}
        aria-hidden="true"
        className="pointer-events-none absolute top-0 left-0 flex h-0 gap-1 overflow-visible opacity-0"
      >
        {tags.map((tag) => (
          <CapabilityTagChip
            key={`measure-${tag.key}`}
            tag={tag}
            className={`${tagClassName} shrink-0`}
          />
        ))}
      </div>
      <span
        ref={badgeMeasureRef}
        aria-hidden="true"
        className="pointer-events-none absolute top-0 left-0 opacity-0"
      >
        <Tag className="mr-0 mb-0 shrink-0 font-mini">+{tags.length}</Tag>
      </span>
    </div>
  );
};

export default ProviderCapabilityTags;
