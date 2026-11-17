'use client';

import React, { useEffect, useRef, useState } from 'react';
import type {
  ConditionFieldOption,
  ConditionFieldSource,
} from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import ConditionFilterInput from '@/app/ops-analysis/components/conditionFilterInput';
import { conditionFieldFromSourceRow, presentConditionField } from '@/app/ops-analysis/utils/conditionFieldSource';
import { extractDataSourceItems, resolveDynamicSourceId } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  parseConditionGroup,
  reconcileConditionRows,
  type ConditionGroup,
} from '@/app/ops-analysis/utils/conditionFilter';
import {
  resolveOptionsQueryParams,
  stableStringify,
  type ResolvedOptionsQuery,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';

const sourceIds = new Map<string, number>();

const staticFields = (
  source: ConditionFieldSource | undefined,
): ConditionFieldOption[] => source?.items || [];

interface ConditionFilterControlProps {
  value?: unknown;
  onChange?: (value: ConditionGroup) => void;
  source?: ConditionFieldSource;
  formParams?: Record<string, unknown>;
  /** 组件参数和全局筛都解析过的字段查询。缺省时只按 formParams 解析引用。 */
  resolvedFieldQuery?: ResolvedOptionsQuery;
  fieldQuerySignature?: string;
  disabled?: boolean;
}

const ConditionFilterControl: React.FC<ConditionFilterControlProps> = ({
  value,
  onChange,
  source,
  formParams,
  resolvedFieldQuery,
  fieldQuerySignature,
  disabled = false,
}) => {
  const api = useDataSourceApi();
  // 这个 hook 每次渲染都返回新对象。放进依赖后，属性加载的 setState 会立刻再发一次请求。
  const apiRef = useRef(api);
  apiRef.current = api;
  const dynamicResolution = source?.kind === 'dynamic'
    ? (resolvedFieldQuery ?? resolveOptionsQueryParams(source.queryParams, (ref) => formParams?.[ref]))
    : undefined;
  const fieldScope = source?.kind === 'dynamic'
    ? [
      'dynamic',
      fieldQuerySignature || stableStringify(dynamicResolution),
      source.sourceRef?.value || source.sourceId || '',
      source.valueField || '',
      source.labelField || '',
    ].join('\0')
    : '';
  // 范围一切换，旧的字段列表就不能再拿来校验。否则重开抽屉时会在属性返回前把已存条件清掉。
  const [loadedFields, setLoadedFields] = useState<{ scope: string; fields: ConditionFieldOption[] }>({
    scope: '',
    fields: [],
  });
  const fieldsReady = !source || source.kind === 'static' || loadedFields.scope === fieldScope;
  const baseFields = source?.kind === 'static' || !source
    ? staticFields(source)
    : (fieldsReady ? loadedFields.fields : []);
  const fields = baseFields.map(presentConditionField);

  useEffect(() => {
    if (source?.kind !== 'dynamic') return undefined;
    const scope = fieldScope;
    const resolution = dynamicResolution;
    if (!resolution || resolution.blocked) {
      setLoadedFields({ scope, fields: [] });
      return undefined;
    }
    const valueField = source.valueField || '';
    const labelField = source.labelField || '';
    let cancelled = false;
    void (async () => {
      try {
        const sourceId = source.sourceRef
          ? await resolveSourceId(apiRef.current, source.sourceRef.value)
          : source.sourceId;
        if (cancelled) return;
        if (!sourceId) {
          setLoadedFields({ scope, fields: [] });
          return;
        }
        const { data } = await apiRef.current.getSourceDataByApiId(sourceId, resolution.params);
        if (cancelled) return;
        const loaded = extractDataSourceItems(data)
          .map((item) => conditionFieldFromSourceRow(item, valueField, labelField))
          .filter((item): item is ConditionFieldOption => Boolean(item));
        setLoadedFields({ scope, fields: loaded });
      } catch {
        if (!cancelled) setLoadedFields({ scope, fields: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
    // 范围字符串已经带上查询结果、数据源和取值列。source 和解析对象每次渲染都可能是新的。
  }, [fieldScope]);

  useEffect(() => {
    if (!fieldsReady || !onChange) return;
    const group = parseConditionGroup(value);
    const next = reconcileConditionRows(group, fields);
    if (JSON.stringify(next) !== JSON.stringify(group)) onChange(next);
  }, [fields, fieldsReady, onChange, value]);

  return (
    <ConditionFilterInput
      value={value}
      onChange={onChange}
      fields={fields}
      disabled={disabled}
    />
  );
};

const resolveSourceId = async (
  api: ReturnType<typeof useDataSourceApi>,
  restApi: string,
) => {
  const cached = sourceIds.get(restApi);
  if (cached) return cached;
  const response = await api.getDataSourceList({ page_size: -1 });
  const items = extractDataSourceItems(response) as Array<{ id?: number; name?: string; rest_api?: string }>;
  items.forEach((item) => {
    if (typeof item.id === 'number' && item.rest_api) sourceIds.set(item.rest_api, item.id);
  });
  return resolveDynamicSourceId(
    { type: 'dynamic', sourceRef: { type: 'rest_api', value: restApi }, valueField: 'id', labelField: 'name' },
    items.filter((item): item is { id: number; name?: string; rest_api?: string } => typeof item.id === 'number'),
  );
};

export default ConditionFilterControl;
