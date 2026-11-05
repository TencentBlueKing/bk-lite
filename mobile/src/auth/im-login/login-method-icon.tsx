'use client';

import { UserOutline } from 'antd-mobile-icons';

const KNOWN_ICONS = new Set(['zhanghaomima', 'wechat', 'feishu', 'wecom']);

export function LoginMethodIcon({
  icon,
  size = 22,
  className = '',
}: {
  icon?: string;
  size?: number;
  className?: string;
}) {
  const type = icon?.trim();
  if (type && KNOWN_ICONS.has(type)) {
    return (
      <svg
        className={className}
        width={size}
        height={size}
        aria-hidden="true"
        style={{ display: 'block' }}
      >
        <use xlinkHref={`#icon-${type}`} href={`#icon-${type}`} />
      </svg>
    );
  }
  return <UserOutline className={className} fontSize={size} />;
}
