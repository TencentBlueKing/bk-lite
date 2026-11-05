import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { isBindableDataSourceParamType } from '@/app/ops-analysis/utils/dataSourceParamContract';
import { OPTIONS_QUERY_INVALID } from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import { pickMatchingFilterDefinition } from '@/app/ops-analysis/utils/scanUnifiedFilterParams';

export type OptionsQueryCandidateOrigin = 'globalFilter' | 'componentParam';

export interface OptionsQueryCandidateFilter {
  id: string;
  key: string;
  label?: string;
  type?: string;
  enabled?: boolean;
  sourceHint?: string;
  queryParams?: Record<string, unknown>;
  inputConfig?: InputControlConfig;
}

export interface OptionsQueryCandidateParam {
  name: string;
  label?: string;
  type?: string;
  filterType?: string;
  value?: unknown;
  inputConfig?: InputControlConfig;
  inputMode?: string;
  queryParams?: Record<string, unknown>;
}

export interface OptionsQueryEditorContext {
  scope: 'globalFilter' | 'component';
  self: { id?: string; key: string; label?: string };
  componentParams?: OptionsQueryCandidateParam[];
  globalFilters?: OptionsQueryCandidateFilter[];
}

export interface OptionsQueryCandidateChoice {
  ref: string;
  origin: OptionsQueryCandidateOrigin;
  displayName: string;
  key: string;
  type?: string;
  sourceHint?: string;
}

const typeMatches = (candidateType: string | undefined, expectedType?: string) => {
  if (candidateType && !isBindableDataSourceParamType(candidateType)) return false;
  if (!expectedType) return !candidateType || isBindableDataSourceParamType(candidateType);
  return candidateType === expectedType;
};

/** 下拉只排除自身、类型和 scope。成环、超过 3 级留到保存时校验。 */
export const listOptionsQueryCandidates = ({
  context,
  expectedType,
}: {
  context?: OptionsQueryEditorContext;
  expectedType?: string;
}): OptionsQueryCandidateChoice[] => {
  if (!context?.self.key && !context?.self.id) return [];
  const selfName = context.scope === 'globalFilter'
    ? (context.self.id || context.self.key)
    : context.self.key;
  const filters = (context.globalFilters ?? []).filter((filter) => filter.id && filter.key);
  const params = context.scope === 'component'
    ? (context.componentParams ?? []).filter((param) => param.name)
    : [];

  const eligibleFilters = filters.filter((filter) => (
    filter.enabled !== false
    && filter.id !== context.self.id
    && filter.id !== selfName
    && typeMatches(filter.type, expectedType)
  ));
  const eligibleParams = params.filter((param) => (
    param.name !== selfName
    && typeMatches(param.type, expectedType)
  ));
  const choices: OptionsQueryCandidateChoice[] = [
    ...eligibleParams.map((param) => ({
      ref: param.name,
      origin: 'componentParam' as const,
      displayName: param.label?.trim() || param.name,
      key: param.name,
      type: param.type,
    })),
    ...eligibleFilters.map((filter) => ({
      ref: filter.id,
      origin: 'globalFilter' as const,
      displayName: filter.label?.trim() || filter.key,
      key: filter.key,
      type: filter.type,
      sourceHint: filter.sourceHint,
    })),
  ];
  choices.sort((left, right) => (
    left.origin.localeCompare(right.origin)
    || left.key.localeCompare(right.key)
    || left.ref.localeCompare(right.ref)
  ));
  return choices;
};

type ChoiceTranslator = (
  key: string,
  fallback?: string,
  values?: Record<string, string>,
) => string;

export const formatOptionsQueryCandidateLabel = (
  choice: OptionsQueryCandidateChoice,
  choices: OptionsQueryCandidateChoice[],
  t: ChoiceTranslator,
) => {
  const origin = choice.origin === 'globalFilter'
    ? t('paramInput.dynamic.originGlobalFilter')
    : t('paramInput.dynamic.originComponentParam');
  const sameName = choices.filter((item) => (
    item.origin === choice.origin && item.displayName === choice.displayName
  ));
  if (sameName.length <= 1) {
    return t('paramInput.dynamic.refChoice', undefined, { origin, name: choice.displayName });
  }
  const hint = choice.sourceHint?.trim();
  if (hint && sameName.some((item) => item.sourceHint?.trim() !== hint)) {
    return t('paramInput.dynamic.refChoiceWithHint', undefined, {
      origin,
      name: choice.displayName,
      hint,
    });
  }
  return t('paramInput.dynamic.refChoiceWithKey', undefined, {
    origin,
    name: choice.displayName,
    key: choice.key,
  });
};

const componentParamOwnsRef = (ref: string, context?: OptionsQueryEditorContext) => (
  context?.scope === 'component'
  && (context.componentParams ?? []).some((param) => param.name === ref)
);

/**
 * 保存时：已经是筛 id 的保持筛 id。
 * 本卡存在同名组件参数时，保留参数名，不把组件参引用收成同 key 的筛 id。
 * 其余裸名在筛唯一或能按选项身份对上时写成 definition.id。
 */
export const canonicalizeOptionsQueryRef = (
  ref: string,
  context?: OptionsQueryEditorContext,
): string => {
  const trimmed = ref.trim();
  if (!trimmed) return trimmed;
  const filters = (context?.globalFilters ?? []).filter((filter) => filter.enabled !== false && filter.id);
  if (filters.some((filter) => filter.id === trimmed)) return trimmed;
  if (componentParamOwnsRef(trimmed, context)) return trimmed;
  const byKey = filters.filter((filter) => filter.key === trimmed);
  if (byKey.length === 1) return byKey[0].id;
  if (byKey.length > 1) {
    const param = context?.componentParams?.find((item) => item.name === trimmed);
    if (param) {
      const picked = pickMatchingFilterDefinition(
        byKey.map(toFilterDefinition),
        {
          name: param.name,
          type: param.type,
          inputConfig: param.inputConfig,
          inputMode: param.inputMode,
        },
      );
      if (picked) return picked.id;
    }
  }
  return trimmed;
};

/** 回显按 ref 精确对应。组件参名不因为唯一同 key 筛而显示成全局筛选。 */
export const resolveOptionsQueryChoice = (
  ref: string,
  choices: OptionsQueryCandidateChoice[],
  context?: OptionsQueryEditorContext,
): OptionsQueryCandidateChoice | undefined => {
  const exact = choices.find((choice) => choice.ref === ref);
  if (exact) return exact;
  if (componentParamOwnsRef(ref, context)) return undefined;
  const globalMatches = choices.filter((choice) => (
    choice.origin === 'globalFilter' && choice.key === ref
  ));
  return globalMatches.length === 1 ? globalMatches[0] : undefined;
};

const toFilterDefinition = (
  filter: OptionsQueryCandidateFilter,
): UnifiedFilterDefinition => ({
  id: filter.id,
  key: filter.key,
  name: filter.label || filter.key,
  type: (filter.type as UnifiedFilterDefinition['type']) || 'string',
  order: 0,
  enabled: filter.enabled !== false,
  inputConfig: filter.inputConfig,
});

/**
 * 组件参数若可跟随全局筛选，引用读筛选当前值。
 * 绑定缺键与绑定面板一样视为跟随；只有显式 false 才读参数自身的值。
 */
export const readComponentOptionsQueryUpstream = ({
  ref,
  componentParams,
  definitions,
  filterBindings,
  readFilterValue,
}: {
  ref: string;
  componentParams: OptionsQueryCandidateParam[];
  definitions: OptionsQueryCandidateFilter[];
  filterBindings?: Record<string, boolean> | null;
  readFilterValue: (id: string) => unknown;
}): unknown => {
  const enabled = definitions.filter((filter) => filter.enabled !== false && filter.id);
  const byId = enabled.find((filter) => filter.id === ref);
  if (byId) return readFilterValue(byId.id);

  const param = componentParams.find((item) => item.name === ref);
  if (param) {
    if (param.filterType === 'filter') {
      const bindings = filterBindings ?? {};
      const matched = enabled.filter((filter) => (
        filter.key === param.name && filter.type === param.type
      ));
      const active = matched.filter((filter) => bindings[filter.id] !== false);
      if (active.length === 1) return readFilterValue(active[0].id);
      if (active.length > 1) {
        const picked = pickMatchingFilterDefinition(
          active.map(toFilterDefinition),
          param,
        );
        return picked ? readFilterValue(picked.id) : OPTIONS_QUERY_INVALID;
      }
      if (matched.length > 0) return param.value;
    }
    return param.value;
  }

  const byKey = enabled.filter((filter) => filter.key === ref);
  if (byKey.length > 1) return OPTIONS_QUERY_INVALID;
  if (byKey.length === 1) return readFilterValue(byKey[0].id);
  return undefined;
};
