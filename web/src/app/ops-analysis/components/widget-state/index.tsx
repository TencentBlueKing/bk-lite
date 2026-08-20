'use client';

import React from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  toCanvasPixels,
  useWidgetViewport,
} from '@/app/ops-analysis/components/widget-viewport';

export interface WidgetStateProps {
  kind?: 'empty' | 'error';
  description?: React.ReactNode;
  className?: string;
}

const WidgetState: React.FC<WidgetStateProps> = ({
  kind = 'empty',
  description,
  className = '',
}) => {
  const { t } = useTranslation();
  const { scale } = useWidgetViewport();
  const errorFontSize = toCanvasPixels(14, scale);

  if (kind === 'error') {
    return (
      <div
        className={`flex h-full flex-col items-center justify-center px-4 text-center ${className}`.trim()}
        style={{ color: 'var(--screen-empty-color, var(--color-text-3))' }}
      >
        <ExclamationCircleOutlined
          style={{
            color: 'var(--ant-color-warning)',
            fontSize: toCanvasPixels(24, scale),
            marginBottom: toCanvasPixels(12, scale),
          }}
        />
        <span style={{ fontSize: errorFontSize, lineHeight: 1.5 }}>{description}</span>
      </div>
    );
  }

  return (
    <div
      className={`flex h-full items-center justify-center px-3 text-center ${className}`.trim()}
      style={{
        color: 'var(--screen-empty-color, var(--color-text-3))',
      }}
    >
      <span
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
};

export default WidgetState;
