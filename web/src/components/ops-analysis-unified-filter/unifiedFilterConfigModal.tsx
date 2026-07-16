'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Table,
  Input,
  Switch,
  Tag,
  Select,
  Button,
  Tooltip,
  Radio,
} from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import {
  HolderOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import FilterOptionsModal from './filterOptionsModal';
import GroupTreeSelect from '@/components/group-tree-select';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import {
  isOptionInputMode,
  normalizeUnifiedFilterInputMode,
  sanitizeUnifiedFilterDefinition,
  scanUnifiedFilterParams,
  type UnifiedFilterLayoutItemLike,
} from './runtime';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import type {
  UnifiedFilterDefinition,
  FilterValue,
  TimeRangeValue,
  FilterOption,
  DatasourceItem,
} from '@/components/ops-analysis-widgets';

interface UnifiedFilterConfigModalProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: (definitions: UnifiedFilterDefinition[]) => void;
  definitions: UnifiedFilterDefinition[];
  layoutItems: UnifiedFilterLayoutItemLike[];
  dataSources: DatasourceItem[];
}

interface SortableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  'data-row-key': string;
}

interface ScannedParam {
  key: string;
  type: 'string' | 'timeRange';
  componentCount: number;
  sampleAlias: string;
  sampleDefaultValue: FilterValue;
}

const SortableRow: React.FC<SortableRowProps> = (props) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: props['data-row-key'] });

  const style: React.CSSProperties = {
    ...props.style,
    transform: CSS.Transform.toString(transform),
    transition,
    ...(isDragging ? { zIndex: 9999, position: 'relative' as const, background: '#fafafa' } : {}),
  };

  const contextValue = useMemo(
    () => ({ attributes, listeners }),
    [attributes, listeners],
  );

  return (
    <DragHandleContext.Provider value={contextValue}>
      <tr {...props} ref={setNodeRef} style={style} />
    </DragHandleContext.Provider>
  );
};

const DragHandle: React.FC = () => {
  const context = React.useContext(DragHandleContext);
  if (!context) return <HolderOutlined style={{ color: '#999' }} />;

  return (
    <HolderOutlined
      {...context.attributes}
      {...context.listeners}
      style={{ cursor: 'grab', color: '#999' }}
    />
  );
};

const DragHandleContext = React.createContext<{
  attributes: Record<string, any>;
  listeners: Record<string, any> | undefined;
} | null>(null);

const toSingleOrganizationValue = (value: FilterValue): number | undefined => {
  if (typeof value !== 'string' && typeof value !== 'number') return undefined;
  const normalized = Number(value);
  return Number.isNaN(normalized) ? undefined : normalized;
};

const toFilterValue = (value: number | number[] | undefined): FilterValue => {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
};

const UnifiedFilterConfigModal: React.FC<UnifiedFilterConfigModalProps> = ({
  open,
  onCancel,
  onConfirm,
  definitions: initialDefinitions,
  layoutItems,
  dataSources,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [definitions, setDefinitions] = useState<UnifiedFilterDefinition[]>([]);
  const [optionsModalOpen, setOptionsModalOpen] = useState(false);
  const [editingFilterId, setEditingFilterId] = useState<string | null>(null);
  const hasInitializedRef = useRef(false);
  const initialSnapshotRef = useRef<string>('');

  const filterTypeOptions = [
    { label: t('dashboard.string'), value: 'input' },
    { label: t('dashboard.inputModeSelect'), value: 'select' },
    { label: t('dashboard.inputModeRadio'), value: 'radio' },
    { label: t('dashboard.inputModeOrganization'), value: 'organization' },
  ];

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const scannedParams = useMemo(
    () => scanUnifiedFilterParams(layoutItems, dataSources) as ScannedParam[],
    [layoutItems, dataSources],
  );

  useEffect(() => {
    if (!open) {
      hasInitializedRef.current = false;
      return;
    }

    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    const existingMap = new Map(
      initialDefinitions.map((d) => [`${d.key}__${d.type}`, d]),
    );

    const merged = scannedParams.map((param, index) => {
      const compositeKey = `${param.key}__${param.type}`;
      const existing = existingMap.get(compositeKey);

      if (existing) {
        return existing;
      }

      return {
        id: compositeKey,
        key: param.key,
        name: param.sampleAlias,
        type: param.type,
        defaultValue: param.sampleDefaultValue,
        order: initialDefinitions.length + index,
        enabled: true,
      };
    });

    merged.sort((a, b) => a.order - b.order);
    setDefinitions(merged);
    initialSnapshotRef.current = JSON.stringify(merged);
  }, [open, initialDefinitions, scannedParams]);

  const handleCancel = () =>
    guardClose(
      JSON.stringify(definitions) !== initialSnapshotRef.current,
      onCancel,
    );

  const handleFieldChange = <K extends keyof UnifiedFilterDefinition>(
    id: string,
    field: K,
    value: UnifiedFilterDefinition[K],
  ) => {
    setDefinitions(
      definitions.map((d) => (d.id === id ? { ...d, [field]: value } : d)),
    );
  };

  const handleInputModeChange = (
    id: string,
    inputMode: UnifiedFilterDefinition['inputMode'],
  ) => {
    setDefinitions(
      definitions.map((definition) => {
        if (definition.id !== id) return definition;
        return sanitizeUnifiedFilterDefinition({
          ...definition,
          inputMode,
          defaultValue: null,
          options: isOptionInputMode(inputMode) ? definition.options : undefined,
        });
      }),
    );
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = definitions.findIndex((d) => d.id === active.id);
    const newIndex = definitions.findIndex((d) => d.id === over.id);

    const newDefinitions = arrayMove(definitions, oldIndex, newIndex).map(
      (d, idx) => ({ ...d, order: idx }),
    );
    setDefinitions(newDefinitions);
  };

  const handleConfirm = () => {
    onConfirm(definitions.map(sanitizeUnifiedFilterDefinition));
    onCancel();
  };

  const handleOpenOptionsModal = (filterId: string) => {
    setEditingFilterId(filterId);
    setOptionsModalOpen(true);
  };

  const handleOptionsConfirm = (options: FilterOption[]) => {
    if (editingFilterId) {
      const optionValues = options.map((item) => item.value);
      setDefinitions(
        definitions.map((d) =>
          d.id === editingFilterId
            ? sanitizeUnifiedFilterDefinition({
              ...d,
              options,
              defaultValue:
                 typeof d.defaultValue === 'string' && !optionValues.includes(d.defaultValue)
                   ? null
                   : d.defaultValue,
            })
            : d
        )
      );
    }
    setEditingFilterId(null);
    setOptionsModalOpen(false);
  };

  const getEditingFilterOptions = (): FilterOption[] => {
    if (!editingFilterId) return [];
    const filter = definitions.find((d) => d.id === editingFilterId);
    return filter?.options || [];
  };

  const columns = [
    {
      title: '',
      dataIndex: 'drag',
      width: 30,
      render: () => <DragHandle />,
    },
    {
      title: t('dashboard.filterKey'),
      dataIndex: 'key',
      width: 120,
      render: (value: string) => (
        <span className="font-mono text-xs">{value}</span>
      ),
    },
    {
      title: t('dashboard.filterName'),
      dataIndex: 'name',
      width: 180,
      render: (value: string, record: UnifiedFilterDefinition) => (
        <Input
          value={value}
          onChange={(e) => handleFieldChange(record.id, 'name', e.target.value)}
          placeholder={t('common.inputTip')}
        />
      ),
    },
    {
      title: t('dashboard.filterType'),
      dataIndex: 'type',
      width: 160,
      render: (_: unknown, record: UnifiedFilterDefinition) => {
        if (record.type === 'timeRange') {
          return (
            <Tag color="blue" style={{ marginRight: 0 }}>
              {t('dashboard.timeRange')}
            </Tag>
          );
        }

        const currentMode = normalizeUnifiedFilterInputMode(record.inputMode);

        return (
          <div className="flex items-center gap-2">
            <Select
              size="small"
              value={currentMode}
              options={filterTypeOptions}
              style={{ width: 120 }}
              onChange={(val) => handleInputModeChange(
                record.id,
                val as UnifiedFilterDefinition['inputMode'],
              )}
            />
          </div>
        );
      },
    },
    {
      title: t('dashboard.defaultValue'),
      dataIndex: 'defaultValue',
      width: 260,
      render: (value: FilterValue, record: UnifiedFilterDefinition) => {
        if (record.type === 'timeRange') {
          const getDefaultValue = (): { selectValue: number; rangePickerVaule: [dayjs.Dayjs, dayjs.Dayjs] | null } => {
            if (value === null || value === undefined) {
              return { selectValue: 15, rangePickerVaule: null };
            }
            if (typeof value === 'number') {
              return { selectValue: value, rangePickerVaule: null };
            }
            const timeValue = value as TimeRangeValue;
            if (!timeValue.start || !timeValue.end) {
              return { selectValue: 15, rangePickerVaule: null };
            }
            const selectVal = timeValue.selectValue ?? 0;
            if (selectVal > 0) {
              return { selectValue: selectVal, rangePickerVaule: null };
            }
            return {
              selectValue: 0,
              rangePickerVaule: [dayjs(timeValue.start), dayjs(timeValue.end)],
            };
          };

          return (
            <TimeSelector
              key={`${record.id}-${JSON.stringify(value)}`}
              onlyTimeSelect
              defaultValue={getDefaultValue()}
              onChange={(range, originValue) => {
                if (range.length === 2) {
                  handleFieldChange(record.id, 'defaultValue', {
                    start: dayjs(range[0]).toISOString(),
                    end: dayjs(range[1]).toISOString(),
                    selectValue: originValue ?? 0,
                  } as TimeRangeValue);
                } else {
                  handleFieldChange(record.id, 'defaultValue', null);
                }
              }}
            />
          );
        }

        const currentMode = normalizeUnifiedFilterInputMode(record.inputMode);

        if (currentMode === 'select') {
          return (
            <div className="flex items-center gap-2">
              <Select
                value={(typeof value === 'string' || typeof value === 'number') ? value : undefined}
                onChange={(nextValue) => handleFieldChange(record.id, 'defaultValue', nextValue ?? null)}
                placeholder={record.options?.length ? t('common.selectTip') : t('dashboard.configOptionsFirst')}
                allowClear
                disabled={!record.options?.length}
                options={record.options}
                className="flex-1"
              />
              <Tooltip title={t('dashboard.configOptions')}>
                <Button
                  type="text"
                  size="small"
                  icon={<SettingOutlined />}
                  className="shrink-0 text-[var(--color-text-2)] hover:text-[var(--color-primary)]"
                  onClick={() => handleOpenOptionsModal(record.id)}
                />
              </Tooltip>
            </div>
          );
        }

        if (currentMode === 'radio') {
          return (
            <div className="flex items-center gap-2">
              <Radio.Group
                value={(typeof value === 'string' || typeof value === 'number') ? value : undefined}
                onChange={(e) => handleFieldChange(record.id, 'defaultValue', e.target.value ?? null)}
                disabled={!record.options?.length}
                options={record.options}
                optionType="button"
                buttonStyle="outline"
                className="flex-1"
              />
              <Tooltip title={t('dashboard.configOptions')}>
                <Button
                  type="text"
                  size="small"
                  icon={<SettingOutlined />}
                  className="shrink-0 text-[var(--color-text-2)] hover:text-[var(--color-primary)]"
                  onClick={() => handleOpenOptionsModal(record.id)}
                />
              </Tooltip>
            </div>
          );
        }

        if (currentMode === 'organization') {
          return (
            <GroupTreeSelect
              value={toSingleOrganizationValue(value)}
              onChange={(nextValue) => handleFieldChange(record.id, 'defaultValue', toFilterValue(nextValue))}
              multiple={false}
              mode="ownership"
              allowClear
              placeholder=" "
            />
          );
        }

        return (
          <Input
            value={(typeof value === 'string' || typeof value === 'number') ? String(value) : ''}
            onChange={(e) =>
              handleFieldChange(
                record.id,
                'defaultValue',
                e.target.value || null,
              )
            }
            placeholder={t('common.inputTip')}
            allowClear
          />
        );
      },
    },
    {
      title: t('dashboard.enabled'),
      dataIndex: 'enabled',
      width: 70,
      render: (value: boolean, record: UnifiedFilterDefinition) => (
        <Switch
          size="small"
          checked={value}
          onChange={(checked) =>
            handleFieldChange(record.id, 'enabled', checked)
          }
        />
      ),
    },
  ];

  return (
    <OperateFormModal
      title={t('dashboard.unifiedFilterConfig')}
      open={open}
      onCancel={handleCancel}
      onConfirm={handleConfirm}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={920}
      maskClosable={false}
      centered
      destroyOnHidden
    >
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={definitions.map((d) => d.id)}
          strategy={verticalListSortingStrategy}
        >
          <Table
            rowKey="id"
            columns={columns}
            dataSource={definitions}
            pagination={false}
            size="small"
            components={{
              body: {
                row: SortableRow,
              },
            }}
            locale={{
              emptyText: (
                <CompactEmptyState
                  description={t('dashboard.noFiltersConfigured')}
                />
              ),
            }}
          />
        </SortableContext>
      </DndContext>
      <FilterOptionsModal
        open={optionsModalOpen}
        options={getEditingFilterOptions()}
        onCancel={() => {
          setOptionsModalOpen(false);
          setEditingFilterId(null);
        }}
        onConfirm={handleOptionsConfirm}
      />
    </OperateFormModal>
  );
};

export default UnifiedFilterConfigModal;
