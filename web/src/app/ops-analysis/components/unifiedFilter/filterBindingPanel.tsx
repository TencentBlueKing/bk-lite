'use client';

import React, { useMemo } from 'react';
import { Switch, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  UnifiedFilterDefinition,
  FilterBindings,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import CompactEmptyState from '@/components/compact-empty-state';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';

interface FilterBindingPanelProps {
  definitions: UnifiedFilterDefinition[];
  dataSourceParams: ParamItem[];
  filterBindings: FilterBindings;
  onChange: (bindings: FilterBindings) => void;
}

interface BindableParam {
  param: ParamItem;
  matchedDefinition?: UnifiedFilterDefinition;
  canBind: boolean;
  filterId: string;
}

const FilterBindingPanel: React.FC<FilterBindingPanelProps> = ({
  definitions,
  dataSourceParams,
  filterBindings,
}) => {
  const { t } = useTranslation();
  const safeFilterBindings = filterBindings || {};

  const bindableParams = useMemo((): BindableParam[] => {
    const filterParams = getBindableFilterParams(dataSourceParams);

    return filterParams.map((param) => {
      const filterId = getFilterDefinitionId(param.name, param.type);
      const matchedDefinition = definitions.find(
        (d) => d.key === param.name && d.type === param.type,
      );
      const canBind = matchedDefinition?.enabled === true;

      return {
        param,
        matchedDefinition,
        canBind,
        filterId,
      };
    });
  }, [dataSourceParams, definitions]);

  if (bindableParams.length === 0) {
    return (
      <CompactEmptyState description={t('dashboard.noUnifiedFilters')} />
    );
  }

  const getTypeLabel = (type: string): string => {
    if (type === 'timeRange') return t('dashboard.timeRange');
    if (type === 'dateRange') return t('dashboard.dateRange');
    return t('dashboard.string');
  };

  return (
    <div className="space-y-2">
      {bindableParams.map(({ param, matchedDefinition, canBind, filterId }) => {
        const isEnabled = safeFilterBindings[filterId] ?? false;
        const displayName = matchedDefinition?.name || param.alias_name || param.name;

        return (
          <div
            key={filterId}
            className={`flex items-center justify-between py-2 ${
              canBind ? '' : 'opacity-60'
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-(--color-text-1)">
                  {displayName}
                </span>
                <Tag
                  color={
                    param.type === 'timeRange'
                      ? 'blue'
                      : param.type === 'dateRange'
                        ? 'purple'
                        : 'green'
                  }
                  className="m-0"
                >
                  {getTypeLabel(param.type)}
                </Tag>
                {!canBind ? (
                  <Tag color="default" className="m-0">
                    {t('dashboard.filterDisabled')}
                  </Tag>
                ) : null}
              </div>
              <div className="mt-0.5 font-mono text-xs text-(--color-text-3)">
                {param.name}
              </div>
            </div>
            <Switch
              size="small"
              className="ml-3 shrink-0"
              checked={canBind && isEnabled}
              disabled
            />
          </div>
        );
      })}
    </div>
  );
};

export default FilterBindingPanel;
