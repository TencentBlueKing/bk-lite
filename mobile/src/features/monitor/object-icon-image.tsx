'use client';

import { monitorObjectIconFallbackUrl, resolveMonitorObjectIconUrl } from '@/features/monitor/object-icon';

interface MonitorObjectIconProps {
  icon?: string;
  size?: number;
  className?: string;
}

/** 与 Web ObjectIcon 同源：`/assets/icons/{icon}.svg`，失败回退默认图标。 */
export default function MonitorObjectIcon({ icon, size = 28, className }: MonitorObjectIconProps) {
  const src = resolveMonitorObjectIconUrl(icon);
  const fallback = monitorObjectIconFallbackUrl();
  return (
    // eslint-disable-next-line @next/next/no-img-element -- 与 Web 一致按需加载同源 SVG
    <img
      className={className}
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }}
      onError={(event) => {
        const img = event.currentTarget;
        if (!img.src.includes('cc-default_默认.svg')) {
          img.src = fallback;
        }
      }}
    />
  );
}
