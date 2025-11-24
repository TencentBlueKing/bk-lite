import React from 'react';
import { getEnumValue, findUnitNameById } from '@/app/monitor/utils/common';
import { MetricItem } from '@/app/monitor/types';

interface SingleValueDisplayProps {
  value: number | string;
  unit?: string;
  showUnit?: string;
  label?: string;
  color?: string;
  fontSize?: number; // 新增属性，用于控制字体大小
  unitFontSize?: number; // 新增属性，用于控制单位的字体大小
  labelFontSize?: number; // 新增属性，用于控制标签的字体大小
  metric?: MetricItem;
}

const SingleValueDisplay: React.FC<SingleValueDisplayProps> = ({
  value,
  unit,
  label,
  showUnit = false,
  color = 'var(--color-text-1)',
  fontSize = 24, // 默认字体大小
  unitFontSize = 16, // 默认单位字体大小
  labelFontSize = 14, // 默认标签字体大小
  metric = {},
}) => {
  return (
    <div className="bg-[var(--color-bg-1)]">
      <div
        className="flex items-center justify-center font-bold"
        style={{ color, fontSize }}
      >
        {getEnumValue(metric as MetricItem, value)}
        {showUnit && (
          <span className="ml-[4px]" style={{ fontSize: unitFontSize }}>
            {findUnitNameById(unit)}
          </span>
        )}
      </div>
      {label && (
        <div
          className="flex items-center justify-center text-[var(--color-text-3)] mt-[10px]"
          style={{ fontSize: labelFontSize }}
        >
          {label}
        </div>
      )}
    </div>
  );
};

SingleValueDisplay.displayName = 'SingleValueDisplay';

export default SingleValueDisplay;
