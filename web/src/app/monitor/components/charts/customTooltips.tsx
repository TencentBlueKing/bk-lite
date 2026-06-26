import React, { useCallback } from 'react';
import { TooltipProps } from 'recharts';
import customTooltipStyle from './index.module.scss';
import { getEnumValue } from '@/app/monitor/utils/common';
import { MetricItem, TableDataItem } from '@/app/monitor/types';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';

interface CustomToolTipProps extends Omit<TooltipProps<any, string>, 'unit'> {
  unit?: string;
  visible?: boolean;
  metric?: MetricItem;
  maxHeight?: number;
  maxWidth?: number;
  seriesUnits?: Record<string, string>;
  // 深色「报告风」变体：深底白字 + 线段色标。仅折线图启用，
  // 柱状图等其它消费方不传，保持原浅色 + 圆点样式不变。
  dark?: boolean;
}

const CustomTooltip: React.FC<CustomToolTipProps> = ({
  active,
  payload,
  label,
  metric = {},
  unit = '',
  visible = true,
  maxHeight,
  maxWidth,
  seriesUnits = {},
  dark = false
}) => {
  const { convertToLocalizedTime } = useLocalizedTime();
  const { findUnitNameById } = useUnitTransform();

  const formatDetailText = useCallback(
    (detail: { label?: string; value?: string }) => {
      const labelText = detail.label?.trim() || '';
      const valueText = detail.value?.trim() || '';

      if (labelText && valueText && labelText !== valueText) {
        return `${labelText}：${valueText}`;
      }

      return valueText || labelText;
    },
    []
  );

  const getValue = useCallback(
    (item: TableDataItem & { dataKey?: string }) => {
      const value = getEnumValue(metric as MetricItem, item.value);
      if (value === '--') {
        return value;
      }
      const currentUnit = (item.dataKey && seriesUnits[item.dataKey]) || unit;
      return `${value} ${findUnitNameById(currentUnit)}`;
    },
    [metric, unit, getEnumValue, findUnitNameById, seriesUnits]
  );

  if (active && payload?.length && visible) {
    // 对payload进行排序
    const sortedPayload = [...payload].sort((a, b) => {
      const valueA = getEnumValue(metric as MetricItem, a.value);
      const valueB = getEnumValue(metric as MetricItem, b.value);
      return valueB - valueA; // 从大到小排序
    });

    return (
      <div
        className={customTooltipStyle.customTooltip}
        style={{
          ...(maxHeight ? { maxHeight: `${maxHeight}px` } : {}),
          ...(maxWidth ? { maxWidth: `${maxWidth}px` } : {}),
          // 深色变体：覆盖浅色底，并用半透明白边在暗色图表背景上保持分界
          ...(dark
            ? {
              background: 'rgba(28, 28, 30, 0.92)',
              color: '#fff',
              border: '1px solid rgba(255, 255, 255, 0.14)',
              borderRadius: '6px',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.28)',
              fontSize: '12px',
              padding: '8px 12px 10px'
            }
            : {})
        }}
      >
        <p className="label font-[600]">{`${convertToLocalizedTime(
          new Date(label * 1000) + ''
        )}`}</p>
        {sortedPayload.map((item: any, index: number) => (
          <div key={index}>
            <div className="flex items-start mt-[4px] text-[13px]">
              {dark ? (
                <span
                  style={{
                    width: '16px',
                    minWidth: '16px',
                    height: 0,
                    borderTop: `2px solid ${item.color}`,
                    marginRight: '8px',
                    marginTop: '8px'
                  }}
                ></span>
              ) : (
                <span
                  style={{
                    width: '10px',
                    minWidth: '10px',
                    height: '10px',
                    backgroundColor: item.color,
                    borderRadius: '50%',
                    marginRight: '5px',
                    marginTop: '5px'
                  }}
                ></span>
              )}
              <span className="flex-1 min-w-0 break-words">
                {(item.payload.details?.[item.dataKey] || [])
                  .map((detail: any) => formatDetailText(detail))
                  .filter(Boolean)
                  .join('-')}
              </span>
              <span className="font-[600] ml-[10px] whitespace-nowrap">
                {getValue(item)}
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export default CustomTooltip;
