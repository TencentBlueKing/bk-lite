'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, Modal, Select, Table, message } from 'antd';
import { DeleteOutlined, PlusOutlined, SwapOutlined } from '@ant-design/icons';

import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { withDatasourceNamespace } from '@/app/ops-analysis/context/dataVariableRuntime';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import ComponentSelector from '@/app/ops-analysis/components/widgetSelector';
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import { ConfigSectionTitle } from '@/app/ops-analysis/components/widgetConfig/configTitles';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, InputControlConfig, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { processDataSourceFormParamsForSubmit } from '@/app/ops-analysis/utils/dataSourceFormParams';
import {
  collectVariableIds,
  columnBlockReasonKey,
  createDataVariableId,
  isDataVariableRef,
  runDataVariables,
  validateDataVariables,
  type ColumnBlockReason,
  type DataVariable,
  type DataVariableIssueCode,
} from '@/app/ops-analysis/utils/dataVariable';
import {
  buildDataVariableRequestParams,
  buildDefaultFilterBindings,
  getBindableFilterParams,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import { useTranslation } from '@/utils/i18n';

interface DataVariableModalProps {
  open: boolean;
  variables: DataVariable[];
  dataSources: DatasourceItem[];
  filters: UnifiedFilterDefinition[];
  filterValues: Record<string, any>;
  namespaceId?: number;
  widgetConfigs: unknown;
  /** 打开时选中这一条。用于从组件查询回填进来的草稿。 */
  focusId?: string;
  onCancel: () => void;
  onConfirm: (variables: DataVariable[]) => void | Promise<void>;
}

const issueText = (
  code: DataVariableIssueCode,
  t: (key: string) => string,
) => {
  if (code === 'duplicate-name') return t('dataVariable.duplicateName');
  if (code === 'missing-name') return t('dataVariable.missingName');
  if (code === 'missing-value-field') return t('dataVariable.missingValueField');
  if (code === 'missing-datasource') return t('dataVariable.missingDatasource');
  if (code === 'cycle') return t('dataVariable.cycle');
  if (code === 'too-deep') return t('dataVariable.tooDeep');
  return t('dataVariable.unknownVariable');
};

const reasonText = (reason: ColumnBlockReason, t: (key: string) => string) =>
  t(columnBlockReasonKey(reason));

const rowsOf = (payload: unknown): Array<Record<string, unknown>> => {
  const list = Array.isArray(payload)
    ? payload
    : payload && typeof payload === 'object' && Array.isArray((payload as { items?: unknown }).items)
      ? (payload as { items: unknown[] }).items
      : [];
  return list.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row));
};

const previewCellText = (value: unknown): string => {
  if (value == null) return '';
  if (Array.isArray(value)) {
    return value
      .filter((item) => item != null && item !== '')
      .map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item)))
      .join(', ');
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const DataVariableModal: React.FC<DataVariableModalProps> = ({
  open,
  variables,
  dataSources,
  filters,
  filterValues,
  namespaceId,
  widgetConfigs,
  focusId,
  onCancel,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const { getSourceDataByApiId, getDataSourceBriefList } = useDataSourceApi();
  const [form] = Form.useForm();
  const [drafts, setDrafts] = useState<DataVariable[]>([]);
  const draftsRef = useRef<DataVariable[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const selectedIdRef = useRef('');
  selectedIdRef.current = selectedId;
  const [sourceCatalog, setSourceCatalog] = useState<DatasourceItem[]>([]);
  const [sourcePickerOpen, setSourcePickerOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewPayload, setPreviewPayload] = useState<unknown>(null);
  const [previewReason, setPreviewReason] = useState<ColumnBlockReason | null>(null);
  const [probedFields, setProbedFields] = useState<Record<string, string[]>>({});
  const [pickedSources, setPickedSources] = useState<Record<number, DatasourceItem>>({});
  const [editingParam, setEditingParam] = useState<ParamItem | null>(null);

  const replaceDrafts = (next: DataVariable[]) => {
    draftsRef.current = next;
    setDrafts(next);
  };

  const sourceById = (id?: number): DatasourceItem | undefined => {
    if (!id) return undefined;
    return sourceCatalog.find((item) => item.id === id)
      ?? dataSources.find((item) => item.id === id)
      ?? pickedSources[id];
  };

  const fillForm = (current: DataVariable | undefined) => {
    const source = sourceById(current?.dataSourceId);
    const params: Record<string, unknown> = {};
    (source?.params ?? []).forEach((param) => {
      params[param.name] = current && Object.prototype.hasOwnProperty.call(current.params, param.name)
        ? current.params[param.name]
        : param.value;
    });
    form.setFieldsValue({
      name: current?.name ?? '',
      valueField: current?.valueField || undefined,
      params,
    });
  };
  const openedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      openedRef.current = false;
      return;
    }
    if (openedRef.current) return;
    openedRef.current = true;
    const firstId = focusId && variables.some((item) => item.id === focusId)
      ? focusId
      : (variables[0]?.id ?? '');
    replaceDrafts(variables);
    setSelectedId(firstId);
    setPreviewPayload(null);
    setPreviewReason(null);
    setProbedFields({});
    setEditingParam(null);
    fillForm(variables.find((item) => item.id === firstId));
    // 只在弹层打开时用已保存的变量回填，编辑过程不再被父组件重渲染覆盖。
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let ignore = false;
    const loadSources = async () => {
      try {
        const response = await getDataSourceBriefList({ page_size: -1 });
        if (ignore) return;
        setSourceCatalog(Array.isArray(response) ? response : []);
      } catch (error) {
        if (ignore) return;
        console.error('获取数据源候选列表失败:', error);
        setSourceCatalog([]);
      }
    };
    void loadSources();
    return () => {
      ignore = true;
    };
  }, [getDataSourceBriefList, open]);

  const catalogHydratedRef = useRef(false);
  useEffect(() => {
    if (!open) {
      catalogHydratedRef.current = false;
      setSourcePickerOpen(false);
      return;
    }
    if (catalogHydratedRef.current || sourceCatalog.length === 0) return;
    catalogHydratedRef.current = true;
    const current = draftsRef.current.find((item) => item.id === selectedIdRef.current);
    if (!current?.dataSourceId) return;
    if (dataSources.some((item) => item.id === current.dataSourceId)) return;
    const source = sourceCatalog.find((item) => item.id === current.dataSourceId);
    if (!source) return;
    const params: Record<string, unknown> = {};
    (source.params ?? []).forEach((param) => {
      params[param.name] = Object.prototype.hasOwnProperty.call(current.params, param.name)
        ? current.params[param.name]
        : param.value;
    });
    form.setFieldsValue({ params });
  }, [dataSources, form, open, sourceCatalog]);

  const selected = drafts.find((item) => item.id === selectedId);
  const selectedSource = sourceById(selected?.dataSourceId);
  const sourceWithValues = useMemo(() => {
    if (!selectedSource || !selected) return undefined;
    return {
      ...selectedSource,
      params: (selectedSource.params ?? []).map((param) => ({
        ...param,
        value: Object.prototype.hasOwnProperty.call(selected.params, param.name)
          ? selected.params[param.name]
          : param.value,
        ...(selected.paramInputs?.[param.name]
          ? { inputConfig: selected.paramInputs[param.name] }
          : {}),
      })),
    } as DatasourceItem;
  }, [selected, selectedSource]);

  const otherVariables = drafts.filter((item) => item.id !== selectedId);
  const showLinkage = Boolean(selectedSource?.params?.length)
    && filters.length > 0
    && getBindableFilterParams(selectedSource?.params).length > 0;
  const fieldOptions = useMemo(() => {
    const keys = new Set<string>();
    (selectedSource?.field_schema ?? []).forEach((field) => {
      if (field.key) keys.add(field.key);
    });
    (probedFields[selectedId] ?? []).forEach((key) => keys.add(key));
    if (selected?.valueField) keys.add(selected.valueField);
    return [...keys].map((key) => {
      const titled = selectedSource?.field_schema?.find((field) => field.key === key);
      return { value: key, label: titled?.title && titled.title !== key ? `${titled.title} (${key})` : key };
    });
  }, [probedFields, selected?.valueField, selectedId, selectedSource]);

  const rememberCurrent = (): DataVariable[] => {
    const currentDrafts = draftsRef.current;
    const current = currentDrafts.find((item) => item.id === selectedId);
    if (!current) return currentDrafts;
    const values = form.getFieldsValue(true) as {
      name?: string;
      valueField?: string;
      params?: Record<string, unknown>;
    };
    const submitted = processDataSourceFormParamsForSubmit(
      values.params ?? {},
      sourceWithValues?.params ?? [],
    );
    const params = Object.fromEntries(submitted.map((param: ParamItem) => [param.name, param.value]));
    const filterBindings = buildDefaultFilterBindings(
      selectedSource?.params,
      filters,
      current.filterBindings,
    ) ?? current.filterBindings;
    const next = currentDrafts.map((item) => item.id === current.id
      ? {
        ...item,
        name: String(values.name ?? '').trim(),
        valueField: String(values.valueField ?? '').trim(),
        params,
        ...(filterBindings ? { filterBindings } : {}),
      }
      : item);
    replaceDrafts(next);
    return next;
  };

  const applySource = (source: DatasourceItem) => {
    if (typeof source.id === 'number') {
      setPickedSources((current) => ({ ...current, [source.id as number]: source }));
    }
    const filterBindings = buildDefaultFilterBindings(source.params, filters);
    const next = draftsRef.current.map((entry) => (
      entry.id === selectedId
        ? {
          ...entry,
          dataSourceId: Number(source.id) || 0,
          valueField: '',
          params: {},
          paramInputs: undefined,
          ...(filterBindings ? { filterBindings } : { filterBindings: undefined }),
        }
        : entry
    ));
    replaceDrafts(next);
    form.setFieldsValue({ valueField: undefined, params: {} });
    setPreviewPayload(null);
    setPreviewReason(null);
  };

  const selectVariable = (id: string) => {
    const next = rememberCurrent();
    setSelectedId(id);
    setPreviewPayload(null);
    setPreviewReason(null);
    fillForm(next.find((item) => item.id === id));
  };

  const addVariable = () => {
    const current = rememberCurrent();
    const created: DataVariable = {
      id: createDataVariableId(),
      name: '',
      dataSourceId: 0,
      valueField: '',
      params: {},
    };
    const next = [...current, created];
    replaceDrafts(next);
    setSelectedId(created.id);
    setPreviewPayload(null);
    setPreviewReason(null);
    fillForm(created);
  };

  const removeVariable = (id: string) => {
    const current = rememberCurrent();
    const used = collectVariableIds({
      variables: current.filter((item) => item.id !== id),
      widgets: widgetConfigs,
    });
    if (used.includes(id)) {
      message.warning(t('dataVariable.deleteBlocked'));
      return;
    }
    const next = current.filter((item) => item.id !== id);
    replaceDrafts(next);
    if (selectedId === id) {
      const fallback = next[0];
      setSelectedId(fallback?.id ?? '');
      fillForm(fallback);
    }
  };

  const handleConfirm = async () => {
    const next = rememberCurrent();
    const issues = validateDataVariables(next);
    if (issues.length > 0) {
      message.error(issueText(issues[0].code, t));
      if (issues[0].id) {
        setSelectedId(issues[0].id);
        fillForm(next.find((item) => item.id === issues[0].id));
      }
      return;
    }
    await onConfirm(next);
  };

  const handlePreview = async () => {
    const next = rememberCurrent();
    const current = next.find((item) => item.id === selectedId);
    if (!current?.dataSourceId) {
      message.warning(t('dataVariable.missingDatasource'));
      return;
    }
    setPreviewLoading(true);
    setPreviewPayload(null);
    setPreviewReason(null);
    try {
      const run = await runDataVariables({
        variables: next,
        roots: [current.id],
        fetchRows: async (variable, params) => {
          const source = sourceById(variable.dataSourceId);
          const shaped = buildDataVariableRequestParams({
            variable,
            resolvedParams: params,
            dataSource: source,
            filterValues,
            filterDefinitions: filters,
          });
          const prepared = withDatasourceNamespace(shaped, source?.namespaces, namespaceId);
          if (!prepared) throw new Error('data-variable-request-blocked');
          const result = await getSourceDataByApiId(variable.dataSourceId, prepared, {
            suppressErrorNotification: true,
          });
          return result.data;
        },
      });
      const column = run.columns[current.id];
      const payload = run.payloads[current.id];
      const keys = new Set<string>();
      rowsOf(payload).forEach((row) => {
        Object.keys(row).forEach((key) => keys.add(key));
      });
      if (keys.size > 0) {
        setProbedFields((currentFields) => ({
          ...currentFields,
          [current.id]: [...keys],
        }));
      }
      setPreviewPayload(payload ?? null);
      const failedBeforeRows = column?.status === 'blocked' && column.reason !== 'missing-field';
      setPreviewReason(!current.valueField
        ? (failedBeforeRows ? column.reason : null)
        : (column?.status === 'blocked' ? column.reason : null));
    } catch {
      setPreviewReason('request');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleInputConfigConfirm = (nextConfig: InputControlConfig) => {
    if (!editingParam || !selected) return;
    const name = editingParam.name;
    const current = rememberCurrent();
    const next = current.map((item) => {
      if (item.id !== selected.id) return item;
      return {
        ...item,
        paramInputs: { ...item.paramInputs, [name]: nextConfig },
      };
    });
    replaceDrafts(next);
    if (nextConfig.control === 'dataVariable') {
      form.setFieldValue(['params', name], { dataVariableId: nextConfig.dataVariableId });
    } else if (isDataVariableRef(form.getFieldValue(['params', name]))) {
      form.setFieldValue(['params', name], undefined);
    }
    setEditingParam(null);
  };

  const previewRows = rowsOf(previewPayload).slice(0, 20);
  const previewColumns = Object.keys(previewRows[0] ?? {}).slice(0, 12).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
    render: (value: unknown) => previewCellText(value),
  }));

  return (
    <>
      <Modal
        title={t('dataVariable.add')}
        open={open}
        onCancel={onCancel}
        onOk={() => handleConfirm()}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        width={1080}
        destroyOnHidden
        centered
        styles={{ body: { overflow: 'hidden' } }}
      >
        <div className="flex h-[min(440px,calc(100vh-220px))] min-h-[280px] gap-4">
          <div className="flex w-48 shrink-0 flex-col overflow-hidden border-r border-(--color-border-1) pr-3">
            <div className="mb-1 flex h-8 shrink-0 items-center justify-between">
              <span className="text-xs text-(--color-text-3)">{t('dataVariable.title')}</span>
              <button
                type="button"
                aria-label={t('dataVariable.add')}
                title={t('dataVariable.add')}
                className="inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded text-(--color-text-2) hover:bg-(--color-fill-1) hover:text-(--color-primary)"
                onClick={addVariable}
              >
                <PlusOutlined className="text-xs" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {drafts.length === 0 ? (
                <div className="px-1 py-6 text-center text-xs text-(--color-text-3)">
                  {t('dataVariable.emptyList')}
                </div>
              ) : drafts.map((item) => {
                const active = item.id === selectedId;
                return (
                  <div
                    key={item.id}
                    className={`group flex h-8 items-center border-l-2 ${
                      active
                        ? 'border-(--color-primary) bg-(--color-fill-1)'
                        : 'border-transparent hover:bg-(--color-fill-1)'
                    }`}
                  >
                    <button
                      type="button"
                      title={item.name || t('dataVariable.title')}
                      className={`min-w-0 flex-1 cursor-pointer truncate px-2 text-left text-sm leading-8 ${
                        active ? 'font-medium text-(--color-text-1)' : 'text-(--color-text-2)'
                      }`}
                      onClick={() => selectVariable(item.id)}
                    >
                      {item.name || t('dataVariable.title')}
                    </button>
                    <button
                      type="button"
                      aria-label={t('common.delete')}
                      className="mr-1 inline-flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center text-xs text-(--color-text-3) opacity-0 hover:text-(--color-text-1) group-hover:opacity-100 group-focus-within:opacity-100"
                      onClick={() => removeVariable(item.id)}
                    >
                      <DeleteOutlined />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
          {selected ? (
            <>
              <Form form={form} layout="vertical" className="min-h-0 min-w-0 flex-1 overflow-y-auto pr-1">
                <Form.Item
                  label={t('dataVariable.name')}
                  name="name"
                  rules={[{ required: true, message: t('dataVariable.missingName') }]}
                >
                  <Input maxLength={40} />
                </Form.Item>
                <Form.Item label={t('dashboard.dataSource')} required>
                  <Input
                    readOnly
                    placeholder={t('common.selectTip')}
                    value={selectedSource
                      ? `${selectedSource.name}${selectedSource.rest_api ? `（${selectedSource.rest_api}）` : ''}`
                      : ''}
                    suffix={
                      <SwapOutlined
                        className="cursor-pointer text-(--color-primary)"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setSourcePickerOpen(true);
                        }}
                      />
                    }
                    onClick={() => setSourcePickerOpen(true)}
                    className="cursor-pointer"
                  />
                </Form.Item>
                {(selectedSource?.params ?? []).some((param) => (
                  ['params', 'fixed'].includes(param.filterType || 'fixed')
                )) ? (
                  <>
                <ConfigSectionTitle>{t('dashboard.queryParams')}</ConfigSectionTitle>
                <DataSourceParamsConfig
                  key={`${selected.id}-${selected.dataSourceId}`}
                  selectedDataSource={sourceWithValues}
                  includeFilterTypes={['params', 'fixed']}
                  globalFilters={filters}
                  filterBindings={selected.filterBindings}
                  globalFilterValues={filterValues}
                  dataVariables={otherVariables}
                  onEditInputConfig={(param) => {
                    const currentValue = form.getFieldValue(['params', param.name]);
                    setEditingParam(isDataVariableRef(currentValue)
                      ? { ...param, inputConfig: { control: 'dataVariable', dataVariableId: currentValue.dataVariableId } }
                      : param);
                  }}
                />
                  </>
                  ) : null}
                {showLinkage ? (
                  <div className="mb-4">
                    <ConfigSectionTitle>{t('dashboard.unifiedFilterLinkage')}</ConfigSectionTitle>
                    <FilterBindingPanel
                      definitions={filters}
                      dataSourceParams={selectedSource?.params ?? []}
                      filterBindings={selected.filterBindings ?? {}}
                      onChange={(filterBindings) => {
                        const next = rememberCurrent().map((item) => (
                          item.id === selected.id ? { ...item, filterBindings } : item
                        ));
                        replaceDrafts(next);
                      }}
                    />
                  </div>
                ) : null}
                <div className="mt-2 border-t border-(--color-border-1) pt-4">
                <Form.Item
                  label={t('dataVariable.valueField')}
                  tooltip={t('dataVariable.valueFieldTip')}
                  name="valueField"
                  className="mb-0"
                  rules={[{ required: true, message: t('dataVariable.missingValueField') }]}
                >
                  <Select
                    showSearch
                    options={fieldOptions}
                    placeholder={t('common.selectTip')}
                    onChange={(valueField) => {
                      replaceDrafts(draftsRef.current.map((item) => (
                        item.id === selected.id ? { ...item, valueField } : item
                      )));
                    }}
                  />
                </Form.Item>
                </div>
              </Form>
              <div className="flex min-h-0 w-[460px] shrink-0 flex-col overflow-hidden border-l border-(--color-border-1) pl-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="m-0 text-sm font-semibold leading-6 text-(--color-text-1)">
                    {t('dataVariable.queryResult')}
                  </h3>
                  <Button size="small" loading={previewLoading} onClick={() => { void handlePreview(); }}>
                    {t('dataVariable.preview')}
                  </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-auto">
                  {previewReason ? (
                    <div className="text-sm text-(--color-text-2)">{reasonText(previewReason, t)}</div>
                  ) : null}
                  {previewRows.length > 0 ? (
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(_row, index) => String(index)}
                      dataSource={previewRows}
                      columns={previewColumns}
                      scroll={{ x: true }}
                    />
                  ) : null}
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-(--color-text-3)">
              {t('dataVariable.emptyList')}
            </div>
          )}
        </div>
      </Modal>
      <ParamInputConfigEditor
        key={editingParam?.name ?? 'closed'}
        open={editingParam !== null}
        variant={
          editingParam?.type === 'conditionFilter'
          || editingParam?.inputConfig?.control === 'conditionFilter'
            ? 'conditionFields'
            : 'param'
        }
        value={editingParam?.inputConfig}
        dataVariables={otherVariables.map((item) => ({ id: item.id, name: item.name || item.id }))}
        onConfirm={handleInputConfigConfirm}
        onCancel={() => setEditingParam(null)}
        excludeSourceIds={selectedSource ? [selectedSource.id] : []}
      />
      <ComponentSelector
        visible={sourcePickerOpen}
        hideSceneWidgets
        onCancel={() => setSourcePickerOpen(false)}
        onPickSource={(source) => {
          applySource(source);
          setSourcePickerOpen(false);
        }}
      />
    </>
  );
};

export default DataVariableModal;
