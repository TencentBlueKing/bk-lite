import React from 'react';
import { ExportOutlined } from '@ant-design/icons';

/** 数据联动在密铺卡片/列表上只露出小箭头，不弹黑底文字提示。 */
const DataLinkHoverMark: React.FC<{
  show?: boolean;
  label?: string;
  className?: string;
}> = ({ show = false, label, className }) => {
  if (!show) return null;
  return (
    <ExportOutlined
      aria-hidden={!label}
      aria-label={label}
      className={`pointer-events-none shrink-0 text-[10px] text-(--color-text-3) opacity-0 transition-opacity group-hover/data-link:opacity-100 group-focus-within/data-link:opacity-100 ${className ?? ''}`}
    />
  );
};

export default DataLinkHoverMark;
