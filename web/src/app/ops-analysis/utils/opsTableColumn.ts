import type { CSSProperties } from 'react';

/** 画布列宽。非法值留给公共表格按自己的默认宽处理。 */
export function resolveOpsTableColumnWidth(width?: number): number | undefined {
  if (typeof width !== 'number' || !Number.isFinite(width) || width <= 0) {
    return undefined;
  }
  return width;
}

/**
 * 文字跟单元格走。公共表格会把列拉满容器，这里不再用固定像素卡住文字。
 */
export function opsTableCellTextStyle(color?: string): CSSProperties {
  const style: CSSProperties = {
    display: 'block',
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  };
  if (color) {
    style.color = color;
    style.fontWeight = 600;
  }
  return style;
}
