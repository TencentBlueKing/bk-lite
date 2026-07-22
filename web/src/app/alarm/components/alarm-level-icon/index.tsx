'use client';

import React from 'react';
import Icon from '@/components/icon';

export interface AlarmLevelIconProps {
  icon?: string;
  className?: string;
  style?: React.CSSProperties;
}

export default function AlarmLevelIcon({
  icon = '',
  className,
  style,
}: AlarmLevelIconProps) {
  if (!icon) {
    return (
      <span className={className} style={style}>
        -
      </span>
    );
  }

  if (icon.startsWith('data:image/')) {
    return <img src={icon} alt="level icon" className={className} style={style} />;
  }

  return <Icon type={icon} className={className} style={style} />;
}
