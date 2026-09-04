'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Modal,
  Table,
  Input,
  Switch,
  Empty,
  Button,
  Select,
  Tag,
} from 'antd';
import {
  HolderOutlined,
} from '@ant-design/icons';
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import GroupTreeSelect from '@/components/group-tree-select';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  coerceValueForMultiple,
  isMultipleSelectInputConfig,
  migrateParamItemsFromStringList,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import DateRangeSelector from '@/app/ops-analysis/components/dateRangeSelector';
import {
  normalizeUnifiedFilterInputMode,
  sanitizeUnifiedFilterDefinition,
  type UnifiedFilterInputMode,
} from '@/app/ops-analysis/utils/widgetDataTransform';
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
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { hasInvalidDateRangeDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';
import type {
  UnifiedFilterDefinition,
  FilterValue,
  TimeRangeValue,
  LayoutItem,
} from '@/app/ops-analysis/types/dashBoard';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type {
  DatasourceItem,
  InputControlConfig,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import { isBindableDataSourceParamType } from '@/app/ops-analysis/utils/dataSourceParamContract';

interface UnifiedFilterConfigModalProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: (definitions: UnifiedFilterDefinition[]) => void;
  definitions: UnifiedFilterDefinition[];
  layoutItems: LayoutItem[];
  dataSources: DatasourceItem[];
}

interface SortableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  'data-row-key': string;
}

interface ScannedParam {
  key: string;
  type: 'string' | 'timeRange' | 'dateRange';
  componentCount: number;
  sampleAlias: string;
  sampleDefaultValue: FilterValue;
  sampleInputConfig?: InputControlConfig;
}

const PARAM_TYPE_LABEL_KEYS = new Set([
  'string',
  'number',
  'boolean',
  'date',
  'timeRange',
  'dateRange',
]);

const fillCell = () => ({ className: 'max-w-0 overflow-hidden' });

const coerceDefaultValueForInputConfig = (
  defaultValue: FilterValue | undefined,
  inputConfig: InputControlConfig,
): FilterValue | null =>
  coerceValueForMultiple(defaultValue, isMultipleSelectInputConfig(inputConfig));

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

const scanFilterParams = (
  layoutItems: LayoutItem[],
  dataSources: DatasourceItem[],
): ScannedParam[] => {
  const paramMap = new Map<string, ScannedParam>();

  const usedDataSourceIds = new Set<number>();
  layoutItems.forEach((item) => {
    const dsId = item.valueConfig?.dataSource;
    if (dsId) {
      usedDataSourceIds.add(typeof dsId === 'string' ? parseInt(dsId, 10) : dsId);
    }
  });

  dataSources.forEach((ds) => {
    if (!usedDataSourceIds.has(ds.id)) return;

    const params = migrateParamItemsFromStringList(
      Array.isArray(ds.params) ? ds.params : [],
    ).params;
    params.forEach((param: ParamItem) => {
      if (param.filterType !== 'filter') return;
      if (!isBindableDataSourceParamType(param.type)) return;

      const compositeKey = `${param.name}__${param.type}`;
      const existing = paramMap.get(compositeKey);

      if (existing) {
        existing.componentCount += 1;
      } else {
        paramMap.set(compositeKey, {
          key: param.name,
          type: param.type,
          componentCount: 1,
          sampleAlias: param.alias_name || param.name,
          sampleDefaultValue: (param.value as FilterValue) ?? null,
          sampleInputConfig: param.inputConfig,
        });
      }
    });
  });

  return Array.from(paramMap.values());
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
  const [inputConfigModalOpen, setInputConfigModalOpen] = useState(false);
  const [editingFilterId, setEditingFilterId] = useState<string | null>(null);
  const hasInitializedRef = useRef(false);
  const initialSnapshotRef = useRef<string>('');

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const scannedParams = useMemo(
    () => scanFilterParams(layoutItems, dataSources),
    [layoutItems, dataSources],
  );

  const getFilterInputConfig = (
    definition?: UnifiedFilterDefinition,
  ): InputControlConfig | undefined => {
    if (!definition) return undefined;
    const normalized = normalizeInputConfig(definition);
    const inputMode = normalizeUnifiedFilterInputMode(definition.inputMode);
    if (normalized) {
      if (inputMode === 'select' || inputMode === 'radio') {
        if (normalized.control === 'input') {
          return {
            control: inputMode,
            optionsSource: {
              type: 'static',
              staticItems: [],
            },
          };
        }
        if (normalized.control === inputMode) {
          return normalized;
        }
        return { ...normalized, control: inputMode };
      }
      return normalized;
    }
    if (inputMode === 'select' || inputMode === 'radio') {
      return {
        control: inputMode,
        optionsSource: {
          type: 'static',
          staticItems: [],
        },
      };
    }
    return { control: 'input' };
  };

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
        inputConfig: param.sampleInputConfig,
        inputMode: param.sampleInputConfig?.control,
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
    if (hasInvalidDateRangeDefinitions(definitions)) return;
    onConfirm(definitions.map(sanitizeUnifiedFilterDefinition));
    onCancel();
  };

  const handleOpenInputConfigModal = (filterId: string) => {
    setEditingFilterId(filterId);
    setInputConfigModalOpen(true);
  };

  const handleControlTypeChange = (
    filterId: string,
    nextMode: UnifiedFilterInputMode,
  ) => {
    setDefinitions(
      definitions.map((definition) => {
        if (definition.id !== filterId) return definition;

        if (nextMode === 'input') {
          const inputConfig: InputControlConfig = { control: 'input' };
          return sanitizeUnifiedFilterDefinition({
            ...definition,
            inputMode: 'input',
            inputConfig,
            defaultValue: coerceDefaultValueForInputConfig(
              definition.defaultValue,
              inputConfig,
            ),
          });
        }

        if (nextMode === 'organization') {
          return sanitizeUnifiedFilterDefinition({
            ...definition,
            inputMode: 'organization',
            inputConfig: undefined,
            defaultValue: coerceDefaultValueForInputConfig(
              definition.defaultValue,
              { control: 'input' },
            ),
          });
        }

        const currentConfig = getFilterInputConfig(definition);
        const inputConfig: InputControlConfig =
          currentConfig && currentConfig.control !== 'input'
            ? {
              ...currentConfig,
              control: nextMode,
              ...(nextMode === 'radio'
                ? { multiple: undefined, picker: undefined }
                : {}),
            }
            : {
              control: nextMode,
              optionsSource: {
                type: 'static',
                staticItems: [],
              },
            };

        return sanitizeUnifiedFilterDefinition({
          ...definition,
          inputMode: nextMode,
          inputConfig,
          defaultValue: coerceDefaultValueForInputConfig(
            definition.defaultValue,
            inputConfig,
          ),
        });
      }),
    );
  };

  const getStringControlMode = (
    definition: UnifiedFilterDefinition,
  ): UnifiedFilterInputMode => {
    const inputMode = normalizeUnifiedFilterInputMode(definition.inputMode);
    if (inputMode === 'organization') return 'organization';
    const inputConfig = getFilterInputConfig(definition);
    if (inputConfig?.control === 'select' || inputConfig?.control === 'radio') {
      return inputConfig.control;
    }
    return 'input';
  };

  const handleInputConfigConfirm = (inputConfig: InputControlConfig) => {
    if (!editingFilterId) return;
    setDefinitions(
      definitions.map((definition) =>
        definition.id === editingFilterId
          ? sanitizeUnifiedFilterDefinition({
            ...definition,
            inputConfig,
            inputMode: inputConfig.control,
            options: undefined,
            defaultValue: coerceDefaultValueForInputConfig(
              definition.defaultValue,
              inputConfig,
            ),
          })
          : definition,
      ),
    );
    setEditingFilterId(null);
    setInputConfigModalOpen(false);
  };

  const getEditingFilterInputConfig = (): InputControlConfig | undefined => {
    if (!editingFilterId) return undefined;
    return getFilterInputConfig(definitions.find((d) => d.id === editingFilterId));
  };

  const columns = [
    {
      title: '',
      dataIndex: 'drag',
      width: 20,
      render: () => <DragHandle />,
    },
    {
      title: t('dashboard.filterKey'),
      dataIndex: 'key',
      width: 170,
      render: (value: string, record: UnifiedFilterDefinition) => (
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          <span className="font-mono text-xs">{value}</span>
          <Tag className="m-0 px-1.5 text-[11px] leading-[18px]">
            {PARAM_TYPE_LABEL_KEYS.has(record.type)
              ? t(`dataSource.paramTypes.${record.type}`)
              : record.type}
          </Tag>
        </div>
      ),
    },
    {
      title: t('dashboard.filterName'),
      dataIndex: 'name',
      width: 140,
      onCell: fillCell,
      render: (value: string, record: UnifiedFilterDefinition) => (
        <Input
          className="w-full"
          value={value}
          onChange={(e) => handleFieldChange(record.id, 'name', e.target.value)}
          placeholder={t('common.inputTip')}
        />
      ),
    },
    {
      title: t('paramInput.controlType'),
      dataIndex: 'inputMode',
      width: 140,
      onCell: fillCell,
      render: (_: unknown, record: UnifiedFilterDefinition) => {
        if (record.type === 'timeRange' || record.type === 'dateRange') {
          return (
            <Select
              disabled
              value={record.type}
              options={[
                {
                  value: record.type,
                  label:
                    record.type === 'timeRange'
                      ? t('dashboard.timeRange')
                      : t('dashboard.dateRange'),
                },
              ]}
              className="w-full"
            />
          );
        }

        const currentMode = getStringControlMode(record);
        const controlTypeOptions = [
          { value: 'input', label: t('paramInput.control.input') },
          { value: 'select', label: t('paramInput.control.select') },
          { value: 'radio', label: t('paramInput.control.radio') },
          ...(currentMode === 'organization'
            ? [
              {
                value: 'organization',
                label: t('dashboard.inputModeOrganization'),
              },
            ]
            : []),
        ];

        return (
          <div className="flex w-full min-w-0 items-center gap-1">
            <div className="min-w-0 flex-1">
              <Select
                value={currentMode}
                options={controlTypeOptions}
                onChange={(value) =>
                  handleControlTypeChange(
                    record.id,
                    value as UnifiedFilterInputMode,
                  )
                }
                className="w-full"
              />
            </div>
            {(currentMode === 'select' || currentMode === 'radio') && (
              <Button
                type="link"
                size="small"
                className="h-auto shrink-0 px-0"
                onClick={() => handleOpenInputConfigModal(record.id)}
              >
                {t('dashboard.configure')}
              </Button>
            )}
          </div>
        );
      },
    },
    {
      title: t('dashboard.defaultValue'),
      dataIndex: 'defaultValue',
      width: 350,
      render: (value: FilterValue, record: UnifiedFilterDefinition) => {
        if (record.type === 'timeRange') {
          const getDefaultValue = (): {
            selectValue: number;
            rangePickerVaule: [dayjs.Dayjs, dayjs.Dayjs] | null;
          } => {
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

        if (record.type === 'dateRange') {
          return (
            <DateRangeSelector
              value={value as DateRangeValue | null | undefined}
              onChange={(nextValue) =>
                handleFieldChange(record.id, 'defaultValue', nextValue)
              }
            />
          );
        }

        const currentMode = normalizeUnifiedFilterInputMode(record.inputMode);

        if (currentMode !== 'organization') {
          const inputConfig = getFilterInputConfig(record);
          const isMultiple = Boolean(
            inputConfig &&
            inputConfig.control !== 'input' &&
            inputConfig.multiple,
          );
          const controlValue = Array.isArray(value)
            ? value
            : typeof value === 'string' || typeof value === 'number'
              ? value
              : undefined;
          const fallbackInput = (
            <Input
              value={
                Array.isArray(value)
                  ? value.map(String).join(', ')
                  : typeof value === 'string' || typeof value === 'number'
                    ? String(value)
                    : ''
              }
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

          return (
            <ParamInputControl
              inputConfig={inputConfig}
              fallback={fallbackInput}
              value={controlValue}
              onChange={(nextValue) => {
                if (isMultiple) {
                  if (Array.isArray(nextValue)) {
                    handleFieldChange(record.id, 'defaultValue', nextValue);
                    return;
                  }
                  if (
                    typeof nextValue === 'string' ||
                    typeof nextValue === 'number'
                  ) {
                    handleFieldChange(record.id, 'defaultValue', [nextValue]);
                    return;
                  }
                  handleFieldChange(record.id, 'defaultValue', null);
                  return;
                }
                handleFieldChange(record.id, 'defaultValue', nextValue ?? null);
              }}
              placeholder={record.name}
            />
          );
        }

        if (currentMode === 'organization') {
          return (
            <GroupTreeSelect
              value={toSingleOrganizationValue(value)}
              onChange={(nextValue) =>
                handleFieldChange(
                  record.id,
                  'defaultValue',
                  toFilterValue(nextValue),
                )
              }
              multiple={false}
              mode="ownership"
              allowClear
              placeholder=" "
            />
          );
        }

        return (
          <Input
            value={
              typeof value === 'string' || typeof value === 'number'
                ? String(value)
                : ''
            }
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
    <Modal
      title={t('dashboard.unifiedFilterConfig')}
      open={open}
      onCancel={handleCancel}
      onOk={handleConfirm}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={1000}
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
            tableLayout="fixed"
            components={{
              body: {
                row: SortableRow,
              },
            }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('dashboard.noFiltersConfigured')}
                />
              ),
            }}
          />
        </SortableContext>
      </DndContext>
      <ParamInputConfigEditor
        key={editingFilterId ?? 'closed'}
        open={inputConfigModalOpen}
        value={getEditingFilterInputConfig()}
        onConfirm={handleInputConfigConfirm}
        onCancel={() => {
          setInputConfigModalOpen(false);
          setEditingFilterId(null);
        }}
      />
    </Modal>
  );
};

export default UnifiedFilterConfigModal;
