'use client';

import React, { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useUserInfoContext } from '@/context/userInfo';
import { QuestionCircleOutlined, CheckOutlined, HolderOutlined, FilterOutlined, DownOutlined, RightOutlined } from '@ant-design/icons';
import type { CorrelationRule } from '@/app/alarm/types/settings';
import {
  Drawer,
  Form,
  Input,
  Select,
  Radio,
  InputNumber,
  message,
  Tooltip,
  Switch,
  Slider,
  Tag,
  Button,
} from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import RulesMatch from '../../components/matchRule';
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
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface OperateModalProps {
  open: boolean;
  currentRow?: CorrelationRule | null;
  onClose: () => void;
  onSuccess: () => void;
}

type PolicyType = 'service' | 'location' | 'resource_name' | 'other';
type AggregationDimension = 'service' | 'location' | 'resource_name' | 'item';

const SectionTitle: React.FC<{ title: string }> = ({ title }) => (
  <div className="flex items-center mb-3 mt-5">
    <div className="w-[3px] h-[16px] bg-blue-500 rounded-sm mr-2" />
    <span className="font-medium text-[15px] text-gray-700">{title}</span>
  </div>
);

const POLICY_PRESETS: Record<PolicyType, { dimensions: AggregationDimension[]; window: number }> = {
  service: { dimensions: ['service'], window: 2 },
  location: { dimensions: ['location'], window: 5 },
  resource_name: { dimensions: ['resource_name'], window: 5 },
  other: { dimensions: ['service'], window: 5 },
};

const DIMENSION_OPTIONS: AggregationDimension[] = ['service', 'location', 'resource_name', 'item'];

const DEFAULT_FILTER_RULES = [[{ key: 'source_id', operator: 'eq', value: '' }]];

interface DraggableTagProps {
  id: string;
  onClose: (e?: React.MouseEvent<HTMLElement>) => void;
}

const DraggableTag: React.FC<DraggableTagProps> = ({ id, onClose }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

  return (
    <Tag
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        display: 'inline-flex',
        alignItems: 'center',
      }}
      closable
      onClose={onClose}
    >
      <HolderOutlined 
        {...attributes} 
        {...listeners} 
        className="cursor-grab mr-1"
        onMouseDown={(e) => e.stopPropagation()}
      />
      {id}
    </Tag>
  );
};

const OperateModal: React.FC<OperateModalProps> = ({ open, currentRow, onClose, onSuccess }) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);
  const { createCorrelationRule, updateCorrelationRule } = useSettingApi();

  const [strategyType, setStrategyType] = useState<'smart_denoise' | 'missing_detection'>('smart_denoise');
  const [filterType, setFilterType] = useState<'all' | 'filter'>('all');
  const [policy, setPolicy] = useState<PolicyType>('service');
  const [dimensions, setDimensions] = useState<AggregationDimension[]>(['service']);
  const [detectionWindow, setDetectionWindow] = useState<number>(2);
  const [selfHealingEnabled, setSelfHealingEnabled] = useState(false);
  const [autoCloseEnabled, setAutoCloseEnabled] = useState(true);
  const [detailExpanded, setDetailExpanded] = useState(false);

  const windowMarks: Record<number, React.ReactNode> = {
    1: <span className="text-xs">{t('settings.correlation.windowSensitive')}</span>,
    5: <span className="text-xs">{t('settings.correlation.windowBalanced')}</span>,
    15: <span className="text-xs">{t('settings.correlation.windowPatient')}</span>,
  };

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  useEffect(() => {
    if (!open) return;
    form.resetFields();

    if (currentRow) {
      const row = currentRow;
      setStrategyType(row.strategy_type === 'missing_detection' ? 'missing_detection' : 'smart_denoise');
      setFilterType(row.match_rules?.length ? 'filter' : 'all');
      setPolicy((row.params?.policy as PolicyType) || 'service');
      setDimensions((row.params?.group_by as AggregationDimension[]) || ['service']);
      setDetectionWindow(row.params?.window_size ?? 5);
      setSelfHealingEnabled(row.params?.time_out ?? false);
      setAutoCloseEnabled(row.auto_close ?? true);

      form.setFieldsValue({
        name: row.name,
        organization: row.team || [],
        assign_organization: row.dispatch_team?.[0],
        filter_rules: row.match_rules?.length ? row.match_rules : DEFAULT_FILTER_RULES,
        self_healing_observation_time: row.params?.time_minutes ?? 60,
        auto_close_time: row.close_minutes ?? 120,
      });
    } else {
      setStrategyType('smart_denoise');
      setFilterType('all');
      setPolicy('service');
      setDimensions(['service']);
      setDetectionWindow(2);
      setSelfHealingEnabled(false);
      setAutoCloseEnabled(true);
      setDetailExpanded(false);

      form.setFieldsValue({
        name: '',
        organization: selectedGroup ? [selectedGroup.id] : [],
        assign_organization: selectedGroup?.id,
        filter_rules: DEFAULT_FILTER_RULES,
        self_healing_observation_time: 60,
        auto_close_time: 120,
      });
    }
  }, [open, currentRow, form, selectedGroup]);

  const handlePolicyChange = (newPolicy: PolicyType) => {
    setPolicy(newPolicy);
    if (newPolicy !== 'other') {
      const preset = POLICY_PRESETS[newPolicy];
      setDimensions(preset.dimensions);
      setDetectionWindow(preset.window);
    }
  };

  const handleDimensionChange = (selected: AggregationDimension[]) => {
    if (selected.length === 0) return;
    setDimensions(selected);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = dimensions.indexOf(active.id as AggregationDimension);
      const newIndex = dimensions.indexOf(over.id as AggregationDimension);
      setDimensions(arrayMove(dimensions, oldIndex, newIndex));
    }
  };

  const handleWindowChange = (value: number | null) => {
    if (value === null) return;
    setDetectionWindow(value);
  };

  const handleFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const isSmartDenoise = strategyType === 'smart_denoise';
      const data = {
        name: values.name,
        strategy_type: strategyType,
        description: '',
        team: values.organization || [],
        dispatch_team: values.assign_organization ? [values.assign_organization] : [],
        match_rules: filterType === 'filter' ? values.filter_rules || [] : [],
        params: {
          ...(isSmartDenoise && {
            policy,
            group_by: dimensions,
            window_size: detectionWindow,
          }),
          time_out: selfHealingEnabled,
          time_minutes: selfHealingEnabled ? values.self_healing_observation_time : undefined,
        },
        auto_close: autoCloseEnabled,
        close_minutes: autoCloseEnabled ? values.auto_close_time : undefined,
      };

      if (currentRow?.id) {
        await updateCorrelationRule(currentRow.id, data);
      } else {
        await createCorrelationRule(data);
      }
      message.success(t('alarmCommon.successOperate'));
      onSuccess();
      onClose();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <Drawer
      title={currentRow ? t('settings.correlation.editStrategy') : t('settings.correlation.addStrategy')}
      width={720}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={submitLoading}>{t('common.cancel')}</Button>
          <Button type="primary" loading={submitLoading} onClick={() => form.submit()}>{t('common.confirm')}</Button>
        </div>
      }
    >
      <Form form={form} layout="vertical" onFinish={handleFinish} className="text-sm">
        {/* 策略类型选择 */}
        <div className="flex gap-3 mb-4">
          {[
            { value: 'smart_denoise', icon: FilterOutlined, labelKey: 'noiseReduction', descKey: 'noiseReductionDesc' },
            // { value: 'missing_detection', icon: AlertOutlined, labelKey: 'missingDetection', descKey: 'missingDetectionDesc' },
          ].map(({ value, icon: Icon, labelKey, descKey }) => {
            const isSelected = strategyType === value;
            return (
              <div
                key={value}
                className={`relative rounded-lg px-3 py-3 cursor-pointer transition-all duration-200 border ${
                  isSelected
                    ? 'border-blue-400 bg-gradient-to-br from-blue-50 to-blue-50/30 shadow-md ring-1 ring-blue-200/50'
                    : 'border-gray-200 bg-white hover:border-blue-200 hover:shadow-sm'
                }`}
                style={{ width: 'calc(50% - 6px)' }}
                onClick={() => setStrategyType(value as 'smart_denoise' | 'missing_detection')}
              >
                {isSelected && (
                  <div className="absolute top-2 right-2 w-5 h-5 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center shadow-sm">
                    <CheckOutlined className="text-white" style={{ fontSize: 10 }} />
                  </div>
                )}
                <div className="flex justify-center mb-2">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                    isSelected ? 'bg-gradient-to-br from-blue-100 to-blue-50 shadow-sm' : 'bg-gray-50 border border-gray-100'
                  }`}>
                    <Icon className={`text-lg ${isSelected ? 'text-blue-600' : 'text-gray-500'}`} />
                  </div>
                </div>
                <div className={`text-sm font-medium text-center transition-colors ${isSelected ? 'text-blue-700' : 'text-gray-700'}`}>
                  {t(`settings.correlation.${labelKey}`)}
                </div>
                <div className="text-xs text-center mt-0.5 text-gray-400 line-clamp-2">
                  {t(`settings.correlation.${descKey}`)}
                </div>
              </div>
            );
          })}
        </div>

        {/* 基础配置 */}
        <SectionTitle title={t('settings.correlation.basicConfig')} />
        <div className="pl-3 mb-4 space-y-4">
          <div className="flex items-center">
            <div className="w-[100px] text-sm text-right pr-2">
              <span className="text-red-500">* </span>{t('settings.correlation.policyName')}
            </div>
            <Form.Item name="name" rules={[{ required: true, message: t('common.inputTip') }]} className="mb-0 flex-1">
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
          </div>
          <div className="flex items-center">
            <div className="w-[100px] text-sm text-right pr-2">
              <span className="text-red-500">* </span>{t('settings.correlation.organization')}
            </div>
            <Form.Item name="organization" rules={[{ required: true, message: t('common.selectTip') }]} className="mb-0 flex-1">
              <GroupTreeSelect multiple placeholder={t('common.selectTip')} />
            </Form.Item>
          </div>
          <div className="flex items-center">
            <div className="w-[100px] text-sm text-right pr-2">
              <span className="text-red-500">* </span>{t('settings.correlation.assignOrganization')}
              <Tooltip title={t('settings.correlation.assignOrganizationTip')}>
                <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
              </Tooltip>
            </div>
            <Form.Item name="assign_organization" rules={[{ required: true, message: t('common.selectTip') }]} className="mb-0 flex-1">
              <GroupTreeSelect multiple={false} placeholder={t('common.selectTip')} />
            </Form.Item>
          </div>
        </div>

        {/* 定义事件范围 */}
        <SectionTitle title={t('settings.correlation.defineEventScope')} />
        <div className="pl-3 mb-4">
          <Radio.Group value={filterType} onChange={(e) => setFilterType(e.target.value)} size="small" className="mb-4">
            <Radio.Button value="all">{t('settings.correlation.all')}</Radio.Button>
            <Radio.Button value="filter">{t('settings.correlation.filter')}</Radio.Button>
          </Radio.Group>
          {filterType === 'filter' && (
            <div className="bg-slate-50/80 rounded-lg p-3 border border-slate-100">
              <Form.Item name="filter_rules" className="mb-0"><RulesMatch /></Form.Item>
            </div>
          )}
        </div>

        {/* 降噪策略 */}
        {strategyType === 'smart_denoise' && (
          <>
            <SectionTitle title={t('settings.correlation.noiseReductionStrategy')} />
            <div className="pl-3">
              <Radio.Group value={policy} onChange={(e) => handlePolicyChange(e.target.value)} size="small" className="mb-3">
                <Radio value="service">{t('settings.correlation.applicationFirst')}</Radio>
                <Radio value="location">{t('settings.correlation.infraFirst')}</Radio>
                <Radio value="resource_name">{t('settings.correlation.instanceFirst')}</Radio>
                <Radio value="other">{t('settings.correlation.custom')}</Radio>
              </Radio.Group>

              <div
                className="flex items-center gap-1 text-sm text-blue-600 cursor-pointer mb-2 select-none"
                onClick={() => setDetailExpanded(!detailExpanded)}
              >
                {detailExpanded ? <DownOutlined className="text-xs" /> : <RightOutlined className="text-xs" />}
                <span>{t('settings.correlation.detailConfig')}</span>
              </div>

              {detailExpanded && (
                <div className="bg-slate-50/80 rounded-lg p-4 space-y-4 border border-slate-100">
                  <div className="flex items-center">
                    <div className="w-[72px] shrink-0 text-[13px] text-slate-600">{t('settings.correlation.aggregationDimension')}</div>
                    <div className="flex-1">
                      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                        <SortableContext items={dimensions} strategy={horizontalListSortingStrategy}>
                          <Select
                            mode="multiple"
                            placeholder={t('common.selectTip')}
                            value={dimensions}
                            style={{ width: '100%' }}
                            onChange={handleDimensionChange}
                            options={DIMENSION_OPTIONS.map((d) => ({ value: d, label: d }))}
                            tagRender={({ value, onClose }) => (
                              <DraggableTag
                                id={value as string}
                                onClose={(e) => { if (dimensions.length > 1) onClose(e); }}
                              />
                            )}
                          />
                        </SortableContext>
                      </DndContext>
                    </div>
                  </div>

                  <div className="flex items-center">
                    <div className="w-[72px] shrink-0 text-[13px] text-slate-600">{t('settings.correlation.detectionWindow')}</div>
                    <div className="flex-1 flex items-center gap-3">
                      <div className="flex-1 px-1">
                        <Slider min={1} max={15} marks={windowMarks} value={detectionWindow} onChange={handleWindowChange}
                          tooltip={{ formatter: (val) => `${val} ${t('settings.correlation.min')}` }} />
                      </div>
                      <InputNumber min={1} max={15} value={detectionWindow} onChange={handleWindowChange}
                        addonAfter='min' style={{ width: 100 }} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <SectionTitle title={t('settings.correlation.selfHealing')} />
            <div className="pl-3">
              <Switch size="small" checked={selfHealingEnabled} onChange={setSelfHealingEnabled} className="mb-3" />
              {selfHealingEnabled && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center text-sm text-gray-600">
                    {t('settings.correlation.observationTime')}
                    <Tooltip title={t('settings.correlation.observationTimeTip')}>
                      <QuestionCircleOutlined className="ml-1 text-gray-400 text-xs" />
                    </Tooltip>
                  </span>
                  <Form.Item name="self_healing_observation_time" className="mb-0">
                    <InputNumber min={1} max={1440} addonAfter='min' style={{ width: 140 }} />
                  </Form.Item>
                </div>
              )}
            </div>

            <SectionTitle title={t('settings.correlation.autoClose')} />
            <div className="pl-3">
              <Switch size="small" checked={autoCloseEnabled} onChange={setAutoCloseEnabled} className="mb-3" />
              {autoCloseEnabled && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center text-sm text-gray-600">
                    {t('settings.correlation.autoCloseTime')}
                    <Tooltip title={t('settings.correlation.autoCloseTip')}>
                      <QuestionCircleOutlined className="ml-1 text-gray-400 text-xs" />
                    </Tooltip>
                  </span>
                  <Form.Item name="auto_close_time" className="mb-0">
                    <InputNumber min={1} max={10080} addonAfter='min' style={{ width: 140 }} />
                  </Form.Item>
                </div>
              )}
            </div>
          </>
        )}
      </Form>
    </Drawer>
  );
};

export default OperateModal;
