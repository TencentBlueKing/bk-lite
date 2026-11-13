'use client';

import React, { useLayoutEffect, useRef, useState } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  toCanvasPixels,
  useWidgetViewport,
} from '@/app/ops-analysis/components/widget-viewport';
import { fitWidgetStateContent } from './fitWidgetState';

export interface WidgetStateProps {
  kind?: 'empty' | 'error';
  description?: React.ReactNode;
  className?: string;
}

const textLengthOf = (description: React.ReactNode) => (
  typeof description === 'string' ? description.trim().length : 0
);

const WidgetState: React.FC<WidgetStateProps> = ({
  kind = 'empty',
  description,
  className = '',
}) => {
  const { t } = useTranslation();
  const { scale } = useWidgetViewport();
  const rootRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const node = rootRef.current;
    if (!node) return undefined;
    const measure = () => {
      const width = node.offsetWidth;
      const height = node.offsetHeight;
      setBox((current) => (
        current.width === width && current.height === height
          ? current
          : { width, height }
      ));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  if (kind !== 'error') {
    return (
      <div
        className={`flex h-full min-h-0 min-w-0 items-center justify-center overflow-hidden px-3 text-center ${className}`.trim()}
        style={{
          color: 'var(--screen-empty-color, var(--color-text-3))',
        }}
      >
        <span
          className="max-w-full"
          style={{
            fontSize: 'calc(13px * var(--screen-widget-ui-scale, 1))',
            lineHeight: 1.35,
            opacity: 0.86,
          }}
        >
          {description ?? t('common.noData')}
        </span>
      </div>
    );
  }

  const fit = box.width > 0 && box.height > 0
    ? fitWidgetStateContent({
      width: box.width,
      height: box.height,
      scale,
      textLength: textLengthOf(description),
    })
    : null;
  const title = fit?.showTitle && typeof description === 'string'
    ? description
    : undefined;

  return (
    <div
      ref={rootRef}
      title={title}
      className={`flex h-full min-h-0 w-full min-w-0 items-center justify-center overflow-hidden text-center ${className}`.trim()}
      style={{
        color: 'var(--screen-empty-color, var(--color-text-3))',
        padding: fit?.padding ?? 4,
      }}
    >
      <div className="flex max-h-full min-h-0 w-full min-w-0 flex-col items-center justify-center">
        {fit?.showIcon && (
          <ExclamationCircleOutlined
            style={{
              color: 'var(--ant-color-warning)',
              fontSize: fit.iconSize,
              marginBottom: fit.iconGap,
            }}
          />
        )}
        <span
          className="max-w-full min-w-0"
          style={{
            fontSize: fit?.fontSize ?? toCanvasPixels(13, scale),
            lineHeight: 1.25,
            display: '-webkit-box',
            WebkitBoxOrient: 'vertical',
            WebkitLineClamp: fit?.lineClamp ?? 2,
            overflow: 'hidden',
            overflowWrap: 'anywhere',
          }}
        >
          {description}
        </span>
      </div>
    </div>
  );
};

export default WidgetState;
