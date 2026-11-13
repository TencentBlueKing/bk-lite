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

const readParam = (formParams: Record<string, unknown> | undefined, name?: string) => {
  if (!name || !formParams) return '';
  const value = formParams[name];
  return value === undefined || value === null ? '' : String(value);
};

const staticFields = (
  source: ConditionFieldSource | undefined,
  queryObject: string,
): ConditionFieldOption[] => {
  const items = source?.items || [];
  return items.filter((item) => {
    if (!queryObject || !item.query_objects?.length) return true;
    return item.query_objects.includes(queryObject);
  });
};

interface ConditionFilterControlProps {
  value?: unknown;
  onChange?: (value: ConditionGroup) => void;
  source?: ConditionFieldSource;
  formParams?: Record<string, unknown>;
  /** 组件参数和全局筛都解析过的字段查询。缺省时只按 formParams 解析引用。 */
  resolvedFieldQuery?: ResolvedOptionsQuery;
  fieldQuerySignature?: string;
  queryObject?: string;
  disabled?: boolean;
}

const ConditionFilterControl: React.FC<ConditionFilterControlProps> = ({
  value,
  onChange,
  source,
  formParams,
  resolvedFieldQuery,
  fieldQuerySignature,
  queryObject = '',
  disabled = false,
}) => {
  const api = useDataSourceApi();
  // 这个 hook 每次渲染都返回新对象。放进依赖后，属性加载的 setState 会立刻再发一次请求。
  const apiRef = useRef(api);
  apiRef.current = api;
  const formParamsRef = useRef(formParams);
  formParamsRef.current = formParams;
  const modelScope = source?.kind === 'modelAttrs' ? readParam(formParams, source.modelParam) : '';
  const endScope = source?.kind === 'endModelAttrs'
    ? [
      readParam(formParams, source.startModelParam),
      readParam(formParams, source.associationParam),
    ].join('\0')
    : '';
  const dynamicResolution = source?.kind === 'dynamic'
    ? (resolvedFieldQuery ?? resolveOptionsQueryParams(source.queryParams, (ref) => formParams?.[ref]))
    : undefined;
  const dynamicScope = source?.kind === 'dynamic'
    ? [
      fieldQuerySignature || stableStringify(dynamicResolution),
      source.sourceRef?.value || source.sourceId || '',
      source.valueField || '',
      source.labelField || '',
    ].join('\0')
    : '';
  const fieldScope = source?.kind === 'modelAttrs'
    ? `model\0${modelScope}`
    : source?.kind === 'endModelAttrs'
      ? `end\0${endScope}`
      : source?.kind === 'dynamic'
        ? `dynamic\0${dynamicScope}`
        : '';
  // 范围一切换，旧的字段列表就不能再拿来校验。否则重开抽屉时会在属性返回前把已存条件清掉。
  const [loadedFields, setLoadedFields] = useState<{ scope: string; fields: ConditionFieldOption[] }>({
    scope: '',
    fields: [],
  });
  const fieldsReady = !source || source.kind === 'static' || loadedFields.scope === fieldScope;
  const baseFields = source?.kind === 'static' || !source
    ? staticFields(source, queryObject)
    : (fieldsReady ? loadedFields.fields : []);
  const fields = baseFields.map(presentConditionField);

  useEffect(() => {
    if (source?.kind !== 'modelAttrs' && source?.kind !== 'endModelAttrs') return undefined;
    let cancelled = false;
    const scope = fieldScope;
    const load = async () => {
      const modelId = source.kind === 'modelAttrs'
        ? modelScope
        : await resolveEndModel(apiRef.current, source, formParamsRef.current);
      if (cancelled) return;
      if (!modelId) {
        setLoadedFields({ scope, fields: [] });
        return;
      }
      try {
        const loaded = await loadConditionModelFields(apiRef.current, modelId);
        if (!cancelled) setLoadedFields({ scope, fields: loaded });
      } catch {
        if (!cancelled) setLoadedFields({ scope, fields: [] });
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [fieldScope, modelScope, source]);

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
        queryObject={queryObject}
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

export const loadConditionModelFields = async (
  api: ReturnType<typeof useDataSourceApi>,
  modelId: string,
): Promise<ConditionFieldOption[]> => {
  const sourceId = await resolveSourceId(api, 'cmdb/list_cmdb_attr_options');
  if (!sourceId) return [];
  const { data } = await api.getSourceDataByApiId(sourceId, { model_id: modelId });
  return extractDataSourceItems(data).map((item) => ({
    value: String(item.attr_id || ''),
    label: String(item.attr_name || item.attr_id || ''),
    valueType: (item.value_type === 'number' || item.value_type === 'enum' ? item.value_type : 'string') as ConditionFieldOption['valueType'],
    options: Array.isArray(item.options)
      ? item.options.filter((option) => option && typeof option === 'object').map((option) => {
        const record = option as { label?: unknown; value?: unknown };
        return { label: String(record.label || record.value || ''), value: String(record.value || '') };
      })
      : [],
  })).filter((item) => item.value);
};

const resolveEndModel = async (
  api: ReturnType<typeof useDataSourceApi>,
  source: ConditionFieldSource,
  formParams: Record<string, unknown> | undefined,
) => {
  const startModel = readParam(formParams, source.startModelParam);
  const association = readParam(formParams, source.associationParam);
  if (!startModel || !association) return '';
  const sourceId = await resolveSourceId(api, 'cmdb/get_model_association_options');
  if (!sourceId) return '';
  const { data } = await api.getSourceDataByApiId(sourceId, { model_id: startModel });
  const row = extractDataSourceItems(data).find((item) => String(item.model_asst_id || '') === association);
  if (!row) return '';
  const src = String(row.src_model_id || '');
  const dst = String(row.dst_model_id || '');
  return src === startModel ? dst : src;
};

export default ConditionFilterControl;
