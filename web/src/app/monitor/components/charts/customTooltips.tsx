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
      const normalizeInlineText = (text?: string) =>
        text?.replace(/\s+/g, ' ').trim() || '';
      const labelText = normalizeInlineText(detail.label);
      const valueText = normalizeInlineText(detail.value);

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
      const valueA = Number(getEnumValue(metric as MetricItem, a.value));
      const valueB = Number(getEnumValue(metric as MetricItem, b.value));
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
        {sortedPayload.map((item: any, index: number) => {
          const dimensionText = (item.payload.details?.[item.dataKey] || [])
            .map((detail: any) => formatDetailText(detail))
            .filter(Boolean)
            .join(' · ');

          return (
            <div
              key={item.dataKey || index}
              className="mt-[4px] text-[13px]"
              style={{
                display: 'grid',
                gridTemplateColumns: `${dark ? '16px' : '10px'} minmax(0, 1fr) max-content`,
                alignItems: 'center',
                columnGap: dark ? 8 : 6,
                minWidth: 0
              }}
            >
              {dark ? (
                <span
                  style={{
                    width: '16px',
                    height: 0,
                    borderTop: `2px solid ${item.color}`
                  }}
                />
              ) : (
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: item.color,
                    borderRadius: '50%'
                  }}
                />
              )}
              <span
                title={dimensionText}
                style={{
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}
              >
                {dimensionText}
              </span>
              <span
                className="font-[600] whitespace-nowrap"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {getValue(item)}
              </span>
            </div>
          );
        })}
      </div>
    );
  }
  return null;
};

export default CustomTooltip;
