'use client';

import React from 'react';
import { Empty } from 'antd';
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
  const fontSize = toCanvasPixels(14, scale);

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
        <span style={{ fontSize, lineHeight: 1.5 }}>{description}</span>
      </div>
    );
  }

  return (
    <div className={`flex h-full items-center justify-center ${className}`.trim()}>
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        styles={{
          image: {
            height: toCanvasPixels(40, scale),
            marginBottom: toCanvasPixels(8, scale),
          },
          description: {
            color: 'var(--screen-empty-color, var(--color-text-3))',
            fontSize,
            lineHeight: 1.5,
          },
        }}
        description={description ?? t('common.noData')}
      />
    </div>
  );
};

export default WidgetState;
