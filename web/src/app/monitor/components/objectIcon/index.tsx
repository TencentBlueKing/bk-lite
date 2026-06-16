'use client';

import React from 'react';

// 监控对象图标的统一渲染入口。图标名优先取后端对象的 `icon` 字段(与集成对象页一致),
// 缺省/加载失败时回退到默认图标。视图左侧树、仪表盘侧边栏等共用此组件,保证全站对象图标一致。
// 用原生 <img>(与集成对象页同款约定):本地 SVG 矢量图无需 next/image 优化,且可避免其
// 「flex 布局下仅一个维度被修改」的宽高比告警;object-fit: contain 保证非正方形图标不变形。
export const DEFAULT_OBJECT_ICON = 'cc-default_默认';

interface ObjectIconProps {
  icon?: string;
  fallback?: string;
  size?: number;
  className?: string;
}

export const ObjectIcon: React.FC<ObjectIconProps> = ({
  icon,
  fallback = DEFAULT_OBJECT_ICON,
  size = 16,
  className
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

export default ObjectIcon;
