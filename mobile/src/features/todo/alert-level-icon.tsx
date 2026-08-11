'use client';

const ICON_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;
const MOBILE_ALERT_LEVEL_ICONS = new Set([
  'huoyanhuodongtuijian',
  'weiwangguanicon-defuben-',
  'gantanhao1',
  'tixing',
]);

interface AlertLevelIconProps {
  icon?: string;
  className?: string;
}

/** 按 Server 下发的图标名称使用 Mobile 本地字体；未收录的名称不做兜底。 */
export function AlertLevelIcon({ icon = '', className }: AlertLevelIconProps) {
  const normalizedIcon = icon.trim();
  const isDataImage = normalizedIcon.startsWith('data:image/');

  if (isDataImage) {
    return <img src={normalizedIcon} alt="" className={className} aria-hidden="true" />;
  }
  if (!ICON_NAME_PATTERN.test(normalizedIcon) || !MOBILE_ALERT_LEVEL_ICONS.has(normalizedIcon)) {
    return null;
  }

  const iconClassName = `iconfont icon-${normalizedIcon}${className ? ` ${className}` : ''}`;
  return <span className={iconClassName} aria-hidden="true" />;
}
