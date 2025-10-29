import React from 'react';
import { TooltipProps } from 'recharts';
import customTooltipStyle from './index.module.scss';
import { getEnumValue } from '@/app/monitor/utils/common';
import { MetricItem } from '@/app/monitor/types';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

interface CustomToolTipProps extends Omit<TooltipProps<any, string>, 'unit'> {
  unit?: string;
  visible?: boolean;
  metric?: MetricItem;
}

const CustomTooltip: React.FC<CustomToolTipProps> = ({
  active,
  payload,
  label,
  metric = {},
  visible = true,
}) => {
  const { convertToLocalizedTime } = useLocalizedTime();
  if (active && payload?.length && visible) {
    // 对payload进行排序
    const sortedPayload = [...payload].sort((a, b) => {
      const valueA = getEnumValue(metric as MetricItem, a.value);
      const valueB = getEnumValue(metric as MetricItem, b.value);
      return valueB - valueA; // 从大到小排序
    });

    return (
      <div className={customTooltipStyle.customTooltip}>
        <p className="label font-[600]">{`${convertToLocalizedTime(
          new Date(label * 1000) + ''
        )}`}</p>
        {sortedPayload.map((item: any, index: number) => (
          <div key={index}>
            <div className="flex items-center mt-[4px]">
              <span
                style={{
                  display: 'inline-block',
                  width: '10px',
                  height: '10px',
                  backgroundColor: item.color,
                  borderRadius: '50%',
                  marginRight: '5px',
                }}
              ></span>
              {(item.payload.details?.[item.dataKey] || [])
                .map((detail: any) =>
                  detail.label
                    ? `${detail.label}：${detail.value}`
                    : detail.value
                )
                .join('-')}
              <span className="font-[600] ml-[10px]">
                {getEnumValue(metric as MetricItem, item.value)}
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
