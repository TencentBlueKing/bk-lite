'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Radio,
  Select,
  Switch,
  Table,
  Tooltip,
} from 'antd';
import { HolderOutlined, MinusOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type {
  DatasourceItem,
  DynamicOptionsSource,
  InputControlConfig,
  InputOption,
} from '@/app/ops-analysis/types/dataSource';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  extractDataSourceItems,
  resolveDynamicSourceId,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  isOptionsQueryParamRef,
  normalizeOptionsQueryParamValue,
  collectOptionsQueryParamIssues,
  hasOptionsQueryRef,
  isRejectedQueryParams,
  normalizeQueryParamsForStorage,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import {
  formatOptionsQueryCandidateLabel,
  canonicalizeOptionsQueryRef,
  listOptionsQueryCandidates,
  resolveOptionsQueryChoice,
  type OptionsQueryEditorContext,
} from '@/app/ops-analysis/utils/optionsQueryCandidates';
import { useTranslation } from '@/utils/i18n';

interface StaticRow extends InputOption {
  uid: string;
}

interface QueryParamRow {
  uid: string;
  name: string;
  alias?: string;
  type?: string;
  mode: 'literal' | 'ref';
  literalText: string;
  literalRaw?: string | number | boolean | null;
  refName: string;
}

interface ParamInputConfigEditorProps {
  open: boolean;
  value?: InputControlConfig;
  onConfirm: (value: InputControlConfig, resolvedOptions?: InputOption[]) => void;
  onCancel: () => void;
  excludeSourceIds?: number[];
  componentSwitchEnabled?: boolean;
  componentSwitchOwner?: { name: string; label: string };
  editingParamName?: string;
  /** 同名多行时，正在编辑的筛选 id。校验图用它做节点名。 */
  editingNodeId?: string;
  optionsQueryContext?: OptionsQueryEditorContext;
}

interface SortableStaticRowProps {
  row: StaticRow;
  onChange: (uid: string, field: 'label' | 'value', value: string) => void;
  onAddAfter: (uid: string) => void;
  onRemove: (uid: string) => void;
  showRemove: boolean;
  valuePlaceholder: string;
  labelPlaceholder: string;
}

const newId = () => Math.random().toString(36).slice(2);
const createRow = (): StaticRow => ({ uid: newId(), label: '', value: '' });
const queryRowFromStored = (name: string, raw: unknown): QueryParamRow => {
  const normalized = normalizeOptionsQueryParamValue(raw);
  if (normalized.ok && isOptionsQueryParamRef(normalized.value)) {
    return {
      uid: newId(),
      name,
      mode: 'ref',
      literalText: '',
      refName: normalized.value.ref,
    };
  }
  const literal = normalized.ok ? normalized.value : '';
  return {
    uid: newId(),
    name,
    mode: 'literal',
    literalText: literal == null ? '' : String(literal),
    literalRaw: normalized.ok && !isOptionsQueryParamRef(normalized.value) ? normalized.value : undefined,
    refName: '',
  };
};

/** 只预填可保存的字面量。数组和日期范围不是查询入参字面量，留空让用户另填。 */
const declaredParamLiteral = (
  value: unknown,
): { literalText: string; literalRaw?: string | number | boolean } => {
  if (typeof value === 'number' || typeof value === 'boolean') {
    return { literalText: String(value), literalRaw: value };
  }
  if (typeof value === 'string' && value !== '') {
    return { literalText: value, literalRaw: value };
  }
  return { literalText: '' };
};

const rowLiteralPayload = (row: QueryParamRow): string | number | boolean | null | undefined => {
  if (row.literalText === '' && row.literalRaw === undefined) return undefined;
  if (row.literalRaw !== undefined && String(row.literalRaw ?? '') === row.literalText) {
    return row.literalRaw;
  }
  return row.literalText;
};

const queryParamAliasText = (alias?: string) => alias?.trim() || '—';

interface FieldOption {
  label: string;
  value: string;
}

const DynamicFieldSelect: React.FC<{
  id?: string;
  value?: string;
  onChange?: (value: string) => void;
  options: FieldOption[];
  allowCustom: boolean;
  placeholder: string;
}> = ({
  value,
  onChange,
  options,
  allowCustom,
  placeholder,
  ...rest
}) => {
  const [search, setSearch] = useState('');
  const typed = search.trim();
  const selectOptions = allowCustom && typed && !options.some((item) => item.value === typed)
    ? [{ label: typed, value: typed }, ...options]
    : options;

  return (
    <Select
      {...rest}
      showSearch={allowCustom}
      value={value}
      placeholder={placeholder}
      options={selectOptions}
      optionFilterProp="label"
      filterOption={allowCustom
        ? (input, option) => {
          const needle = input.trim().toLowerCase();
          if (!needle) return true;
          const label = String(option?.label ?? '').toLowerCase();
          const optionValue = String(option?.value ?? '').toLowerCase();
          return label.includes(needle) || optionValue.includes(needle);
        }
        : undefined}
      onSearch={allowCustom ? setSearch : undefined}
      onInputKeyDown={(event) => {
        if (!allowCustom || event.key !== 'Enter') return;
        const typedValue = search.trim();
        if (!typedValue) return;
        event.preventDefault();
        setSearch('');
        onChange?.(typedValue);
      }}
      onChange={(next: string) => {
        setSearch('');
        onChange?.(next);
      }}
    />
  );
};

const TECHNICAL_QUERY_NODE_ID = /__(?:string|number|boolean|timeRange|dateRange|organization)(?:__[0-9a-z]+)?$/i;

/** 引用下拉弹出层高度。选项多时在层内滚动，不把表单撑高。 */
const OPTIONS_QUERY_REF_LIST_HEIGHT = 256;

const readableQueryToken = (token: string, labels?: ReadonlyMap<string, string>) => {
  const named = labels?.get(token)?.trim();
  if (named) return named;
  return token.replace(TECHNICAL_QUERY_NODE_ID, '') || token;
};

const readableQueryPath = (path: string[] | undefined, labels?: ReadonlyMap<string, string>) => (
  (path || []).map((token) => readableQueryToken(token, labels)).join(' → ')
);

/** 校验提示用显示名。没有显示名时去掉 `__string` 和摘要 id，避免把内部 id 链直接给用户。 */
export const optionsQueryIssueLabels = (
  context?: OptionsQueryEditorContext,
): Map<string, string> => {
  const labels = new Map<string, string>();
  const put = (id?: string, label?: string) => {
    const text = label?.trim();
    if (!id || !text) return;
    labels.set(id, text);
  };
  (context?.componentParams ?? []).forEach((param) => put(param.name, param.label));
  const filters = context?.globalFilters ?? [];
  filters.forEach((filter) => put(filter.id, filter.label));
  const namesByKey = new Map<string, Set<string>>();
  filters.forEach((filter) => {
    const text = filter.label?.trim();
    if (!filter.key || !text) return;
    const names = namesByKey.get(filter.key) ?? new Set<string>();
    names.add(text);
    namesByKey.set(filter.key, names);
  });
  namesByKey.forEach((names, key) => {
    if (names.size === 1) put(key, [...names][0]);
  });
  put(context?.self.id, context?.self.label);
  put(context?.self.key, context?.self.label);
  return labels;
};

export const describeQueryIssue = (
  t: (key: string, _default?: string, values?: Record<string, string>) => string,
  issue: { code: string; param?: string; name?: string; ref?: string; path?: string[] },
  labels?: ReadonlyMap<string, string>,
) => {
  const ref = readableQueryToken(issue.ref || '', labels);
  const path = readableQueryPath(issue.path, labels);
  if (issue.code === 'concat') return t('paramInput.dynamic.concatRejected');
  if (issue.code === 'self') return t('paramInput.dynamic.selfRef');
  if (issue.code === 'missing') {
    return t('paramInput.dynamic.missingRef', undefined, { ref });
  }
  if (issue.code === 'type') {
    return t('paramInput.dynamic.unbindableRef', undefined, { ref });
  }
  if (issue.code === 'ambiguous') return t('paramInput.dynamic.ambiguousRef');
  if (issue.code === 'cycle') return t('paramInput.dynamic.cycle', undefined, { path });
  if (issue.code === 'depth') return t('paramInput.dynamic.depth', undefined, { path });
  return t('paramInput.dynamic.invalidValue');
};
const SortableStaticRow: React.FC<SortableStaticRowProps> = ({
  row,
  onChange,
  onAddAfter,
  onRemove,
  showRemove,
  valuePlaceholder,
  labelPlaceholder,
}) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: row.uid });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li ref={setNodeRef} style={style} className="mb-2 flex items-center">
      <HolderOutlined
        {...attributes}
        {...listeners}
        className="mr-[4px] cursor-grab text-[var(--color-text-3)]"
      />
      <Input
        className="mr-[10px] w-2/5"
        value={String(row.value)}
        placeholder={valuePlaceholder}
        onChange={(event) => onChange(row.uid, 'value', event.target.value)}
      />
      <Input
        className="mr-[10px] w-2/5"
        value={row.label}
        placeholder={labelPlaceholder}
        onChange={(event) => onChange(row.uid, 'label', event.target.value)}
      />
      <PlusOutlined
        className="mr-[10px] cursor-pointer text-[var(--color-primary)]"
        onClick={() => onAddAfter(row.uid)}
      />
      {showRemove && (
        <MinusOutlined
          className="cursor-pointer text-[var(--color-primary)]"
          onClick={() => onRemove(row.uid)}
        />
      )}
    </li>
  );
};

export const ParamInputConfigEditor: React.FC<ParamInputConfigEditorProps> = ({
  open,
  value,
  onConfirm,
  onCancel,
  excludeSourceIds = [],
  componentSwitchEnabled = false,
  componentSwitchOwner,
  editingParamName,
  editingNodeId,
  optionsQueryContext,
}) => {
  const { t } = useTranslation();
  const { getDataSourceList, getSourceDataByApiId } = useDataSourceApi();
  const [form] = Form.useForm();
  const [control, setControl] = useState<InputControlConfig['control']>('input');
  const [picker, setPicker] = useState<'dropdown' | 'table'>('dropdown');
  const [componentSwitch, setComponentSwitch] = useState(false);
  const [multiple, setMultiple] = useState(false);
  const isOptionsControl = control === 'select' || control === 'radio';
  const [sourceType, setSourceType] = useState<'static' | 'dynamic'>('static');
  const [staticRows, setStaticRows] = useState<StaticRow[]>([createRow()]);
  const [dataSourceList, setDataSourceList] = useState<DatasourceItem[]>([]);
  const [dsLoading, setDsLoading] = useState(false);
  const [dynamicSourceId, setDynamicSourceId] = useState<number | undefined>();
  const [dynamicValueField, setDynamicValueField] = useState<string | undefined>();
  const [dynamicLabelField, setDynamicLabelField] = useState<string | undefined>();
  const [dynamicPreview, setDynamicPreview] = useState<Record<string, unknown>[]>([]);
  const [previewFieldKeys, setPreviewFieldKeys] = useState<string[]>([]);
  const [dynamicPreviewLoading, setDynamicPreviewLoading] = useState(false);
  const [queryParamRows, setQueryParamRows] = useState<QueryParamRow[]>([]);
  const previewRequestIdRef = useRef(0);
  const staticSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  useEffect(() => {
    if (!open) return;
    if (!value) {
      setControl('input');
      setPicker('dropdown');
      setComponentSwitch(false);
      setMultiple(false);
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      setPreviewFieldKeys([]);
      setQueryParamRows([]);
      form.resetFields(['dynamicSourceId', 'dynamicValueField', 'dynamicLabelField']);
      return;
    }

    setControl(value.control);
    setPicker(value.control === 'select' && value.picker === 'table' ? 'table' : 'dropdown');
    setComponentSwitch(
      (value.control === 'select' || value.control === 'radio')
        && Boolean(value.componentSwitch)
        && hasOptionsQueryRef(value) === false,
    );
    setMultiple(
      value.control === 'select' ? Boolean(value.multiple) : false,
    );
    if (value.control === 'input' || value.control === 'organization') {
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      setPreviewFieldKeys([]);
      setQueryParamRows([]);
      form.resetFields(['dynamicSourceId', 'dynamicValueField', 'dynamicLabelField']);
      return;
    }

    if (value.optionsSource.type === 'static') {
      setSourceType('static');
      setStaticRows(
        value.optionsSource.staticItems.length > 0
          ? value.optionsSource.staticItems.map((item) => ({ ...item, uid: newId() }))
          : [createRow()],
      );
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      setPreviewFieldKeys([]);
      setQueryParamRows([]);
      form.resetFields(['dynamicSourceId', 'dynamicValueField', 'dynamicLabelField']);
      return;
    }

    const initialSourceId = value.optionsSource.sourceRef
      ? undefined
      : value.optionsSource.sourceId;
    setSourceType('dynamic');
    setDynamicSourceId(initialSourceId);
    setDynamicValueField(value.optionsSource.valueField);
    setDynamicLabelField(value.optionsSource.labelField);
    setQueryParamRows(
      Object.entries(value.optionsSource.queryParams ?? {}).map(([name, raw]) => queryRowFromStored(name, raw)),
    );
    setDynamicPreview([]);
    setPreviewFieldKeys([]);
    form.setFieldsValue({
      dynamicSourceId: initialSourceId,
      dynamicValueField: value.optionsSource.valueField,
      dynamicLabelField: value.optionsSource.labelField,
    });
  }, [form, open, value]);

  const filteredDataSourceList = useMemo(() => {
    if (excludeSourceIds.length === 0) return dataSourceList;
    return dataSourceList.filter((item) => !excludeSourceIds.includes(item.id));
  }, [dataSourceList, excludeSourceIds]);

  const selectedDataSource = useMemo(
    () => dataSourceList.find((item) => item.id === dynamicSourceId),
    [dataSourceList, dynamicSourceId],
  );

  useEffect(() => {
    if (!open || sourceType !== 'dynamic' || !selectedDataSource) return;
    if (!Array.isArray(selectedDataSource.params)) return;
    const declared = selectedDataSource.params.filter((param) => param.name);
    setQueryParamRows((prev) => declared.map((param) => {
      const existing = prev.find((row) => row.name === param.name);
      if (existing) {
        return { ...existing, alias: param.alias_name, type: param.type };
      }
      const literal = declaredParamLiteral(param.value);
      return {
        uid: newId(),
        name: param.name,
        alias: param.alias_name,
        type: param.type,
        mode: 'literal' as const,
        literalText: literal.literalText,
        literalRaw: literal.literalRaw,
        refName: '',
      };
    }));
  }, [open, selectedDataSource, sourceType]);

  const hasFieldSchema = (selectedDataSource?.field_schema?.length ?? 0) > 0;

  const availableFields = useMemo(() => {
    const options: FieldOption[] = [];
    const seen = new Set<string>();
    const push = (fieldValue: string, label: string) => {
      if (!fieldValue || seen.has(fieldValue)) return;
      seen.add(fieldValue);
      options.push({ label, value: fieldValue });
    };
    (selectedDataSource?.field_schema || []).forEach((field) => {
      push(field.key, field.title ? `${field.title}（${field.key}）` : field.key);
    });
    previewFieldKeys.forEach((key) => push(key, key));
    if (dynamicValueField) push(dynamicValueField, dynamicValueField);
    if (dynamicLabelField) push(dynamicLabelField, dynamicLabelField);
    return options;
  }, [dynamicLabelField, dynamicValueField, previewFieldKeys, selectedDataSource?.field_schema]);

  const dynamicPreviewColumns = useMemo(() => {
    const first = dynamicPreview[0];
    const fieldKeys = first
      ? Object.keys(first)
      : (selectedDataSource?.field_schema || []).map((field) => field.key);
    const uniqueFieldKeys = Array.from(new Set(fieldKeys));

    return uniqueFieldKeys.map((fieldKey) => ({
      title:
        availableFields.find((field) => field.value === fieldKey)?.label ||
        fieldKey,
      dataIndex: fieldKey,
      key: fieldKey,
      width: 160,
      ellipsis: true,
      render: (text: unknown) => String(text ?? ''),
    }));
  }, [availableFields, dynamicPreview, selectedDataSource?.field_schema]);

  const staticRowIds = useMemo(
    () => staticRows.map((row) => row.uid),
    [staticRows],
  );

  useEffect(() => {
    if (!open || sourceType !== 'dynamic' || !isOptionsControl) return;
    setDsLoading(true);
    getDataSourceList({ page_size: -1 })
      .then((response) => {
        const items = Array.isArray(response) ? response : response?.items || [];
        setDataSourceList(items as DatasourceItem[]);
      })
      .catch((error: Error) => {
        message.error(error.message || t('paramInput.dynamic.loadDataSourceFailed'));
      })
      .finally(() => setDsLoading(false));
  }, [control, getDataSourceList, open, sourceType, t]);

  useEffect(() => {
    if (
      !open ||
      control === 'input' ||
      control === 'organization' ||
      sourceType !== 'dynamic' ||
      dynamicSourceId ||
      !value ||
      value.control === 'input' ||
      value.control === 'organization' ||
      value.optionsSource.type !== 'dynamic' ||
      !value.optionsSource.sourceRef ||
      dataSourceList.length === 0
    ) {
      return;
    }

    const resolvedSourceId = resolveDynamicSourceId(
      value.optionsSource,
      dataSourceList,
    );
    if (resolvedSourceId) {
      setDynamicSourceId(resolvedSourceId);
      form.setFieldValue('dynamicSourceId', resolvedSourceId);
    }
  }, [control, dataSourceList, dynamicSourceId, form, open, sourceType, value]);

  const fetchDynamicPreview = useCallback((sourceId: number, params: Record<string, unknown> = {}) => {
    const requestId = ++previewRequestIdRef.current;
    setDynamicPreviewLoading(true);
    return getSourceDataByApiId(sourceId, params)
      .then(({ data }) => {
        if (requestId !== previewRequestIdRef.current) return;
        const items = extractDataSourceItems(data).slice(0, 5);
        setDynamicPreview(extractDataSourceItems(data).slice(0, 5));
        setPreviewFieldKeys((prev) => {
          const next = new Set(prev);
          items.forEach((item) => {
            if (!item || typeof item !== 'object' || Array.isArray(item)) return;
            Object.keys(item).forEach((key) => next.add(key));
          });
          return Array.from(next);
        });
      })
      .catch((error: any) => {
        if (requestId !== previewRequestIdRef.current) return;
        // 失败只收起样本。已选字段和已发现列名保留。
        setDynamicPreview([]);
        message.error(
          error?.response?.data?.message ||
          error?.message ||
          t('paramInput.dynamic.testFailed'),
        );
      })
      .finally(() => {
        if (requestId === previewRequestIdRef.current) setDynamicPreviewLoading(false);
      });
  }, [getSourceDataByApiId, t]);

  useEffect(() => {
    if (!open || !isOptionsControl || sourceType !== 'dynamic' || !dynamicSourceId) {
      return;
    }
    if (!selectedDataSource || selectedDataSource.id !== dynamicSourceId) return;
    const hasDeclaredParams = Array.isArray(selectedDataSource.params)
      && selectedDataSource.params.some((param) => Boolean(param.name));
    
    if (!hasDeclaredParams) {
      void fetchDynamicPreview(dynamicSourceId);
      return;
    }

    if (queryParamRows.length === 0) return;

    const allLiteral = queryParamRows.every((row) => row.mode === 'literal');
    const allFilledLiterals = queryParamRows.every((row) => {
      if (row.mode !== 'literal') return false;
      const literal = rowLiteralPayload(row);
      return literal !== undefined && literal !== null && literal !== '';
    });

    if (allLiteral && allFilledLiterals) {
      const params: Record<string, unknown> = {};
      queryParamRows.forEach((row) => {
        const name = row.name.trim();
        if (!name) return;
        const literal = rowLiteralPayload(row);
        if (literal !== undefined && literal !== null && literal !== '') {
          params[name] = literal;
        }
      });
      void fetchDynamicPreview(dynamicSourceId, params);
    }
  }, [dynamicSourceId, fetchDynamicPreview, isOptionsControl, open, queryParamRows, selectedDataSource, sourceType]);

  const handleStaticChange = (
    uid: string,
    field: 'label' | 'value',
    nextValue: string,
  ) => {
    setStaticRows((prev) =>
      prev.map((row) =>
        row.uid === uid
          ? {
            ...row,
            [field]: nextValue,
          }
          : row,
      ),
    );
  };

  const handleAddStaticRowAfter = (uid: string) => {
    setStaticRows((prev) => {
      const index = prev.findIndex((row) => row.uid === uid);
      const next = [...prev];
      next.splice(index + 1, 0, createRow());
      return next;
    });
  };

  const handleRemoveStaticRow = (uid: string) => {
    setStaticRows((prev) => (prev.length <= 1 ? prev : prev.filter((row) => row.uid !== uid)));
  };

  const handleStaticDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    setStaticRows((prev) => {
      const oldIndex = prev.findIndex((row) => row.uid === active.id);
      const newIndex = prev.findIndex((row) => row.uid === over.id);
      return arrayMove(prev, oldIndex, newIndex);
    });
  };

  const buildOptionControlExtras = (): Pick<
    Extract<InputControlConfig, { control: 'select' | 'radio' }>,
    'multiple' | 'maxCount' | 'picker'
  > => {
    const current = value && (value.control === 'select' || value.control === 'radio')
      ? value
      : undefined;
    return {
      ...(control === 'select' && multiple
        ? { multiple: true as const, maxCount: current?.maxCount }
        : {}),
      ...(control === 'select' && picker === 'table' ? { picker: 'table' as const } : {}),
    };
  };

  const queryRefDisablesSwitch = queryParamRows.some((row) => row.mode === 'ref' && row.refName.trim());

  const handleConfirm = async () => {
    if (control === 'input') {
      onConfirm({ control: 'input' });
      return;
    }
    if (control === 'organization') {
      onConfirm({ control: 'organization' });
      return;
    }

    if (sourceType === 'static') {
      const staticItems = staticRows
        .filter((row) => String(row.value).trim() !== '' && row.label.trim() !== '')
        .map(({ label, value }) => ({ label: label.trim(), value }));

      if (staticItems.length === 0) {
        message.warning(t('paramInput.static.emptyError'));
        return;
      }

      const values = new Set(staticItems.map((item) => String(item.value)));
      if (values.size !== staticItems.length) {
        message.warning(t('paramInput.static.duplicateValueError'));
        return;
      }

      onConfirm(
        {
          control,
          componentSwitch: componentSwitch ? true : undefined,
          ...buildOptionControlExtras(),
          optionsSource: {
            type: 'static',
            staticItems,
          },
        },
        staticItems,
      );
      return;
    }

    let dynamicValues: {
      dynamicSourceId: number;
      dynamicValueField: string;
      dynamicLabelField: string;
    };
    try {
      dynamicValues = await form.validateFields([
        'dynamicSourceId',
        'dynamicValueField',
        'dynamicLabelField',
      ]);
    } catch {
      return;
    }

    const selectedSource = dataSourceList.find(
      (item) => item.id === dynamicValues.dynamicSourceId,
    );
    const sourceRef = selectedSource?.rest_api
      ? { type: 'rest_api' as const, value: selectedSource.rest_api }
      : undefined;
    if (queryParamRows.some((row) => row.name.trim() && row.mode === 'ref' && !row.refName.trim())) {
      message.error(t('paramInput.dynamic.refRequired'));
      return;
    }
    const draftParams: Record<string, unknown> = {};
    queryParamRows.forEach((row) => {
      const name = row.name.trim();
      if (!name) return;
      if (row.mode === 'ref') {
        draftParams[name] = {
          ref: canonicalizeOptionsQueryRef(row.refName.trim(), optionsQueryContext),
        };
        return;
      }
      const literal = rowLiteralPayload(row);
      if (literal === undefined) return;
      draftParams[name] = literal;
    });
    const storedParams = normalizeQueryParamsForStorage(draftParams);
    const scope = optionsQueryContext?.scope ?? 'component';
    const paramName = editingParamName || optionsQueryContext?.self.key || 'current';
    const nodeName = scope === 'globalFilter'
      ? (optionsQueryContext?.self.id || editingNodeId || paramName)
      : (editingParamName || optionsQueryContext?.self.key || 'current');
    const selfAlias = scope === 'globalFilter' ? (optionsQueryContext?.self.key || paramName) : undefined;
    const otherFilters = (optionsQueryContext?.globalFilters ?? []).filter((filter) => (
      filter.id && filter.id !== nodeName && filter.id !== optionsQueryContext?.self.id
    ));
    const otherParams = scope === 'component'
      ? (optionsQueryContext?.componentParams ?? []).filter((param) => param.name && param.name !== nodeName)
      : [];
    // 本卡组件参名含正在编辑的 self。这些 key 不再作全局筛别名，避免 self 与筛别名被看成两条。
    const componentParamNames = new Set<string>();
    if (scope === 'component') {
      (optionsQueryContext?.componentParams ?? []).forEach((param) => {
        if (param.name) componentParamNames.add(param.name);
      });
      if (nodeName) componentParamNames.add(nodeName);
      if (optionsQueryContext?.self.key) componentParamNames.add(optionsQueryContext.self.key);
    }
    const issues = collectOptionsQueryParamIssues(
      [
        ...otherFilters.map((filter) => ({
          name: filter.id,
          aliases: filter.key && filter.key !== filter.id && !componentParamNames.has(filter.key)
            ? [filter.key]
            : undefined,
          queryParams: filter.queryParams,
        })),
        ...otherParams.map((param) => ({
          name: param.name,
          queryParams: param.queryParams,
        })),
        {
          name: nodeName,
          aliases: selfAlias && selfAlias !== nodeName ? [selfAlias] : undefined,
          queryParams: draftParams,
        },
      ],
      [
        { name: nodeName },
        ...(selfAlias && selfAlias !== nodeName ? [{ name: selfAlias }] : []),
        ...otherFilters.flatMap((filter) => [
          { name: filter.id, type: filter.type },
          ...(filter.key ? [{ name: filter.key, type: filter.type }] : []),
        ]),
        ...otherParams.map((param) => ({ name: param.name, type: param.type })),
      ],
    );
    if (issues.length > 0 || isRejectedQueryParams(storedParams)) {
      const labels = optionsQueryIssueLabels(optionsQueryContext);
      const parts = issues.map((issue) => describeQueryIssue(t, issue, labels));
      if (isRejectedQueryParams(storedParams)) {
        const storedText = describeQueryIssue(t, storedParams.issue, labels);
        if (!parts.includes(storedText)) parts.unshift(storedText);
      }
      message.error(parts.join('；'));
      return;
    }

    const optionsSource: DynamicOptionsSource = {
      type: 'dynamic',
      ...(sourceRef
        ? { sourceRef }
        : { sourceId: dynamicValues.dynamicSourceId }),
      valueField: dynamicValues.dynamicValueField,
      labelField: dynamicValues.dynamicLabelField,
      ...(storedParams.queryParams ? { queryParams: storedParams.queryParams } : {}),
    };

    onConfirm({
      control,
      componentSwitch: queryRefDisablesSwitch ? undefined : (componentSwitch ? true : undefined),
      ...buildOptionControlExtras(),
      optionsSource,
    });
  };

  const hasRefQueryParam = queryParamRows.some((row) => row.mode === 'ref');

  return (
    <Modal
      title={t('paramInput.title')}
      open={open}
      onCancel={onCancel}
      onOk={handleConfirm}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={640}
      centered
      destroyOnHidden
      styles={{
        body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' },
      }}
    >
      <Form form={form} layout="vertical" colon={false}>
        <Form.Item label={t('paramInput.controlType')} className="mb-3">
          <Radio.Group
            value={control}
            onChange={(event) => {
              const nextControl = event.target.value as InputControlConfig['control'];
              setControl(nextControl);
              if (nextControl !== 'select') {
                setPicker('dropdown');
              }
              if (nextControl === 'input' || nextControl === 'organization') {
                setComponentSwitch(false);
                setDynamicSourceId(undefined);
                setDynamicValueField(undefined);
                setDynamicLabelField(undefined);
                setDynamicPreview([]);
                setPreviewFieldKeys([]);
                form.resetFields(['dynamicSourceId', 'dynamicValueField', 'dynamicLabelField']);
              }
            }}
            options={[
              { label: t('paramInput.control.input'), value: 'input' },
              { label: t('paramInput.control.select'), value: 'select' },
              { label: t('paramInput.control.radio'), value: 'radio' },
              { label: t('paramInput.control.organization'), value: 'organization' },
            ]}
          />
        </Form.Item>

        {control === 'select' && (
          <Form.Item label={t('paramInput.picker')} className="mb-3">
            <Radio.Group
              value={picker}
              onChange={(event) => setPicker(event.target.value)}
              options={[
                { label: t('paramInput.pickerDropdown'), value: 'dropdown' },
                { label: t('paramInput.pickerTable'), value: 'table' },
              ]}
            />
          </Form.Item>
        )}

        {control === 'select' && (
          <Form.Item label={t('paramInput.multiple')} className="mb-3">
            <Tooltip
              title={
                componentSwitch
                  ? t('paramInput.multipleDisabledByComponentSwitch')
                  : undefined
              }
            >
              <Switch
                size="small"
                checked={multiple}
                disabled={componentSwitch}
                onChange={(checked) => {
                  setMultiple(checked);
                  if (checked) {
                    setComponentSwitch(false);
                  }
                }}
              />
            </Tooltip>
          </Form.Item>
        )}

        {isOptionsControl && (
          <>
            {componentSwitchEnabled && (
              <Form.Item
                label={t('dashboard.componentSwitch')}
                className="mb-3"
              >
                <Tooltip
                  title={
                    componentSwitchOwner &&
                      componentSwitchOwner.name !== editingParamName
                      ? t('dashboard.componentSwitchOccupied', undefined, {
                        label: componentSwitchOwner.label,
                      })
                      : multiple
                        ? t('dashboard.componentSwitchDisabledByMultiple')
                        : queryRefDisablesSwitch
                          ? t('dashboard.componentSwitchDisabledByQueryRef')
                          : undefined
                  }
                >
                  <Switch
                    size='small'
                    checked={componentSwitch && queryRefDisablesSwitch === false}
                    disabled={Boolean(
                      (componentSwitchOwner &&
                        componentSwitchOwner.name !== editingParamName) ||
                      multiple ||
                      queryRefDisablesSwitch,
                    )}
                    onChange={(checked) => {
                      setComponentSwitch(checked);
                      if (checked) {
                        setMultiple(false);
                      }
                    }}
                  />
                </Tooltip>
              </Form.Item>
            )}
            <Form.Item label={t('paramInput.sourceType')} className="mb-3">
              <Radio.Group
                value={sourceType}
                onChange={(event) => {
                  setSourceType(event.target.value);
                  setDynamicSourceId(undefined);
                  setDynamicValueField(undefined);
                  setDynamicLabelField(undefined);
                  setDynamicPreview([]);
                  setPreviewFieldKeys([]);
                  form.resetFields(['dynamicSourceId', 'dynamicValueField', 'dynamicLabelField']);
                }}
                options={[
                  { label: t('paramInput.source.static'), value: 'static' },
                  { label: t('paramInput.source.dynamic'), value: 'dynamic' },
                ]}
              />
            </Form.Item>

            {sourceType === 'static' ? (
              <Form.Item label={t('paramInput.static.options')} className="mb-2">
                <DndContext
                  sensors={staticSensors}
                  collisionDetection={closestCenter}
                  onDragEnd={handleStaticDragEnd}
                >
                  <SortableContext
                    items={staticRowIds}
                    strategy={verticalListSortingStrategy}
                  >
                    <ul className="pt-1">
                      {staticRows.map((row) => (
                        <SortableStaticRow
                          key={row.uid}
                          row={row}
                          onChange={handleStaticChange}
                          onAddAfter={handleAddStaticRowAfter}
                          onRemove={handleRemoveStaticRow}
                          showRemove={staticRows.length > 1}
                          valuePlaceholder={t('paramInput.static.value')}
                          labelPlaceholder={t('paramInput.static.label')}
                        />
                      ))}
                    </ul>
                  </SortableContext>
                </DndContext>
              </Form.Item>
            ) : (
              <>
                <div className="mb-3 flex items-start gap-0">
                  <Form.Item
                    name="dynamicSourceId"
                    label={t('paramInput.dynamic.source')}
                    className="mb-0 flex-1"
                    rules={[
                      {
                        required: true,
                        message: t('paramInput.dynamic.sourcePlaceholder'),
                      },
                    ]}
                  >
                    <Select
                      showSearch
                      loading={dsLoading}
                      value={dynamicSourceId}
                      placeholder={t('paramInput.dynamic.sourcePlaceholder')}
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      options={filteredDataSourceList.map((item) => ({
                        value: item.id,
                        label: `${item.name}${item.rest_api ? `（${item.rest_api}）` : ''}`,
                      }))}
                      onChange={(sourceId) => {
                        previewRequestIdRef.current += 1;
                        setDynamicSourceId(sourceId);
                        setDynamicValueField(undefined);
                        setDynamicLabelField(undefined);
                        setDynamicPreview([]);
                        setPreviewFieldKeys([]);
                        form.setFieldsValue({
                          dynamicSourceId: sourceId,
                          dynamicValueField: undefined,
                          dynamicLabelField: undefined,
                        });
                      }}
                      notFoundContent={
                        dsLoading ? undefined : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
                        )
                      }
                    />
                  </Form.Item>
                  <Button
                    icon={<ReloadOutlined />}
                    aria-label={t('paramInput.dynamic.preview')}
                    disabled={!dynamicSourceId}
                    loading={dynamicPreviewLoading}
                    title={t('paramInput.dynamic.preview')}
                    className="mt-[30px]"
                    onClick={() => {
                      if (!dynamicSourceId) return;
                      const params: Record<string, unknown> = {};
                      queryParamRows.forEach((row) => {
                        const name = row.name.trim();
                        if (!name || row.mode === 'ref') return;
                        const literal = rowLiteralPayload(row);
                        if (literal === undefined || literal === null || literal === '') return;
                        params[name] = literal;
                      });
                      void fetchDynamicPreview(dynamicSourceId, params);
                    }}
                  />
                </div>

                <Form.Item
                  name="dynamicValueField"
                  label={t('paramInput.dynamic.valueField')}
                  className="mb-3"
                  rules={[
                    {
                      required: true,
                      message: t('paramInput.dynamic.valueFieldPlaceholder'),
                    },
                  ]}
                >
                  <DynamicFieldSelect
                    value={dynamicValueField}
                    placeholder={hasFieldSchema
                      ? t('paramInput.dynamic.valueFieldPlaceholder')
                      : t('paramInput.dynamic.fieldNamePlaceholder')}
                    options={availableFields}
                    allowCustom={!hasFieldSchema}
                    onChange={(field) => {
                      setDynamicValueField(field);
                    }}
                  />
                </Form.Item>
                <Form.Item
                  name="dynamicLabelField"
                  label={t('paramInput.dynamic.labelField')}
                  className="mb-3"
                  rules={[
                    {
                      required: true,
                      message: t('paramInput.dynamic.labelFieldPlaceholder'),
                    },
                  ]}
                >
                  <DynamicFieldSelect
                    value={dynamicLabelField}
                    placeholder={hasFieldSchema
                      ? t('paramInput.dynamic.labelFieldPlaceholder')
                      : t('paramInput.dynamic.fieldNamePlaceholder')}
                    options={availableFields}
                    allowCustom={!hasFieldSchema}
                    onChange={(field) => {
                      setDynamicLabelField(field);
                    }}
                  />
                </Form.Item>
                {queryParamRows.length > 0 ? (
                  <Form.Item label={t('paramInput.dynamic.queryParams')} className="mb-3">
                    <Table<QueryParamRow>
                      className="w-full"
                      size="small"
                      pagination={false}
                      tableLayout="fixed"
                      rowKey="uid"
                      dataSource={queryParamRows}
                      columns={[
                        {
                          title: t('paramInput.dynamic.queryParamTechnicalName'),
                          dataIndex: 'name',
                          width: 112,
                          ellipsis: true,
                          render: (name: string) => (
                            <span className="block truncate font-mono text-xs" title={name}>
                              {name}
                            </span>
                          ),
                        },
                        {
                          title: t('paramInput.dynamic.queryParamAlias'),
                          dataIndex: 'alias',
                          width: 112,
                          ellipsis: true,
                          render: (_value: string | undefined, row) => {
                            const alias = row.alias?.trim();
                            return (
                              <span className="block truncate text-xs" title={alias || undefined}>
                                {queryParamAliasText(row.alias)}
                              </span>
                            );
                          },
                        },
                        {
                          title: t('paramInput.dynamic.valueMode'),
                          dataIndex: 'mode',
                          width: 112,
                          render: (_value: QueryParamRow['mode'], row) => (
                            <Select
                              value={row.mode}
                              style={{ width: '100%' }}
                              popupMatchSelectWidth={false}
                              options={[
                                { value: 'literal', label: t('paramInput.dynamic.fixedValue') },
                                { value: 'ref', label: t('paramInput.dynamic.dollarRef') },
                              ]}
                              onChange={(mode: 'literal' | 'ref') => {
                                setQueryParamRows((prev) => prev.map((item) => (
                                  item.uid === row.uid ? { ...item, mode } : item
                                )));
                              }}
                            />
                          ),
                        },
                        {
                          title: t('paramInput.dynamic.valueOrRef'),
                          dataIndex: 'literalText',
                          render: (_value: string, row) => {
                            const choices = listOptionsQueryCandidates({
                              context: optionsQueryContext,
                              expectedType: row.type,
                            });
                            if (row.mode === 'ref') {
                              const selected = resolveOptionsQueryChoice(
                                row.refName,
                                choices,
                                optionsQueryContext,
                              );
                              return (
                                <Select
                                  value={selected?.ref ?? (row.refName || undefined)}
                                  style={{ width: '100%' }}
                                  listHeight={OPTIONS_QUERY_REF_LIST_HEIGHT}
                                  placeholder={t('paramInput.dynamic.selectUpstream')}
                                  options={choices.map((choice) => ({
                                    value: choice.ref,
                                    label: formatOptionsQueryCandidateLabel(choice, choices, t),
                                  }))}
                                  notFoundContent={(
                                    <Empty
                                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                                      description={t('paramInput.dynamic.noRefCandidates')}
                                    />
                                  )}
                                  onChange={(refName) => {
                                    setQueryParamRows((prev) => prev.map((item) => (
                                      item.uid === row.uid ? { ...item, refName } : item
                                    )));
                                  }}
                                />
                              );
                            }
                            return (
                              <Input
                                value={row.literalText}
                                placeholder={t('paramInput.dynamic.queryParamValue')}
                                onChange={(event) => {
                                  const literalText = event.target.value;
                                  setQueryParamRows((prev) => prev.map((item) => (
                                    item.uid === row.uid
                                      ? { ...item, literalText, literalRaw: undefined }
                                      : item
                                  )));
                                }}
                              />
                            );
                          },
                        },
                      ]}
                    />
                    {hasRefQueryParam ? (
                      <div className="mt-2 text-xs text-(--color-text-3)">
                        {t('paramInput.dynamic.previewFixedOnly')}
                      </div>
                    ) : null}
                  </Form.Item>
                ) : null}
                <Form.Item label={t('paramInput.dynamic.preview')} className="mb-0">
                  <Table
                    bordered
                    size="small"
                    loading={dynamicPreviewLoading}
                    pagination={false}
                    showHeader={dynamicPreviewColumns.length > 0}
                    dataSource={dynamicPreview}
                    rowKey={(_, index) => String(index)}
                    columns={dynamicPreviewColumns}
                    scroll={{ x: 'max-content' }}
                  />
                </Form.Item>
              </>
            )}
          </>
        )}
      </Form>
    </Modal>
  );
};
