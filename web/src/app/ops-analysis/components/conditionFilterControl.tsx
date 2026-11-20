'use client';

import React, { useEffect, useRef, useState } from 'react';
import type {
  ConditionFieldOption,
  ConditionFieldSource,
} from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import ConditionFilterInput from '@/app/ops-analysis/components/conditionFilterInput';
import { conditionFieldFromSourceRow, presentConditionField } from '@/app/ops-analysis/utils/conditionFieldSource';
import { classifyOptionSource, extractDataSourceItems } from '@/app/ops-analysis/utils/paramInputConfigUtils';
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
import { useTranslation } from '@/utils/i18n';

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
  /** 当前用户能否打开组件编辑器修好选项来源。文案不授予保存权限。 */
  canRepairOptionSource?: boolean;
}

const ConditionFilterControl: React.FC<ConditionFilterControlProps> = ({
  value,
  onChange,
  source,
  formParams,
  resolvedFieldQuery,
  fieldQuerySignature,
  disabled = false,
  canRepairOptionSource = false,
}) => {
  const { t } = useTranslation();
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
      String(source.sourceId ?? ''),
      source.builtinKey || '',
      source.sourceRef?.value || '',
      source.valueField || '',
      source.labelField || '',
    ].join('\0')
    : '';
  // 范围一切换，旧的字段列表就不能再拿来校验。否则重开抽屉时会在属性返回前把已存条件清掉。
  const [loadedFields, setLoadedFields] = useState<{
    scope: string;
    fields: ConditionFieldOption[];
    unresolved?: 'ambiguous' | 'missing' | 'forbidden';
  }>({
    scope: '',
    fields: [],
  });
  const fieldsReady = !source || source.kind === 'static' || (
    loadedFields.scope === fieldScope && !loadedFields.unresolved
  );
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
        const resolved = await resolveConditionSource(apiRef.current, source);
        if (cancelled) return;
        if (resolved.status !== 'resolved') {
          setLoadedFields({ scope, fields: [], unresolved: resolved.status });
          return;
        }
        const sourceId = resolved.id;
        const { data } = await apiRef.current.getSourceDataByApiId(sourceId, resolution.params, {
          suppressErrorNotification: true,
        });
        if (cancelled) return;
        const loaded = extractDataSourceItems(data)
          .map((item) => conditionFieldFromSourceRow(item, valueField, labelField))
          .filter((item): item is ConditionFieldOption => Boolean(item));
        setLoadedFields({ scope, fields: loaded });
      } catch (error) {
        if (cancelled) return;
        const status = readHttpStatus(error);
        setLoadedFields({
          scope,
          fields: [],
          unresolved: status === 403 ? 'forbidden' : 'missing',
        });
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

  const unresolved = loadedFields.scope === fieldScope ? loadedFields.unresolved : undefined;
  const hintKey = unresolved === 'ambiguous'
    ? (canRepairOptionSource
      ? 'paramInput.dynamic.optionSourceAmbiguous'
      : 'paramInput.dynamic.optionSourceAmbiguousReadonly')
    : unresolved === 'forbidden'
      ? 'paramInput.dynamic.optionSourceForbidden'
      : unresolved === 'missing'
        ? 'paramInput.dynamic.optionSourceMissing'
        : '';

  return (
    <div>
      <ConditionFilterInput
        value={value}
        onChange={onChange}
        fields={fields}
        disabled={disabled || Boolean(unresolved)}
      />
      {hintKey ? (
        <div className="mt-1 text-xs text-[var(--color-text-2)]">{t(hintKey)}</div>
      ) : null}
    </div>
  );
};

const readHttpStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  if ('status' in error && typeof (error as { status?: unknown }).status === 'number') {
    return (error as { status: number }).status;
  }
  const response = (error as { response?: { status?: unknown } }).response;
  if (response && typeof response.status === 'number') return response.status;
  return undefined;
};

const resolveConditionSource = async (
  api: ReturnType<typeof useDataSourceApi> & {
    resolveOptionSource?: (body: { sourceId?: number; builtinKey?: string; sourceRef?: string }) => Promise<{ status?: string; id?: number }>;
  },
  source: ConditionFieldSource,
): Promise<{ status: 'resolved'; id: number } | { status: 'ambiguous' | 'missing' | 'forbidden' }> => {
  if (api.resolveOptionSource) {
    const identity = await api.resolveOptionSource({
      sourceId: typeof source.sourceId === 'number' ? source.sourceId : undefined,
      builtinKey: source.builtinKey,
      sourceRef: source.sourceRef?.value,
    });
    if (identity.status === 'resolved' && typeof identity.id === 'number') {
      return { status: 'resolved', id: identity.id };
    }
    if (identity.status === 'ambiguous' || identity.status === 'forbidden') return { status: identity.status };
    return { status: 'missing' };
  }
  if (typeof source.sourceId === 'number') return { status: 'resolved', id: source.sourceId };
  const response = await api.getDataSourceList({ page_size: -1 });
  const items = extractDataSourceItems(response).filter(
    (item): item is { id: number; name?: string; rest_api?: string; build_in_key?: string | null } =>
      typeof (item as { id?: unknown }).id === 'number',
  );
  const classified = classifyOptionSource(source, items);
  if (classified.status === 'resolved') return classified;
  return classified.status === 'ambiguous' ? { status: 'ambiguous' } : { status: 'missing' };
};

export default ConditionFilterControl;
