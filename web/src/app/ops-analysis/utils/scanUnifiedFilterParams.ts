import type {
  FilterValue,
  LayoutItem,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  InputControlConfig,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import {
  isBindableDataSourceParamType,
  type BindableDataSourceParamType,
} from '@/app/ops-analysis/utils/dataSourceParamContract';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  optionsSourceCoreKey,
  optionsSourceIdentity,
  optionsSourceIdentityKey,
  optionsSourceSummary,
  type OptionsSourceIdentity,
} from '@/app/ops-analysis/utils/optionsSourceIdentity';
import { migrateParamItemsFromStringList } from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

export interface FilterParamScanInput {
  name: string;
  type: BindableDataSourceParamType;
  alias?: string;
  defaultValue?: FilterValue;
  inputConfig?: InputControlConfig;
  inputMode?: string;
  dataSourceLabel?: string;
}

export interface ScannedFilterGroup {
  key: string;
  type: BindableDataSourceParamType;
  componentCount: number;
  sampleAlias: string;
  sampleDefaultValue: FilterValue;
  sampleInputConfig?: InputControlConfig;
  dataSourceLabels: string[];
  identity: OptionsSourceIdentity;
  mergeKey: string;
  sourceHint: string;
}

export type AssignedFilterGroup = ScannedFilterGroup & {
  id: string;
  suggestedName: string;
};

type ReusableFilterDefinition = Pick<
  UnifiedFilterDefinition,
  'id' | 'key' | 'type' | 'inputConfig' | 'inputMode'
>;

export const isBoardSharedFilterDimension = (input: {
  type?: string;
  inputConfig?: InputControlConfig;
  inputMode?: string;
}): boolean => {
  if (input.type === 'timeRange' || input.type === 'dateRange') return true;
  return normalizeInputConfig(input)?.control === 'organization';
};

/** 同画布同名同类型只并一行，与 getFilterDefinitionId 一致，不因 optionsSource 拆开。 */
export const filterMergeKey = (input: FilterParamScanInput): string =>
  `${input.name}__${input.type}`;

const pushLabel = (labels: string[], label?: string) => {
  const next = label?.trim();
  if (next && !labels.includes(next)) labels.push(next);
};

export const groupFilterParams = (params: FilterParamScanInput[]): ScannedFilterGroup[] => {
  const grouped = new Map<string, ScannedFilterGroup>();
  params.forEach((param) => {
    const inputConfig = normalizeInputConfig(param);
    const mergeKey = filterMergeKey({ ...param, inputConfig });
    const existing = grouped.get(mergeKey);
    if (existing) {
      existing.componentCount += 1;
      pushLabel(existing.dataSourceLabels, param.dataSourceLabel);
      existing.sourceHint = existing.dataSourceLabels.join(' / ')
        || optionsSourceSummary(existing.sampleInputConfig);
      // 先扫到的 inputConfig 留下。后挂图的异源选项不覆盖。
      return;
    }
    const labels: string[] = [];
    pushLabel(labels, param.dataSourceLabel);
    grouped.set(mergeKey, {
      key: param.name,
      type: param.type,
      componentCount: 1,
      sampleAlias: param.alias || param.name,
      sampleDefaultValue: param.defaultValue ?? null,
      sampleInputConfig: inputConfig,
      dataSourceLabels: labels,
      identity: optionsSourceIdentity(inputConfig),
      mergeKey,
      sourceHint: labels.join(' / ') || optionsSourceSummary(inputConfig),
    });
  });
  return Array.from(grouped.values());
};

export const assignFilterDefinitionIds = (
  groups: ScannedFilterGroup[],
  existing: ReusableFilterDefinition[] = [],
): AssignedFilterGroup[] => groups.map((group) => {
  const id = `${group.key}__${group.type}`;
  const stored = existing.find((item) => item.id === id)
    ?? existing.find((item) => item.key === group.key && item.type === group.type);
  return {
    ...group,
    id,
    suggestedName: group.sampleAlias,
    sampleInputConfig: stored?.inputConfig ?? group.sampleInputConfig,
  };
});

export const findReusableFilterDefinition = <T extends ReusableFilterDefinition>(
  existing: T[],
  scanned: { id: string; key: string; type: string; inputConfig?: InputControlConfig; inputMode?: string },
): T | undefined => {
  const byId = existing.find((item) => item.id === scanned.id);
  if (byId) return byId;
  const same = existing.filter((item) => item.key === scanned.key && item.type === scanned.type);
  if (same.length === 1 && scanned.id === `${scanned.key}__${scanned.type}`) return same[0];
  const scannedKey = optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(scanned)));
  return same.find((item) =>
    optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(item))) === scannedKey);
};

const sameNameDefinitions = <T extends { key: string; type: string }>(
  definitions: T[],
  param: { name: string; type?: string },
): T[] => definitions.filter((definition) =>
  definition.key === param.name && definition.type === param.type);

/**
 * 同名多条时只在能唯一对上时返回。
 * 先比完整 identity，再比选项宇宙（忽略 queryParams 写法）。并列则视为真歧义。
 */
interface MatchableFilterDefinition {
  id: string;
  key: string;
  type: string;
  inputConfig?: InputControlConfig;
  inputMode?: string;
}

export const pickMatchingFilterDefinition = <T extends MatchableFilterDefinition>(
  definitions: T[],
  param: Pick<ParamItem, 'name' | 'type' | 'inputConfig' | 'inputMode'>,
): T | undefined => {
  const same = sameNameDefinitions(definitions, param);
  if (same.length <= 1) return same[0];
  if (isBoardSharedFilterDimension(param) || same.every((item) => isBoardSharedFilterDimension(item))) {
    return same[0];
  }
  const paramKey = optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(param)));
  const exact = same.filter((definition) =>
    optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(definition))) === paramKey);
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) return undefined;
  const paramCore = optionsSourceCoreKey(normalizeInputConfig(param));
  const core = same.filter((definition) =>
    optionsSourceCoreKey(normalizeInputConfig(definition)) === paramCore);
  return core.length === 1 ? core[0] : undefined;
};

export const matchFilterDefinitionForParam = (
  definitions: UnifiedFilterDefinition[],
  param: Pick<ParamItem, 'name' | 'type' | 'inputConfig' | 'inputMode'>,
): UnifiedFilterDefinition | undefined => {
  const picked = pickMatchingFilterDefinition(definitions, param);
  if (picked) return picked;
  const same = sameNameDefinitions(definitions, param);
  if (same.length <= 1) return same[0];
  if (isBoardSharedFilterDimension(param) || same.every((item) => isBoardSharedFilterDimension(item))) {
    return same[0];
  }
  const paramKey = optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(param)));
  return same.find((definition) =>
    optionsSourceIdentityKey(optionsSourceIdentity(normalizeInputConfig(definition))) === paramKey);
};

const toScanInput = (
  param: ParamItem & { type: BindableDataSourceParamType },
  dataSourceLabel?: string,
): FilterParamScanInput => ({
  name: param.name,
  type: param.type,
  alias: param.alias_name || param.name,
  defaultValue: (param.value as FilterValue) ?? null,
  inputConfig: param.inputConfig,
  inputMode: param.inputMode,
  dataSourceLabel,
});

/** 主包与旧包各有一份 DatasourceItem，扫描只依赖这些字段。 */
export interface ScannableFilterDataSource {
  id: number;
  name?: string;
  rest_api?: string;
  params?: ReadonlyArray<{
    name: string;
    type?: string;
    alias_name?: string;
    value?: FilterValue | string | number | boolean | Array<string | number> | [number, number] | null;
    filterType?: string;
    inputMode?: string;
    inputConfig?: InputControlConfig | {
      control?: 'input' | 'select' | 'radio' | 'organization';
      multiple?: boolean;
    };
  }>;
}

export const scanDataSourceFilterParams = (
  layoutItems: Array<Pick<LayoutItem, 'valueConfig'>>,
  dataSources: ReadonlyArray<ScannableFilterDataSource>,
  existing: ReusableFilterDefinition[] = [],
): AssignedFilterGroup[] => {
  const usedDataSourceIds = new Set<number>();
  layoutItems.forEach((item) => {
    const dataSourceId = item.valueConfig?.dataSource;
    if (dataSourceId == null || dataSourceId === '') return;
    const normalized = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
    if (Number.isFinite(normalized)) usedDataSourceIds.add(normalized);
  });

  const inputs: FilterParamScanInput[] = [];
  dataSources.forEach((dataSource) => {
    if (!usedDataSourceIds.has(dataSource.id)) return;
    const params = migrateParamItemsFromStringList(
      (Array.isArray(dataSource.params) ? dataSource.params : []) as ParamItem[],
    ).params;
    params.forEach((param) => {
      if (param.filterType !== 'filter' || !isBindableDataSourceParamType(param.type)) return;
      inputs.push(toScanInput(
        param as ParamItem & { type: BindableDataSourceParamType },
        dataSource.name || dataSource.rest_api,
      ));
    });
  });
  return assignFilterDefinitionIds(groupFilterParams(inputs), existing);
};
