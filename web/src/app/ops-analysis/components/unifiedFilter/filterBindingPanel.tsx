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
  onChange?: (bindings: FilterBindings) => void;
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

  const getTypeTagColor = (type: string) => {
    if (type === 'timeRange') return 'blue';
    if (type === 'dateRange') return 'purple';
    return 'default';
  };

  return (
    <div className="divide-y divide-(--color-border-1) rounded-md border border-(--color-border-1) bg-(--color-bg)">
      {bindableParams.map(({ param, matchedDefinition, canBind, filterId }) => {
        const isEnabled = safeFilterBindings[filterId] ?? false;
        const displayName = matchedDefinition?.name || param.alias_name || param.name;
        const hasCustomName = Boolean(displayName && displayName !== param.name);

        return (
          <div
            key={filterId}
            className={`flex items-center justify-between px-3.5 py-2.5 transition-colors ${
              canBind ? 'hover:bg-(--color-fill-1)/40' : 'opacity-60'
            }`}
          >
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <span className="truncate text-[13px] font-medium text-(--color-text-1)">
                {displayName}
              </span>
              {hasCustomName ? (
                <span className="truncate font-mono text-xs text-(--color-text-3)">
                  ({param.name})
                </span>
              ) : null}
              <Tag
                bordered={false}
                color={getTypeTagColor(param.type)}
                className="m-0 text-[11px] font-normal leading-tight"
              >
                {getTypeLabel(param.type)}
              </Tag>
              {!canBind ? (
                <Tag
                  bordered={false}
                  className="m-0 text-[11px] font-normal leading-tight text-(--color-text-4)"
                >
                  {t('dashboard.filterDisabled')}
                </Tag>
              ) : null}
            </div>
            <div className="ml-3 flex shrink-0 items-center gap-2">
              <span className="text-xs text-(--color-text-3)">
                {canBind && isEnabled
                  ? t('dashboard.filterLinked')
                  : t('dashboard.filterUnlinked')}
              </span>
              <Switch
                size="small"
                checked={canBind && isEnabled}
                disabled
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default FilterBindingPanel;
