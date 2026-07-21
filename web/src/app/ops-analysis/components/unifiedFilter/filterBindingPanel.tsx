'use client';

import React, { useMemo } from 'react';
import { Switch, Tag, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  UnifiedFilterDefinition,
  FilterBindings,
} from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import CompactEmptyState from '@/app/ops-analysis/components/compactEmptyState';
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
  onChange,
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

  const handleBindingChange = (filterId: string, enabled: boolean) => {
    onChange({
      ...safeFilterBindings,
      [filterId]: enabled,
    });
  };

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
            className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${
              canBind
                ? 'bg-gray-50 border-gray-100'
                : 'bg-gray-100 border-gray-200 opacity-60'
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm text-(--color-text-1)">{displayName}</span>
                <Tag
                  color={param.type === 'timeRange' ? 'blue' : param.type === 'dateRange' ? 'purple' : 'green'}
                  style={{ marginRight: 0 }}
                >
                  {getTypeLabel(param.type)}
                </Tag>
                {!canBind && (
                  <Tag color="default">{t('dashboard.filterDisabled')}</Tag>
                )}
              </div>
              <div className="text-xs text-(--color-text-3) mt-0.5 font-mono">{param.name}</div>
            </div>
            <div className="ml-3 flex-shrink-0">
              {canBind ? (
                <Switch
                  size="small"
                  checked={isEnabled}
                  onChange={(checked) => handleBindingChange(filterId, checked)}
                />
              ) : (
                <Tooltip title={t('dashboard.filterDisabledTip')}>
                  <Switch size="small" checked={false} disabled />
                </Tooltip>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default FilterBindingPanel;
