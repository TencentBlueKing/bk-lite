'use client';

import React from 'react';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/components/monitor-shared';
export const DEFAULT_OBJECT_ICON = OBJECT_DEFAULT_ICON;

export interface MonitorObjectIconProps {
  icon?: string;
  fallback?: string;
  size?: number;
  className?: string;
}

const MonitorObjectIcon: React.FC<MonitorObjectIconProps> = ({
  icon,
  fallback = DEFAULT_OBJECT_ICON,
  size = 16,
  className,
}) => {
  const src = `/assets/icons/${icon || fallback}.svg`;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={icon || fallback}
      width={size}
      height={size}
      className={className}
      style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }}
      onError={(e) => {
        const img = e.currentTarget;
        if (!img.src.endsWith(`/assets/icons/${fallback}.svg`)) {
          img.src = `/assets/icons/${fallback}.svg`;
        }
      }}
    />
  );
};

export default MonitorObjectIcon;
