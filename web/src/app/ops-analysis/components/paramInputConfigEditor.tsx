'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Form, Input, message, Modal, Radio, Select, Space, Table } from 'antd';
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
import { useTranslation } from '@/utils/i18n';

interface StaticRow extends InputOption {
  uid: string;
}

interface ParamInputConfigEditorProps {
  open: boolean;
  value?: InputControlConfig;
  onConfirm: (value: InputControlConfig) => void;
  onCancel: () => void;
  excludeSourceIds?: number[];
}

interface SortableStaticRowProps {
  row: StaticRow;
  onChange: (uid: string, field: 'label' | 'value', value: string) => void;
  onAddAfter: (uid: string) => void;
  onRemove: (uid: string) => void;
  showRemove: boolean;
  placeholder: string;
}

const newId = () => Math.random().toString(36).slice(2);
const createRow = (): StaticRow => ({ uid: newId(), label: '', value: '' });
const SortableStaticRow: React.FC<SortableStaticRowProps> = ({
  row,
  onChange,
  onAddAfter,
  onRemove,
  showRemove,
  placeholder,
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
        placeholder={String(row.value).trim() ? undefined : placeholder}
        onChange={(event) => onChange(row.uid, 'value', event.target.value)}
      />
      <Input
        className="mr-[10px] w-2/5"
        value={row.label}
        placeholder={row.label.trim() ? undefined : placeholder}
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
}) => {
  const { t } = useTranslation();
  const { getDataSourceList, getSourceDataByApiId } = useDataSourceApi();
  const [control, setControl] = useState<InputControlConfig['control']>('input');
  const [sourceType, setSourceType] = useState<'static' | 'dynamic'>('static');
  const [staticRows, setStaticRows] = useState<StaticRow[]>([createRow()]);
  const [dataSourceList, setDataSourceList] = useState<DatasourceItem[]>([]);
  const [dsLoading, setDsLoading] = useState(false);
  const [dynamicSourceId, setDynamicSourceId] = useState<number | undefined>();
  const [dynamicValueField, setDynamicValueField] = useState<string | undefined>();
  const [dynamicLabelField, setDynamicLabelField] = useState<string | undefined>();
  const [dynamicPreview, setDynamicPreview] = useState<Record<string, unknown>[]>([]);
  const [dynamicPreviewLoading, setDynamicPreviewLoading] = useState(false);
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
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
      return;
    }

    setControl(value.control);
    if (value.control === 'input') {
      setSourceType('static');
      setStaticRows([createRow()]);
      setDynamicSourceId(undefined);
      setDynamicValueField(undefined);
      setDynamicLabelField(undefined);
      setDynamicPreview([]);
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
      return;
    }

    setSourceType('dynamic');
    setDynamicSourceId(value.optionsSource.sourceId);
    setDynamicValueField(value.optionsSource.valueField);
    setDynamicLabelField(value.optionsSource.labelField);
    setDynamicPreview([]);
  }, [open, value]);

  const filteredDataSourceList = useMemo(() => {
    if (excludeSourceIds.length === 0) return dataSourceList;
    return dataSourceList.filter((item) => !excludeSourceIds.includes(item.id));
  }, [dataSourceList, excludeSourceIds]);

  const availableFields = useMemo(() => {
    const first = dynamicPreview[0];
    if (!first) return [];
    return Object.keys(first).map((key) => ({ label: key, value: key }));
  }, [dynamicPreview]);

  const staticRowIds = useMemo(
    () => staticRows.map((row) => row.uid),
    [staticRows],
  );

  useEffect(() => {
    if (!open || sourceType !== 'dynamic' || control === 'input') return;
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
      sourceType !== 'dynamic' ||
      dynamicSourceId ||
      !value ||
      value.control === 'input' ||
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
    }
  }, [control, dataSourceList, dynamicSourceId, open, sourceType, value]);

  const fetchDynamicPreview = (sourceId: number) => {
    const requestId = ++previewRequestIdRef.current;
    setDynamicPreviewLoading(true);
    getSourceDataByApiId(sourceId, {})
      .then((response) => {
        if (requestId !== previewRequestIdRef.current) return;
        setDynamicPreview(extractDataSourceItems(response).slice(0, 5));
      })
      .catch((error: any) => {
        if (requestId !== previewRequestIdRef.current) return;
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
  };

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

  const handleConfirm = () => {
    if (control === 'input') {
      onConfirm({ control: 'input' });
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

      onConfirm({
        control,
        optionsSource: {
          type: 'static',
          staticItems,
        },
      });
      return;
    }

    if (!dynamicSourceId || !dynamicValueField || !dynamicLabelField) {
      message.warning(t('paramInput.dynamic.incomplete'));
      return;
    }

    const optionsSource: DynamicOptionsSource = {
      type: 'dynamic',
      sourceId: dynamicSourceId,
      valueField: dynamicValueField,
      labelField: dynamicLabelField,
    };

    onConfirm({ control, optionsSource });
  };

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
      <Form layout="vertical" colon={false}>
        <Form.Item label={t('paramInput.controlType')} className="mb-3">
          <Radio.Group
            value={control}
            onChange={(event) => setControl(event.target.value)}
            options={[
              { label: t('paramInput.control.input'), value: 'input' },
              { label: t('paramInput.control.select'), value: 'select' },
              { label: t('paramInput.control.radio'), value: 'radio' },
            ]}
          />
        </Form.Item>

        {control !== 'input' && (
          <>
            <Form.Item label={t('paramInput.sourceType')} className="mb-3">
              <Radio.Group
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
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
                      <li className="mb-2 flex items-center text-sm text-[var(--color-text-2)]">
                        <span className="mr-[4px] w-[14px]" />
                        <span className="mr-[10px] w-2/5">
                          {t('paramInput.static.value')}
                        </span>
                        <span className="mr-[10px] w-2/5">
                          {t('paramInput.static.label')}
                        </span>
                      </li>
                      {staticRows.map((row) => (
                        <SortableStaticRow
                          key={row.uid}
                          row={row}
                          onChange={handleStaticChange}
                          onAddAfter={handleAddStaticRowAfter}
                          onRemove={handleRemoveStaticRow}
                          showRemove={staticRows.length > 1}
                          placeholder={t('common.inputMsg')}
                        />
                      ))}
                    </ul>
                  </SortableContext>
                </DndContext>
              </Form.Item>
            ) : (
              <>
                <Form.Item label={t('paramInput.dynamic.source')} className="mb-3">
                  <Space.Compact style={{ width: '100%' }}>
                    <Select
                      showSearch
                      loading={dsLoading}
                      value={dynamicSourceId}
                      placeholder={t('paramInput.dynamic.sourcePlaceholder')}
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      options={filteredDataSourceList.map((item) => ({
                        value: item.id,
                        label: `${item.name}（${item.rest_api}）`,
                      }))}
                      onChange={(sourceId) => {
                        previewRequestIdRef.current += 1;
                        setDynamicSourceId(sourceId);
                        setDynamicValueField(undefined);
                        setDynamicLabelField(undefined);
                        setDynamicPreview([]);
                      }}
                      notFoundContent={
                        dsLoading ? undefined : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
                        )
                      }
                    />
                    <Button
                      icon={<ReloadOutlined />}
                      disabled={!dynamicSourceId}
                      loading={dynamicPreviewLoading}
                      title={t('paramInput.dynamic.preview')}
                      onClick={() => {
                        if (dynamicSourceId) fetchDynamicPreview(dynamicSourceId);
                      }}
                    />
                  </Space.Compact>
                </Form.Item>

                <Form.Item label={t('paramInput.dynamic.valueField')} className="mb-3">
                  <Select
                    value={dynamicValueField}
                    placeholder={t('paramInput.dynamic.valueFieldPlaceholder')}
                    disabled={availableFields.length === 0}
                    options={availableFields}
                    onChange={setDynamicValueField}
                  />
                </Form.Item>
                <Form.Item label={t('paramInput.dynamic.labelField')} className="mb-3">
                  <Select
                    value={dynamicLabelField}
                    placeholder={t('paramInput.dynamic.labelFieldPlaceholder')}
                    disabled={availableFields.length === 0}
                    options={availableFields}
                    onChange={setDynamicLabelField}
                  />
                </Form.Item>
                <Form.Item label={t('paramInput.dynamic.preview')} className="mb-0">
                  <Table
                    size="small"
                    pagination={false}
                    showHeader={false}
                    dataSource={dynamicPreview}
                    rowKey={(_, index) => String(index)}
                    columns={[
                      {
                        dataIndex: dynamicLabelField || '',
                        render: (text) => String(text ?? ''),
                      },
                    ]}
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
