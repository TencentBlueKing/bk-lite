import React, { memo, useMemo, useCallback } from 'react';
import chartStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';

interface DimensionFilterProps {
  data: any[];
  colors: string[];
  visibleAreas: any[];
  details: any;
  onLegendClick: (key: any) => void;
}

const getChartAreaKeys = (arr: any[]) => {
  const keys = new Set();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const dimensionLael = (detail: any) => {
  const arr = (detail || []).map((item: any) => `${item.label}: ${item.value}`);
  return arr.join('-') || '--';
};

const DimensionFilter: React.FC<DimensionFilterProps> = memo(
  ({ data, colors, visibleAreas, details, onLegendClick }) => {
    const { t } = useTranslation();

    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const getDimensionLabel = useCallback(
      (key: string) => {
        return dimensionLael(details[key]);
      },
      [details]
    );

    return (
      <div className={chartStyle.filterArea}>
        <div className="bg-[var(--color-fill-2)] text-[14px] font-[800] p-[4px] text-center">
          {t('monitor.integrations.dimension')}
        </div>
        <ul className="text-[12px]">
          {chartAreaKeys.map((key, index) => {
            const dimensionLabel = getDimensionLabel(key as string);
            return (
              <li
                key={index}
                className={`cursor-pointer ${
                  visibleAreas.includes(key)
                    ? 'text-[var(--color-text-2)]'
                    : 'text-[var(--ant-color-text-disabled)]'
                }`}
                onClick={() => onLegendClick(key)}
              >
                <span
                  className="w-[10px] h-[4px] mr-[10px]"
                  style={{
                    background: visibleAreas.includes(key)
                      ? colors[index]
                      : 'var(--ant-color-bg-container-disabled)',
                  }}
                ></span>
                <span
                  className={`${chartStyle.dimeLabel} hide-text`}
                  title={dimensionLabel}
                >
                  {dimensionLabel}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }
);

DimensionFilter.displayName = 'DimensionFilter';

export default DimensionFilter;
