'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useUserInfoContext } from '@/context/userInfo';
import {
  QuestionCircleOutlined,
  CheckOutlined,
  HolderOutlined,
  FilterOutlined,
  AlertOutlined,
  DownOutlined,
  RightOutlined,
} from '@ant-design/icons';
import type {
  CorrelationRule,
  HeartbeatParams,
} from '@/app/alarm/types/settings';
import {
  Drawer,
  Form,
  Input,
  Select,
  Radio,
  InputNumber,
  Typography,
  message,
  Tooltip,
  Switch,
  Slider,
  Tag,
  Button,
} from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import RulesMatch from '../../components/matchRule';
import CheckPeriod from './cron/checkPeriod';
import AlertTemplate from './alertTemplate';
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
type StrategyType = 'smart_denoise' | 'missing_detection';
type FilterType = 'all' | 'filter';

interface FormValues {
  name: string;
  organization: string[];
  assign_organization?: string;
  filter_rules: Array<Array<{ key: string; operator: string; value: string | number }>>;
  self_healing_observation_time?: number;
  auto_close_time?: number;
  md_cron_expr?: string;
  md_grace_period?: number;
  md_alert_title?: string;
  md_alert_level?: string;
  md_alert_description?: string;
  md_auto_recovery?: boolean;
  md_activation_mode?: 'first_heartbeat' | 'immediate';
}

const SectionTitle: React.FC<{ title: React.ReactNode }> = ({ title }) => (
  <div className="mb-3 mt-5 flex items-center">
    <div className="mr-2 h-[16px] w-[3px] rounded-sm bg-blue-500" />
    <span className="text-[15px] font-medium text-gray-700">{title}</span>
  </div>
);

const POLICY_PRESETS: Record<
  PolicyType,
  { dimensions: AggregationDimension[]; window: number }
> = {
  service: {
    dimensions: ['service', 'location', 'resource_name', 'item'],
    window: 2,
  },
  location: {
    dimensions: ['location', 'service', 'resource_name', 'item'],
    window: 5,
  },
  resource_name: {
    dimensions: ['resource_name', 'service', 'location', 'item'],
    window: 5,
  },
  other: { dimensions: ['service'], window: 5 },
};

const DIMENSION_OPTIONS: AggregationDimension[] = [
  'service',
  'location',
  'resource_name',
  'item',
];

const DEFAULT_FILTER_RULES = [[{ key: 'source_id', operator: 'eq', value: '' }]];

const MISSING_DETECTION_FORM_RULE_LIST = [
  { name: 'title', verbose_name: '标题' },
  { name: 'source_id', verbose_name: '告警源' },
  { name: 'level', verbose_name: '级别' },
  { name: 'resource_type', verbose_name: '类型对象' },
  { name: 'resource_id', verbose_name: '对象实例' },
  { name: 'description', verbose_name: '内容' },
  { name: 'service', verbose_name: '服务' },
  { name: 'location', verbose_name: '位置' },
  { name: 'resource_name', verbose_name: '资源名称' },
  { name: 'item', verbose_name: '指标' },
];

const MISSING_DETECTION_INITIAL_CONDITION_LISTS: Record<
  string,
  { name: string; desc: string }[]
> = {
  title: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
  source_id: [{ name: 'eq', desc: '等于' }],
  level: [{ name: 'eq', desc: '等于' }],
  resource_type: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
  resource_id: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
  description: [
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
  service: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
  location: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
  resource_name: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
  item: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
};

const DEFAULT_MISSING_VALUES: Pick<
  FormValues,
  | 'md_cron_expr'
  | 'md_grace_period'
  | 'md_alert_title'
  | 'md_alert_level'
  | 'md_alert_description'
  | 'md_auto_recovery'
  | 'md_activation_mode'
> = {
  md_cron_expr: '0 9 * * *',
  md_grace_period: 20,
  md_alert_title: '',
  md_alert_level: undefined,
  md_alert_description: '',
  md_auto_recovery: true,
  md_activation_mode: 'first_heartbeat',
};

interface DraggableTagProps {
  id: string;
  onClose: (e?: React.MouseEvent<HTMLElement>) => void;
}

const DraggableTag: React.FC<DraggableTagProps> = ({ id, onClose }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });

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
        className="mr-1 cursor-grab"
        onMouseDown={(e) => e.stopPropagation()}
      />
      {id}
    </Tag>
  );
};

const isMissingDetectionParams = (
  params?: CorrelationRule['params']
): params is HeartbeatParams => {
  return !!params && 'check_mode' in params;
};

export function normalizeMissingDetectionValues(
  rule?: CorrelationRule
): Partial<FormValues> {
  if (!rule || !isMissingDetectionParams(rule.params)) {
    return DEFAULT_MISSING_VALUES;
  }

  const params = rule.params;

  return {
    md_cron_expr: params.cron_expr || '',
    md_grace_period: params.grace_period,
    md_alert_title: params.alert_template?.title || '',
    md_alert_level: params.alert_template?.level || undefined,
    md_alert_description: params.alert_template?.description || '',
    md_auto_recovery: params.auto_recovery,
    md_activation_mode: params.activation_mode,
  };
}

export function buildMissingDetectionPayload(values: FormValues): CorrelationRule {
  return {
    id: 0,
    created_at: '',
    updated_at: '',
    created_by: '',
    updated_by: '',
    name: values.name,
    strategy_type: 'missing_detection',
    team: values.organization || [],
    dispatch_team: values.assign_organization ? [values.assign_organization] : [],
    match_rules: values.filter_rules || [],
    params: {
      check_mode: 'cron',
      cron_expr: values.md_cron_expr || '',
      grace_period: values.md_grace_period || 0,
      activation_mode: values.md_activation_mode || 'first_heartbeat',
      auto_recovery: values.md_auto_recovery ?? true,
      alert_template: {
        title: values.md_alert_title || '',
        level: values.md_alert_level || '',
        description: values.md_alert_description || '',
      },
    },
    auto_close: false,
    close_minutes: 120,
  };
}

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const [form] = Form.useForm<FormValues>();
  const activationMode =
    Form.useWatch('md_activation_mode', form) ?? DEFAULT_MISSING_VALUES.md_activation_mode;
  const [submitLoading, setSubmitLoading] = useState(false);
  const { createCorrelationRule, updateCorrelationRule } = useSettingApi();

  const [strategyType, setStrategyType] = useState<StrategyType>('smart_denoise');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [policy, setPolicy] = useState<PolicyType>('service');
  const [dimensions, setDimensions] = useState<AggregationDimension[]>([
    'service',
    'location',
    'resource_name',
    'item',
  ]);
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
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const strategyCards = useMemo(
    () => [
      {
        value: 'smart_denoise' as StrategyType,
        icon: FilterOutlined,
        labelKey: 'noiseReduction',
        descKey: 'noiseReductionDesc',
      },
      {
        value: 'missing_detection' as StrategyType,
        icon: AlertOutlined,
        labelKey: 'missingDetection',
        descKey: 'missingDetectionDesc',
      },
    ],
    []
  );

  const defaultFormValues = useMemo(
    () => ({
      name: '',
      organization: selectedGroup ? [selectedGroup.id] : [],
      assign_organization: selectedGroup?.id,
      filter_rules: DEFAULT_FILTER_RULES,
      self_healing_observation_time: 60,
      auto_close_time: 120,
      ...DEFAULT_MISSING_VALUES,
    }),
    [selectedGroup]
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    form.resetFields();

    if (currentRow) {
      const row = currentRow;
      const nextType: StrategyType =
        row.strategy_type === 'missing_detection'
          ? 'missing_detection'
          : 'smart_denoise';
      const nextFilterType: FilterType =
        nextType === 'missing_detection'
          ? 'filter'
          : row.match_rules?.length
            ? 'filter'
            : 'all';

      setStrategyType(nextType);
      setFilterType(nextFilterType);
      setPolicy((row.params && 'policy' in row.params && row.params.policy) || 'service');
      setDimensions(
        (row.params && 'group_by' in row.params && row.params.group_by) || [
          'service',
          'location',
          'resource_name',
          'item',
        ]
      );
      setDetectionWindow(
        (row.params && 'window_size' in row.params && row.params.window_size) || 5
      );
      setSelfHealingEnabled(
        Boolean(row.params && 'time_out' in row.params && row.params.time_out)
      );
      setAutoCloseEnabled(row.auto_close ?? true);
      setDetailExpanded(false);

      form.setFieldsValue({
        name: row.name,
        organization: row.team || [],
        assign_organization: row.dispatch_team?.[0],
        filter_rules: row.match_rules?.length
          ? row.match_rules
          : DEFAULT_FILTER_RULES,
        self_healing_observation_time:
          row.params && 'time_minutes' in row.params
            ? row.params.time_minutes
            : 60,
        auto_close_time: row.close_minutes ?? 120,
        ...normalizeMissingDetectionValues(row),
      });

      return;
    }

    setStrategyType('smart_denoise');
    setFilterType('all');
    setPolicy('service');
    setDimensions(['service', 'location', 'resource_name', 'item']);
    setDetectionWindow(2);
    setSelfHealingEnabled(false);
    setAutoCloseEnabled(true);
    setDetailExpanded(false);

    form.setFieldsValue(defaultFormValues);
  }, [open, currentRow, form, selectedGroup]);

  const handleStrategyTypeChange = (nextType: StrategyType) => {
    if (nextType === strategyType) {
      return;
    }

    form.resetFields();
    setStrategyType(nextType);
    setFilterType(nextType === 'missing_detection' ? 'filter' : 'all');
    setPolicy('service');
    setDimensions(['service', 'location', 'resource_name', 'item']);
    setDetectionWindow(2);
    setSelfHealingEnabled(false);
    setAutoCloseEnabled(true);
    setDetailExpanded(false);
    form.setFieldsValue(defaultFormValues);
  };

  const handlePolicyChange = (newPolicy: PolicyType) => {
    setPolicy(newPolicy);
    if (newPolicy !== 'other') {
      const preset = POLICY_PRESETS[newPolicy];
      setDimensions(preset.dimensions);
      setDetectionWindow(preset.window);
    }
  };

  const handleDimensionChange = (selected: AggregationDimension[]) => {
    if (selected.length === 0) {
      return;
    }
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
    if (value === null) {
      return;
    }
    setDetectionWindow(value);
  };

  const handleFinish = async (values: FormValues) => {
    setSubmitLoading(true);
    try {
      const payload =
        strategyType === 'missing_detection'
          ? {
            name: values.name,
            strategy_type: 'missing_detection' as const,
            description: '',
            team: values.organization || [],
            dispatch_team: values.assign_organization
              ? [values.assign_organization]
              : [],
            match_rules: values.filter_rules || [],
            params: buildMissingDetectionPayload(values).params,
            auto_close: false,
            close_minutes: 120,
          }
          : {
            name: values.name,
            strategy_type: 'smart_denoise' as const,
            description: '',
            team: values.organization || [],
            dispatch_team: values.assign_organization
              ? [values.assign_organization]
              : [],
            match_rules:
                filterType === 'filter' ? values.filter_rules || [] : [],
            params: {
              policy,
              group_by: dimensions,
              window_size: detectionWindow,
              time_out: selfHealingEnabled,
              time_minutes: selfHealingEnabled
                ? values.self_healing_observation_time
                : undefined,
            },
            auto_close: autoCloseEnabled,
            close_minutes: autoCloseEnabled ? values.auto_close_time : undefined,
          };

      if (currentRow?.id) {
        await updateCorrelationRule(currentRow.id, payload);
      } else {
        await createCorrelationRule(payload);
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
      title={
        currentRow
          ? t('settings.correlation.editStrategy')
          : t('settings.correlation.addStrategy')
      }
      width={720}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={submitLoading}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" loading={submitLoading} onClick={() => form.submit()}>
            {t('common.confirm')}
          </Button>
        </div>
      }
    >
      <Form<FormValues>
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        className="text-sm"
      >
        <div className="mb-4 flex gap-3">
          {strategyCards.map(({ value, icon: Icon, labelKey, descKey }) => {
            const isSelected = strategyType === value;

            return (
              <div
                key={value}
                className={`relative cursor-pointer rounded-lg border px-3 py-3 transition-all duration-200 ${
                  isSelected
                    ? 'border-blue-400 bg-gradient-to-br from-blue-50 to-blue-50/30 shadow-md ring-1 ring-blue-200/50'
                    : 'border-gray-200 bg-white hover:border-blue-200 hover:shadow-sm'
                }`}
                style={{ width: 'calc(50% - 6px)' }}
                onClick={() => handleStrategyTypeChange(value)}
              >
                {isSelected && (
                  <div className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600 shadow-sm">
                    <CheckOutlined className="text-white" style={{ fontSize: 10 }} />
                  </div>
                )}
                <div className="mb-2 flex justify-center">
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all ${
                      isSelected
                        ? 'bg-gradient-to-br from-blue-100 to-blue-50 shadow-sm'
                        : 'border border-gray-100 bg-gray-50'
                    }`}
                  >
                    <Icon
                      className={`text-lg ${
                        isSelected ? 'text-blue-600' : 'text-gray-500'
                      }`}
                    />
                  </div>
                </div>
                <div
                  className={`text-center text-sm font-medium transition-colors ${
                    isSelected ? 'text-blue-700' : 'text-gray-700'
                  }`}
                >
                  {t(`settings.correlation.${labelKey}`)}
                </div>
                <div className="mt-0.5 line-clamp-2 text-center text-xs text-gray-400">
                  {t(`settings.correlation.${descKey}`)}
                </div>
              </div>
            );
          })}
        </div>

        <SectionTitle title={t('settings.correlation.basicConfig')} />
        <div className="mb-4 space-y-4 pl-3">
          <div className="flex items-center">
            <div className="w-[100px] pr-2 text-right text-sm">
              <span className="text-red-500">* </span>
              {t('settings.correlation.policyName')}
            </div>
            <Form.Item
              name="name"
              rules={[{ required: true, message: t('common.inputTip') }]}
              className="mb-0 flex-1"
            >
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
          </div>
          <div className="flex items-center">
            <div className="w-[100px] pr-2 text-right text-sm">
              <span className="text-red-500">* </span>
              {t('settings.correlation.organization')}
            </div>
            <Form.Item
              name="organization"
              rules={[{ required: true, message: t('common.selectTip') }]}
              className="mb-0 flex-1"
            >
              <GroupTreeSelect multiple placeholder={t('common.selectTip')} />
            </Form.Item>
          </div>
          <div className="flex items-center">
            <div className="w-[100px] pr-2 text-right text-sm">
              <span className="text-red-500">* </span>
              {t('settings.correlation.assignOrganization')}
              <Tooltip title={t('settings.correlation.assignOrganizationTip')}>
                <QuestionCircleOutlined className="ml-1 cursor-help text-gray-400" />
              </Tooltip>
            </div>
            <Form.Item
              name="assign_organization"
              rules={[{ required: true, message: t('common.selectTip') }]}
              className="mb-0 flex-1"
            >
              <GroupTreeSelect multiple={false} placeholder={t('common.selectTip')} />
            </Form.Item>
          </div>
        </div>

        <SectionTitle
          title={
            strategyType === 'missing_detection' ? (
              t('settings.correlation.defineMonitorTarget')
            ) : (
              t('settings.correlation.defineEventScope')
            )
          }
        />
        <div className="mb-4 pl-3">
          {strategyType === 'missing_detection' && (
            <Typography.Text type="secondary" className="mb-3 block text-sm leading-5">
              {t('settings.correlation.expectedEventGuide')}
            </Typography.Text>
          )}
          {strategyType === 'missing_detection' ? null : (
            <Radio.Group
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              size="small"
              className="mb-4"
            >
              <Radio.Button value="all">
                {t('settings.correlation.all')}
              </Radio.Button>
              <Radio.Button value="filter">
                {t('settings.correlation.filter')}
              </Radio.Button>
            </Radio.Group>
          )}
          {(filterType === 'filter' || strategyType === 'missing_detection') && (
            <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50/80 p-3">
              <Form.Item
                name="filter_rules"
                className="mb-0"
                rules={
                  strategyType === 'missing_detection'
                    ? [
                      {
                        validator: async (_, value) => {
                          if (
                            !value ||
                              !Array.isArray(value) ||
                              value.length === 0 ||
                              !value.some(
                                (group) =>
                                  Array.isArray(group) &&
                                  group.some(
                                    (item) => item?.key && item?.operator && item?.value !== undefined && item?.value !== ''
                                  )
                              )
                          ) {
                            throw new Error(t('settings.correlation.filterRequired'));
                          }
                        },
                      },
                    ]
                    : undefined
                }
              >
                <RulesMatch
                  ruleOptions={
                    strategyType === 'missing_detection'
                      ? MISSING_DETECTION_FORM_RULE_LIST
                      : undefined
                  }
                  conditionOptions={
                    strategyType === 'missing_detection'
                      ? MISSING_DETECTION_INITIAL_CONDITION_LISTS
                      : undefined
                  }
                />
              </Form.Item>
            </div>
          )}
        </div>

        {strategyType === 'smart_denoise' ? (
          <>
            <SectionTitle title={t('settings.correlation.noiseReductionStrategy')} />
            <div className="pl-3">
              <Radio.Group
                value={policy}
                onChange={(e) => handlePolicyChange(e.target.value)}
                size="small"
                className="mb-3"
              >
                <Radio value="service">{t('settings.correlation.applicationFirst')}</Radio>
                <Radio value="location">{t('settings.correlation.infraFirst')}</Radio>
                <Radio value="resource_name">
                  {t('settings.correlation.instanceFirst')}
                </Radio>
                <Radio value="other">{t('settings.correlation.custom')}</Radio>
              </Radio.Group>

              <div
                className="mb-2 flex cursor-pointer select-none items-center gap-1 text-sm text-blue-600"
                onClick={() => setDetailExpanded(!detailExpanded)}
              >
                {detailExpanded ? (
                  <DownOutlined className="text-xs" />
                ) : (
                  <RightOutlined className="text-xs" />
                )}
                <span>{t('settings.correlation.detailConfig')}</span>
              </div>

              {detailExpanded && (
                <div className="space-y-4 rounded-lg border border-slate-100 bg-slate-50/80 p-4">
                  <div className="flex items-center">
                    <div className="w-[72px] shrink-0 text-[13px] text-slate-600">
                      {t('settings.correlation.aggregationDimension')}
                    </div>
                    <div className="flex-1">
                      <DndContext
                        sensors={sensors}
                        collisionDetection={closestCenter}
                        onDragEnd={handleDragEnd}
                      >
                        <SortableContext
                          items={dimensions}
                          strategy={horizontalListSortingStrategy}
                        >
                          <Select
                            mode="multiple"
                            placeholder={t('common.selectTip')}
                            value={dimensions}
                            style={{ width: '100%' }}
                            onChange={(selected) =>
                              handleDimensionChange(selected as AggregationDimension[])
                            }
                            options={DIMENSION_OPTIONS.map((d) => ({
                              value: d,
                              label: t(`settings.correlation.${d === 'resource_name' ? 'resourceName' : d}`),
                            }))}
                            tagRender={({ value, onClose }) => (
                              <DraggableTag
                                id={value as string}
                                onClose={(e) => {
                                  if (dimensions.length > 1) {
                                    onClose(e);
                                  }
                                }}
                              />
                            )}
                          />
                        </SortableContext>
                      </DndContext>
                    </div>
                  </div>

                  <div className="flex items-center">
                    <div className="w-[72px] shrink-0 text-[13px] text-slate-600">
                      {t('settings.correlation.detectionWindow')}
                    </div>
                    <div className="flex flex-1 items-center gap-3">
                      <div className="flex-1 px-1">
                        <Slider
                          min={1}
                          max={15}
                          marks={windowMarks}
                          value={detectionWindow}
                          onChange={handleWindowChange}
                          tooltip={{
                            formatter: (val) => `${val} ${t('settings.correlation.min')}`,
                          }}
                        />
                      </div>
                      <InputNumber
                        min={1}
                        max={15}
                        value={detectionWindow}
                        onChange={handleWindowChange}
                        addonAfter="min"
                        style={{ width: 100 }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <SectionTitle title={t('settings.correlation.selfHealing')} />
            <div className="pl-3">
              <Switch
                size="small"
                checked={selfHealingEnabled}
                onChange={setSelfHealingEnabled}
                className="mb-3"
              />
              {selfHealingEnabled && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center text-sm text-gray-600">
                    {t('settings.correlation.observationTime')}
                    <Tooltip title={t('settings.correlation.observationTimeTip')}>
                      <QuestionCircleOutlined className="ml-1 text-xs text-gray-400" />
                    </Tooltip>
                  </span>
                  <Form.Item name="self_healing_observation_time" className="mb-0">
                    <InputNumber
                      min={1}
                      max={1440}
                      addonAfter="min"
                      style={{ width: 140 }}
                    />
                  </Form.Item>
                </div>
              )}
            </div>

            <SectionTitle title={t('settings.correlation.autoClose')} />
            <div className="pl-3">
              <Switch
                size="small"
                checked={autoCloseEnabled}
                onChange={setAutoCloseEnabled}
                className="mb-3"
              />
              {autoCloseEnabled && (
                <div className="flex items-center gap-3">
                  <span className="flex items-center text-sm text-gray-600">
                    {t('settings.correlation.autoCloseTime')}
                    <Tooltip title={t('settings.correlation.autoCloseTip')}>
                      <QuestionCircleOutlined className="ml-1 text-xs text-gray-400" />
                    </Tooltip>
                  </span>
                  <Form.Item name="auto_close_time" className="mb-0">
                    <InputNumber
                      min={1}
                      max={10080}
                      addonAfter="min"
                      style={{ width: 140 }}
                    />
                  </Form.Item>
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <SectionTitle title={t('settings.correlation.checkPeriod')} />
            <div className="pl-3">
              <CheckPeriod />
            </div>

            <SectionTitle title={t('settings.correlation.activationRules')} />
            <div className="pl-3">
              <div className="space-y-2">
                <Form.Item
                  name="md_activation_mode"
                  rules={[{ required: true, message: t('common.selectTip') }]}
                  className="mb-0"
                >
                  <Radio.Group>
                    <Radio value="first_heartbeat">
                      {t('settings.correlation.firstHeartbeatActivation')}
                    </Radio>
                    <Radio value="immediate">
                      {t('settings.correlation.immediateActivation')}
                    </Radio>
                    </Radio.Group>
                </Form.Item>
                <Typography.Text type="secondary" className="mt-1 block text-sm leading-5">
                  {t(
                    activationMode === 'immediate'
                      ? 'settings.correlation.immediateActivationTip'
                      : 'settings.correlation.firstHeartbeatActivationTip'
                  )}
                </Typography.Text>
              </div>
            </div>

            <SectionTitle title={t('settings.correlation.recoveryRules')} />
            <div className="pl-3">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="flex items-center text-sm text-gray-600">
                    {t('settings.correlation.autoRecovery')}
                    <Tooltip title={t('settings.correlation.autoRecoveryTip')}>
                      <QuestionCircleOutlined className="ml-1 cursor-help text-xs text-gray-400" />
                    </Tooltip>
                  </span>
                  <Form.Item
                    name="md_auto_recovery"
                    valuePropName="checked"
                    className="mb-0"
                  >
                    <Switch size="small" />
                  </Form.Item>
                </div>
              </div>
            </div>

            <SectionTitle title={t('settings.correlation.alertTemplate')} />
            <div className="pl-3">
              <AlertTemplate />
            </div>
          </>
        )}
      </Form>
    </Drawer>
  );
};

export default OperateModal;
