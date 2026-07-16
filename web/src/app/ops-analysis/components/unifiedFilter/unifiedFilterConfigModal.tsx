'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Modal,
  Table,
  Input,
  Switch,
  Empty,
  Button,
  Tooltip,
} from 'antd';
import {
  HolderOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';
import { ParamInputControl } from '@/app/ops-analysis/components/paramInputControl';
import GroupTreeSelect from '@/components/group-tree-select';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import dayjs from 'dayjs';
import TimeSelector from '@/components/time-selector';
import {
  normalizeUnifiedFilterInputMode,
  sanitizeUnifiedFilterDefinition,
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
import type {
  UnifiedFilterDefinition,
  FilterValue,
  TimeRangeValue,
  LayoutItem,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  DatasourceItem,
  InputControlConfig,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';

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

    const params = Array.isArray(ds.params) ? ds.params : [];
    params.forEach((param: ParamItem) => {
      if (param.filterType !== 'filter') return;
      if (param.type !== 'string' && param.type !== 'timeRange') return;

      const compositeKey = `${param.name}__${param.type}`;
      const existing = paramMap.get(compositeKey);

      if (existing) {
        existing.componentCount += 1;
      } else {
        paramMap.set(compositeKey, {
          key: param.name,
          type: param.type as 'string' | 'timeRange',
          componentCount: 1,
          sampleAlias: param.alias_name || param.name,
          sampleDefaultValue: (param.value as FilterValue) ?? null,
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
    onConfirm(definitions.map(sanitizeUnifiedFilterDefinition));
    onCancel();
  };

  const handleOpenInputConfigModal = (filterId: string) => {
    setEditingFilterId(filterId);
    setInputConfigModalOpen(true);
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
          return <span>{t('dashboard.timeRange')}</span>;
        }

        return (
          <div className="flex w-full items-center justify-between">
            <span>{t('dashboard.string')}</span>
            <Tooltip title={t('dashboard.configOptions')}>
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined />}
                className="shrink-0 text-[var(--color-text-3)] hover:text-[var(--color-text-2)]"
                onClick={() => handleOpenInputConfigModal(record.id)}
              />
            </Tooltip>
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

        if (currentMode !== 'organization') {
          const inputConfig = getFilterInputConfig(record);
          const fallbackInput = (
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

          return (
            <ParamInputControl
              inputConfig={inputConfig}
              fallback={fallbackInput}
              value={(typeof value === 'string' || typeof value === 'number') ? value : undefined}
              onChange={(nextValue) => handleFieldChange(record.id, 'defaultValue', nextValue ?? null)}
              placeholder={record.name}
              style={{ minWidth: 160 }}
            />
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
    <Modal
      title={t('dashboard.unifiedFilterConfig')}
      open={open}
      onCancel={handleCancel}
      onOk={handleConfirm}
      okText={t('common.confirm')}
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
