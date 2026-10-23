'use client';

import React from 'react';
import { Spin } from 'antd';

/** 与列表区空态同一句。专业盘加载文案只从这里取。 */
export const PRO_DASH_LOADING_LABEL = '加载中';

export type ProDashLoadingSize = 'default' | 'small';
export type ProDashLoadingLayout = 'stack' | 'inline';

/**
 * 专业盘唯一加载皮肤。点是 Ant Design Spin 的四颗蓝点（与列表 Table loading 同一套），
 * 文案在点下或点旁。主机和 MySQL 只引用本组件，不再各写静态「加载中」或骨架。
 */
export default function ProDashLoading({
  size = 'default',
  layout = 'stack'
}: {
  size?: ProDashLoadingSize;
  /** stack：点在上、文案在下（卡、趋势区）。inline：点与文案横排（窄条、事件轨）。 */
  layout?: ProDashLoadingLayout;
}) {
  const textClass = size === 'small'
    ? 'text-[12px] leading-4 text-[var(--color-text-3)]'
    : 'text-[13px] leading-4 text-[var(--color-text-3)]';
  return (
    <span
      className={
        layout === 'inline'
          ? 'inline-flex max-w-full items-center gap-2'
          : 'inline-flex max-w-full flex-col items-center justify-center gap-2'
      }
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-pro-dash-loading=""
      data-pro-dash-loading-size={size}
      data-pro-dash-loading-layout={layout}
    >
      <Spin size={size} />
      <span className={textClass}>{PRO_DASH_LOADING_LABEL}</span>
    </span>
  );
}
