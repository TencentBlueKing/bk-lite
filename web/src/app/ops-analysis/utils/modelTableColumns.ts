import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import dayjs from 'dayjs';

export const INSTANCE_QUERY_API = 'cmdb/query_cmdb_instances';
export const ONE_HOP_QUERY_API = 'cmdb/query_cmdb_one_hop';

export interface ModelColumnOption {
  value: string;
  label: string;
}

export interface ModelColumnField {
  key: string;
  title: string;
  attr_type?: string;
  default_visible?: boolean;
  display_key?: string;
  display_format?: string;
  options?: ModelColumnOption[];
}

export interface ModelColumnPayload {
  source: 'model_attrs';
  model_key: string;
  fields: ModelColumnField[];
}

export interface ModelCellFormat {
  attrType?: string;
  displayKey?: string;
  displayFormat?: string;
  options?: ModelColumnOption[];
}

export type ModelAwareColumn<ColumnType extends TableColumnConfigItem = TableColumnConfigItem> =
  ColumnType & { modelFormat?: ModelCellFormat };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const isModelAttrTableSource = (restApi?: string): boolean =>
  restApi === INSTANCE_QUERY_API || restApi === ONE_HOP_QUERY_API;

export const modelTableBindingKey = (
  restApi: string | undefined,
  params: Record<string, unknown> | undefined,
): string => {
  if (restApi === INSTANCE_QUERY_API) {
    const modelId = String(params?.model_id || '').trim();
    return modelId ? `instance:${modelId}` : '';
  }
  if (restApi === ONE_HOP_QUERY_API) {
    const start = String(params?.start_model_id || '').trim();
    const association = String(params?.model_asst_id || '').trim();
    return start && association ? `onehop:${start}:${association}` : '';
  }
  return '';
};

export const readModelColumnPayload = (rawData: unknown): ModelColumnPayload | null => {
  if (!isRecord(rawData)) return null;
  const payload = rawData.column_fields;
  if (!isRecord(payload) || payload.source !== 'model_attrs' || !Array.isArray(payload.fields)) {
    return null;
  }
  const fields = payload.fields.filter((field): field is ModelColumnField => (
    isRecord(field) && typeof field.key === 'string' && field.key.trim() !== ''
  ));
  if (!fields.length) return null;
  return {
    source: 'model_attrs',
    model_key: String(payload.model_key || ''),
    fields,
  };
};

export const modelCellFormat = (field: ModelColumnField): ModelCellFormat => ({
  attrType: field.attr_type,
  displayKey: field.display_key,
  displayFormat: field.display_format,
  options: field.options,
});

export const columnsFromModelFields = <ColumnType extends TableColumnConfigItem>(
  fields: ModelColumnField[],
): ModelAwareColumn<ColumnType>[] =>
  fields.map((field, index) => ({
    key: field.key,
    title: field.title || field.key,
    visible: field.default_visible !== false,
    order: index,
    modelFormat: modelCellFormat(field),
  }) as ModelAwareColumn<ColumnType>);

export const reconcileSavedModelColumns = <ColumnType extends TableColumnConfigItem>(
  saved: ColumnType[],
  catalog: ModelAwareColumn<ColumnType>[],
): ModelAwareColumn<ColumnType>[] => {
  const byKey = new Map(catalog.map((column) => [column.key, column]));
  const kept = [...saved]
    .sort((left, right) => left.order - right.order)
    .flatMap((column) => {
      const fresh = byKey.get(column.key);
      if (!fresh) return [];
      return [{
        ...fresh,
        visible: column.visible !== false,
        width: column.width,
        columnType: column.columnType,
        cellType: column.cellType,
        valueMappings: column.valueMappings,
        cellThresholdColors: column.cellThresholdColors,
      }];
    })
    .map((column, index) => ({ ...column, order: index }));
  return kept.length ? kept : catalog;
};

interface ResolveModelColumnsInput<ColumnType extends TableColumnConfigItem> {
  configuredColumns?: ColumnType[];
  columnModelKey?: string;
  modelColumns: ModelColumnPayload;
}

export const resolveModelAttrColumns = <ColumnType extends TableColumnConfigItem>({
  configuredColumns = [],
  columnModelKey,
  modelColumns,
}: ResolveModelColumnsInput<ColumnType>): ModelAwareColumn<ColumnType>[] => {
  const catalog = columnsFromModelFields<ColumnType>(modelColumns.fields);
  const saved = configuredColumns.filter((column) => column.columnType !== 'actions' && column.key);
  if (!saved.length || columnModelKey !== modelColumns.model_key) {
    return catalog;
  }
  return reconcileSavedModelColumns(saved, catalog);
};

export const schemaFieldsForTable = (
  fields: ResponseFieldDefinition[] = [],
): ResponseFieldDefinition[] => fields.filter((field) => field.table !== false);

const formatEnumValue = (value: unknown, options: ModelColumnOption[] = []): string => {
  const list = Array.isArray(value) ? value : [value];
  const labels = list.flatMap((item) => {
    if (item === null || item === undefined || item === '') return [];
    const matched = options.find((option) => String(option.value) === String(item));
    return [matched ? matched.label : String(item)];
  });
  return labels.length ? labels.join(', ') : '--';
};

const formatOneTime = (value: unknown, displayFormat?: string): string => {
  if (value === null || value === undefined || value === '') return '--';
  const pattern = displayFormat === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss';
  const parsed = dayjs(value as dayjs.ConfigType);
  return parsed.isValid() ? parsed.format(pattern) : String(value);
};

const formatList = (value: unknown[]): string => {
  if (!value.length) return '--';
  const primitive = value.every((item) => (
    item === null || item === undefined || ['string', 'number', 'boolean'].includes(typeof item)
  ));
  if (primitive) {
    return value
      .map((item) => (item === null || item === undefined || item === '' ? '--' : String(item)))
      .join(', ');
  }
  try {
    return JSON.stringify(value);
  } catch {
    return '--';
  }
};

export const formatModelCell = (
  value: unknown,
  field: ModelCellFormat | undefined,
  row?: Record<string, unknown>,
): string => {
  const displayKey = field?.displayKey;
  if (displayKey && row && Object.prototype.hasOwnProperty.call(row, displayKey)) {
    const display = row[displayKey];
    if (typeof display === 'string' && display.trim()) return display;
  }
  if (value === null || value === undefined || value === '') return '--';
  const attrType = String(field?.attrType || '').toLowerCase();
  if (attrType === 'bool' || attrType === 'boolean') {
    return value === true || value === 1 || value === 'true' || value === '1' ? 'YES' : 'NO';
  }
  if (attrType === 'enum') return formatEnumValue(value, field?.options);
  if (attrType === 'time' || attrType === 'datetime') {
    if (Array.isArray(value)) {
      return value.map((item) => formatOneTime(item, field?.displayFormat)).join(' - ');
    }
    return formatOneTime(value, field?.displayFormat);
  }
  if (Array.isArray(value)) return formatList(value);
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '--';
    }
  }
  return String(value);
};

export const modelCellDisplayText = (
  raw: unknown,
  column: {
    modelFormat?: ModelCellFormat;
    valueMappings?: Parameters<typeof applyValueMapping>[1];
  },
  row?: Record<string, unknown>,
): string | null => {
  if (!column.modelFormat) return null;
  if (applyValueMapping(raw, column.valueMappings)?.text !== undefined) return null;
  return formatModelCell(raw, column.modelFormat, row);
};

export const modelTableEmptyText = (
  restApi: string | undefined,
  params: Record<string, unknown> | undefined,
  t: (key: string) => string,
): string | null => {
  if (restApi === INSTANCE_QUERY_API && !String(params?.model_id || '').trim()) {
    return t('dashboard.selectModel');
  }
  if (
    restApi === ONE_HOP_QUERY_API
    && (
      !String(params?.start_model_id || '').trim()
      || !String(params?.model_asst_id || '').trim()
    )
  ) {
    return t('dashboard.selectModelRelationFirst');
  }
  return null;
};
