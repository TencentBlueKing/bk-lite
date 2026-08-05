/**
 * 监控对象图标与 Web 一致：后端 `icon` 字段 → `/assets/icons/{icon}.svg`。
 * H5 网关已把 `/assets/` 反代到 Web；本地开发可走 NEXT_PUBLIC_API_URL。
 */

const WEB_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '');
const DEFAULT_OBJECT_ICON = 'cc-default_默认';
const SAFE_ICON_SEGMENT = /^[\w\u4e00-\u9fff.-]+$/u;

export function resolveMonitorObjectIconUrl(icon?: string): string {
  const raw = (icon || '').trim();
  const fileBase = SAFE_ICON_SEGMENT.test(raw) && !raw.includes('..') ? raw : DEFAULT_OBJECT_ICON;
  const path = `/assets/icons/${fileBase}.svg`;
  return WEB_ORIGIN ? `${WEB_ORIGIN}${path}` : path;
}

export function monitorObjectIconFallbackUrl(): string {
  return resolveMonitorObjectIconUrl(DEFAULT_OBJECT_ICON);
}
