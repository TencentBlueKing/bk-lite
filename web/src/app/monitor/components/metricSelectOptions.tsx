'use client';

import React, { useMemo, useState } from 'react';
import type { DefaultOptionType } from 'antd/es/select';
import type { IndexViewItem, MetricItem } from '@/app/monitor/types';
import './metricSelectOptions.scss';

export type MetricSelectGroup = Pick<IndexViewItem, 'name' | 'display_name'> & {
  child?: MetricItem[] | null;
};

/** 分组指标 Select 的叶子选项：展示中文名 + 灰色英文 ID，并支持双字段搜索。 */
export interface MetricSelectLeafOption extends DefaultOptionType {
  value: number;
  name: string;
  displayLabel: string;
}

/** Ant Design 下拉默认单行高度会裁切双行 option，挂到 Select 的 popupClassName。 */
export const METRIC_SELECT_POPUP_CLASSNAME = 'metric-select-popup';

const metricMatchesSearch = (metric: MetricItem, query: string): boolean => {
  if (!query) return true;
  const displayLabel = (metric.display_name || metric.name || '').toLowerCase();
  const name = (metric.name || '').toLowerCase();
  return displayLabel.includes(query) || name.includes(query);
};

/**
 * 自行按关键词过滤分组叶子项。
 * Ant Design 分组 Select 的 filterOption 对 OptGroup 返回 true 时会保留全部子项，
 * 因此禁用内置过滤，改由 options 生成阶段完成中英文匹配。
 */
export const buildGroupedMetricSelectOptions = (
  groups: MetricSelectGroup[],
  search = '',
): DefaultOptionType[] => {
  const query = search.trim().toLowerCase();
  return groups
    .map((group) => {
      const options = (group.child || [])
        .filter((metric) => metricMatchesSearch(metric, query))
        .map((metric): MetricSelectLeafOption => {
          const displayLabel = metric.display_name || metric.name || '--';
          return {
            value: metric.id,
            name: metric.name,
            displayLabel,
            label: (
              <div className="flex flex-col gap-[2px] py-[2px] leading-[18px]">
                <span className="text-[13px] text-[var(--color-text-1)]">
                  {displayLabel}
                </span>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {metric.name}
                </span>
              </div>
            ),
          };
        });
      if (!options.length) return null;
      return {
        label: group.display_name,
        title: group.name,
        options,
      };
    })
    .filter((group): group is NonNullable<typeof group> => group != null);
};

/** 单实例指标 Select：管理搜索词并生成已过滤 options。 */
export const useMetricSelectOptions = (groups: MetricSelectGroup[]) => {
  const [search, setSearch] = useState('');
  const options = useMemo(
    () => buildGroupedMetricSelectOptions(groups, search),
    [groups, search],
  );

  return {
    options,
    selectSearchProps: {
      showSearch: true as const,
      filterOption: false as const,
      optionLabelProp: 'displayLabel' as const,
      popupClassName: METRIC_SELECT_POPUP_CLASSNAME,
      onSearch: setSearch,
      onDropdownVisibleChange: (open: boolean) => {
        if (!open) setSearch('');
      },
    },
  };
};
