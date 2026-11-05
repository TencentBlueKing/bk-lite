'use client';

import React from 'react';
import {
  ApartmentOutlined,
  BarChartOutlined,
  BranchesOutlined,
  DesktopOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

export const CanvasTypeIcon = ({ type, className = 'text-sm text-[var(--color-text-2)]' }: {
  type: CanvasType;
  className?: string;
}) => {
  switch (type) {
    case 'dashboard':
      return <BarChartOutlined className={className} />;
    case 'topology':
      return <Icon type="tuoputu" className={className} />;
    case 'architecture':
      return <ApartmentOutlined className={className} />;
    case 'screen':
      return <DesktopOutlined className={className} />;
    case 'report':
      return <FileTextOutlined className={className} />;
    case 'networkTopology':
      return <BranchesOutlined className={className} />;
    default:
      return null;
  }
};
