import type { CardListConfig } from '@/app/ops-analysis/utils/cardList';
import type { InputControlConfig, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { isSceneWidgetType } from '@/app/ops-analysis/types/sceneWidgetCapability';
import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
  FilterValue,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { isDashboardGroupItem, isDashboardWidgetItem } from '@/app/ops-analysis/utils/dashboardGroups';
import { syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';

export const DASHBOARD_PROPOSAL_SCHEMA_VERSION = '1.0';

const FORMAT_VALUE_CONFIG_KEYS = [
  'unit',
  'unitId',
  'conversionFactor',
  'decimalPlaces',
  'valueMappings',
  'thresholdColors',
  'gaugeMin',
  'gaugeMax',
  'gaugeShape',
  'compare',
  'compareMode',
  'chartThemeMode',
  'appearance',
  'actions',
] as const;

export interface DashboardProposalWidget {
  i?: string;
  id?: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  name?: string;
  description?: string;
  valueConfig?: ValueConfig;
}

export interface DashboardProposalFilter {
  id?: string;
  key?: string;
  name?: string;
  type?: UnifiedFilterDefinition['type'];
  defaultValue?: FilterValue;
  order?: number;
  enabled?: boolean;
  inputMode?: UnifiedFilterDefinition['inputMode'];
  options?: UnifiedFilterDefinition['options'];
  inputConfig?: UnifiedFilterDefinition['inputConfig'];
}

export interface DashboardProposal {
  schemaVersion?: string;
  dashboardId?: string;
  layout?: DashboardProposalWidget[];
  filters?: DashboardProposalFilter[];
}

export interface ApplyDashboardProposalInput {
  layout: DashboardLayoutItem[];
  filters: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  proposal: DashboardProposal;
  allocateId: (preferred: string | undefined, used: Set<string>) => string;
}

export type ApplyDashboardProposalResult =
  | {
    ok: true;
    layout: DashboardLayoutItem[];
    filters: UnifiedFilterDefinition[];
    filterValues: Record<string, FilterValue>;
  }
  | {
    ok: false;
    reason: 'schema' | 'proposal';
  };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const stable = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stable(item)).join(',')}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value).sort().map((key) => `${key}:${stable(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value ?? null);
};

const hasOwn = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

const isSceneLayoutItem = (item: DashboardWidgetLayoutItem) =>
  isSceneWidgetType(item.valueConfig?.sceneWidgetType)
  || isSceneWidgetType(item.valueConfig?.chartType)
  || item.itemType === 'sceneWidget';

const isProposalSceneWidget = (item: DashboardProposalWidget) =>
  isSceneWidgetType(item.valueConfig?.sceneWidgetType)
  || isSceneWidgetType(item.valueConfig?.chartType);

const sorted = (values: string[]) => [...values].sort();

const columnKeys = (config: ValueConfig | undefined) =>
  sorted((config?.tableConfig?.columns || []).map((column) => column.key).filter(Boolean));

const cardListFields = (cardList: CardListConfig | undefined) => ({
  titleField: cardList?.titleField || '',
  descriptionField: cardList?.descriptionField || '',
  leadingField: cardList?.leading?.type === 'field' ? cardList.leading.field : '',
  leadingType: cardList?.leading?.type || '',
  badgeField: cardList?.badgeField || '',
  trailingPrimaryField: cardList?.trailingPrimaryField || '',
  trailingSecondaryField: cardList?.trailingSecondaryField || '',
});

const paramNames = (config: ValueConfig | undefined) =>
  sorted((config?.dataSourceParams || []).map((param) => param.name).filter(Boolean));

const bindingKeys = (config: ValueConfig | undefined) =>
  sorted(Object.entries(config?.filterBindings || {}).flatMap(([key, enabled]) => (enabled ? [key] : [])));

export const widgetContractDigest = (config: ValueConfig | undefined): string => stable({
  chartType: config?.chartType || '',
  dataSource: config?.dataSource == null ? '' : String(config.dataSource),
  selectedFields: sorted(config?.selectedFields || []),
  descriptionField: config?.descriptionField || '',
  topNLabelField: config?.topNLabelField || '',
  topNValueField: config?.topNValueField || '',
  dimensionField: config?.dimensionField || '',
  valueField: config?.valueField || '',
  multiValueLabelField: config?.multiValueLabelField || '',
  multiValueValueField: config?.multiValueValueField || '',
  nodeGraphIdentityMode: config?.nodeGraphIdentityMode || '',
  nodeGraphSourceField: config?.nodeGraphSourceField || '',
  nodeGraphTargetField: config?.nodeGraphTargetField || '',
  nodeGraphValueField: config?.nodeGraphValueField || '',
  nodeGraphTargetPortField: config?.nodeGraphTargetPortField || '',
  eventTimelineFields: {
    timeField: config?.eventTimeline?.timeField || '',
    titleField: config?.eventTimeline?.titleField || '',
    descriptionField: config?.eventTimeline?.descriptionField || '',
    categoryField: config?.eventTimeline?.categoryField || '',
    statusField: config?.eventTimeline?.statusField || '',
    linkField: config?.eventTimeline?.linkField || '',
  },
  radarFields: {
    indicators: sorted((config?.radar?.indicators || []).map((item) => item.key).filter(Boolean)),
    arrayNameField: config?.radar?.arrayNameField || '',
    arrayValueField: config?.radar?.arrayValueField || '',
  },
  columnKeys: columnKeys(config),
  cardListFields: cardListFields(config?.cardList),
  paramNames: paramNames(config),
  bindingKeys: bindingKeys(config),
});

const controlOf = (filter: { inputConfig?: InputControlConfig; inputMode?: string }) =>
  filter.inputConfig?.control || filter.inputMode || 'input';

const optionsSourceIdentity = (inputConfig: InputControlConfig | undefined) => {
  if (!inputConfig || inputConfig.control === 'input' || inputConfig.control === 'organization') {
    return null;
  }
  const source = inputConfig.optionsSource;
  if (!source || source.type !== 'dynamic') {
    return null;
  }
  return {
    type: 'dynamic' as const,
    sourceId: source.sourceId ?? null,
    sourceRef: source.sourceRef ?? null,
    valueField: source.valueField,
    labelField: source.labelField,
  };
};

export const filterContractDigest = (filter: {
  key?: string;
  name?: string;
  type?: string;
  defaultValue?: FilterValue;
  enabled?: boolean;
  inputMode?: string;
  inputConfig?: InputControlConfig;
}): string => stable({
  key: filter.key || '',
  name: filter.name || '',
  type: filter.type || '',
  defaultValue: filter.defaultValue ?? null,
  enabled: filter.enabled !== false,
  control: controlOf(filter),
  optionsSource: optionsSourceIdentity(filter.inputConfig),
});

const overlayParams = (stored: ParamItem[] | undefined, proposal: ParamItem[] | undefined): ParamItem[] => {
  const proposalByName = new Map((proposal || []).map((param) => [param.name, param]));
  return (stored || []).map((param) => {
    const next = proposalByName.get(param.name);
    if (!next) return param;
    return { ...param, ...next, name: param.name };
  });
};

const overlayColumns = (stored: ValueConfig, proposal: ValueConfig): ValueConfig['tableConfig'] => {
  if (!proposal.tableConfig) return stored.tableConfig;
  const storedColumns = stored.tableConfig?.columns || [];
  const proposalColumns = new Map((proposal.tableConfig.columns || []).map((column) => [column.key, column]));
  const columns = storedColumns.map((column) => {
    const next = proposalColumns.get(column.key);
    return next ? { ...column, ...next, key: column.key } : column;
  });
  return {
    ...stored.tableConfig,
    ...proposal.tableConfig,
    columns: proposal.tableConfig.columns ? columns : stored.tableConfig?.columns,
  };
};

const overlayValueConfig = (stored: ValueConfig, proposal: ValueConfig): ValueConfig => {
  const next: ValueConfig = { ...stored };
  FORMAT_VALUE_CONFIG_KEYS.forEach((key) => {
    if (hasOwn(proposal, key)) {
      (next as Record<string, unknown>)[key] = proposal[key];
    }
  });
  if (proposal.dataSourceParams) {
    next.dataSourceParams = overlayParams(stored.dataSourceParams, proposal.dataSourceParams);
  }
  if (proposal.tableConfig) {
    next.tableConfig = overlayColumns(stored, proposal);
  }
  if (proposal.eventTimeline) {
    next.eventTimeline = { ...stored.eventTimeline, ...proposal.eventTimeline };
  }
  if (proposal.radar) {
    next.radar = { ...stored.radar, ...proposal.radar, indicators: stored.radar?.indicators };
  }
  if (proposal.cardList) {
    next.cardList = { ...stored.cardList, ...proposal.cardList, titleField: stored.cardList?.titleField || proposal.cardList.titleField };
  }
  return next;
};

const readNumber = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : undefined);

const applyPosition = (
  item: DashboardWidgetLayoutItem,
  proposal: DashboardProposalWidget,
): DashboardWidgetLayoutItem => ({
  ...item,
  x: readNumber(proposal.x) ?? item.x,
  y: readNumber(proposal.y) ?? item.y,
  w: readNumber(proposal.w) ?? item.w,
  h: readNumber(proposal.h) ?? item.h,
  name: typeof proposal.name === 'string' ? proposal.name : item.name,
  description: hasOwn(proposal, 'description') ? proposal.description : item.description,
});

const toFilterDefinition = (
  proposal: DashboardProposalFilter,
  id: string,
  order: number,
): UnifiedFilterDefinition => ({
  id,
  key: proposal.key || '',
  name: proposal.name || proposal.key || '',
  type: proposal.type || 'string',
  defaultValue: proposal.defaultValue,
  order: readNumber(proposal.order) ?? order,
  enabled: proposal.enabled !== false,
  inputMode: proposal.inputMode,
  options: proposal.options,
  inputConfig: proposal.inputConfig,
});

const mergeFilters = (
  filters: UnifiedFilterDefinition[],
  proposalFilters: DashboardProposalFilter[] | undefined,
  usedIds: Set<string>,
  allocateId: ApplyDashboardProposalInput['allocateId'],
) => {
  const incoming = proposalFilters || [];
  const incomingById = new Map(incoming.flatMap((item) => (item.id ? [[item.id, item] as const] : [])));
  const kept: UnifiedFilterDefinition[] = [];
  filters.forEach((filter) => {
    const proposal = incomingById.get(filter.id);
    if (!proposal) return;
    if (filterContractDigest(filter) === filterContractDigest(proposal)) {
      kept.push({
        ...filter,
        order: readNumber(proposal.order) ?? filter.order,
        inputConfig: proposal.inputConfig ?? filter.inputConfig,
      });
      return;
    }
    kept.push(toFilterDefinition(proposal, filter.id, filter.order));
  });
  const keptIds = new Set(kept.map((filter) => filter.id));
  let nextOrder = kept.reduce((maxOrder, filter) => Math.max(maxOrder, filter.order), -1) + 1;
  incoming.forEach((proposal) => {
    if (proposal.id && keptIds.has(proposal.id)) return;
    const id = allocateId(proposal.id, usedIds);
    usedIds.add(id);
    kept.push(toFilterDefinition(proposal, id, nextOrder));
    nextOrder += 1;
  });
  return kept;
};

const defaultChanged = (previous: UnifiedFilterDefinition | undefined, next: UnifiedFilterDefinition) =>
  stable(previous?.defaultValue ?? null) !== stable(next.defaultValue ?? null);

const mergeFilterValues = (
  previousFilters: UnifiedFilterDefinition[],
  nextFilters: UnifiedFilterDefinition[],
  filterValues: Record<string, FilterValue>,
) => {
  const previousById = new Map(previousFilters.map((filter) => [filter.id, filter]));
  const seeded: Record<string, FilterValue> = {};
  nextFilters.forEach((filter) => {
    const previous = previousById.get(filter.id);
    if (!previous || defaultChanged(previous, filter)) {
      if (filter.defaultValue !== undefined && filter.defaultValue !== null) {
        seeded[filter.id] = filter.defaultValue;
      }
      return;
    }
    if (filterValues[filter.id] !== undefined) {
      seeded[filter.id] = filterValues[filter.id];
    }
  });
  return syncFilterValuesWithDefinitions(nextFilters, seeded);
};

const packProposalWidgets = (widgets: DashboardProposalWidget[]): DashboardProposalWidget[] => {
  const columns = 12;
  const cellW = 4;
  const allMissing = widgets.every((item) => readNumber(item.x) == null && readNumber(item.y) == null);
  if (!allMissing) return widgets;
  let x = 0;
  let y = 0;
  let rowH = 0;
  return widgets.map((item) => {
    const height = readNumber(item.h) ?? 3;
    if (x + cellW > columns) {
      x = 0;
      y += rowH;
      rowH = 0;
    }
    const next = { ...item, x, y, w: cellW, h: height };
    x += cellW;
    rowH = Math.max(rowH, height);
    return next;
  });
};

export const applyDashboardProposal = (
  input: ApplyDashboardProposalInput,
): ApplyDashboardProposalResult => {
  if (!isRecord(input.proposal) || !Array.isArray(input.proposal.layout)) {
    return { ok: false, reason: 'proposal' };
  }
  if (input.proposal.filters != null && !Array.isArray(input.proposal.filters)) {
    return { ok: false, reason: 'proposal' };
  }
  if (input.proposal.schemaVersion !== DASHBOARD_PROPOSAL_SCHEMA_VERSION) {
    return { ok: false, reason: 'schema' };
  }

  const proposalWidgets = packProposalWidgets(
    input.proposal.layout
      .filter((item) => !isProposalSceneWidget(item))
      .map((item) => ({ ...item, i: item.i || item.id })),
  );
  const proposalById = new Map(proposalWidgets.flatMap((item) => (item.i ? [[item.i, item] as const] : [])));
  const appliedIds = new Set<string>();
  const nextLayout: DashboardLayoutItem[] = [];

  input.layout.forEach((item) => {
    if (isDashboardGroupItem(item) || (isDashboardWidgetItem(item) && isSceneLayoutItem(item))) {
      nextLayout.push(item);
      return;
    }
    if (!isDashboardWidgetItem(item)) return;
    const proposal = proposalById.get(item.i);
    if (!proposal?.valueConfig) return;
    appliedIds.add(item.i);
    const sameContract = widgetContractDigest(item.valueConfig) === widgetContractDigest(proposal.valueConfig);
    nextLayout.push(applyPosition({
      ...item,
      valueConfig: sameContract
        ? overlayValueConfig(item.valueConfig || {}, proposal.valueConfig)
        : proposal.valueConfig,
    }, proposal));
  });

  const usedIds = new Set(nextLayout.map((item) => item.i));
  proposalWidgets.forEach((proposal) => {
    if (proposal.i && appliedIds.has(proposal.i)) return;
    if (!proposal.valueConfig?.chartType) return;
    const id = input.allocateId(proposal.i, usedIds);
    usedIds.add(id);
    const widget: DashboardWidgetLayoutItem = {
      i: id,
      x: readNumber(proposal.x) ?? 0,
      y: readNumber(proposal.y) ?? 0,
      w: readNumber(proposal.w) ?? 4,
      h: readNumber(proposal.h) ?? 3,
      groupId: null,
      name: proposal.name || proposal.valueConfig.chartType,
      description: proposal.description,
      valueConfig: proposal.valueConfig,
    };
    nextLayout.push(widget);
  });

  const filters = mergeFilters(
    input.filters,
    Array.isArray(input.proposal.filters) ? input.proposal.filters : [],
    usedIds,
    input.allocateId,
  );
  return {
    ok: true,
    layout: nextLayout,
    filters,
    filterValues: mergeFilterValues(input.filters, filters, input.filterValues),
  };
};

export const proposalTargetsDashboard = (dashboardId: unknown, currentId: string | number | undefined) => {
  if (dashboardId === 'current') return true;
  if (currentId == null || dashboardId == null) return false;
  return String(dashboardId) === String(currentId);
};
