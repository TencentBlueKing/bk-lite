'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import {
  Button,
  Drawer,
  Form,
  Grid,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Progress,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import { formatLatency, formatPercentage } from '@/app/apm/components/metric-format';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type {
  ApmService,
  ApmSliType,
  ApmSlo,
  ApmSloEvaluationWindow,
  ApmSloInput,
} from '@/app/apm/types';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import FilterToolbar from '@/components/filter-toolbar';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

interface SloFormValues {
  name: string;
  service_id: string;
  endpoint?: string;
  environment: string;
  sli_type: ApmSliType;
  objective: number;
  latency_threshold_ms?: number;
  evaluation_window: ApmSloEvaluationWindow;
}

const sliI18n: Record<ApmSliType, { id: string; fallback: string }> = {
  availability: { id: 'apm.slo.availability', fallback: '可用性（非错误请求占比）' },
  latency_p95: { id: 'apm.slo.latencyP95', fallback: '时延（P95 小于阈值）' },
  latency_p99: { id: 'apm.slo.latencyP99', fallback: '时延（P99 小于阈值）' },
};

const windowI18n: Record<ApmSloEvaluationWindow, { id: string; fallback: string }> = {
  rolling7d: { id: 'apm.slo.rolling7d', fallback: '滚动 7 天' },
  rolling30d: { id: 'apm.slo.rolling30d', fallback: '滚动 30 天' },
  calendarMonth: { id: 'apm.slo.calendarMonth', fallback: '自然月' },
};

function BudgetProgress({ value }: { value: number | null }) {
  if (value === null) return <Typography.Text type="secondary">—</Typography.Text>;
  const color = value >= 80
    ? 'var(--color-success)'
    : value >= 40
      ? 'var(--theme-color-status-warning)'
      : 'var(--color-fail)';
  return (
    <div className="grid w-full min-w-0 grid-cols-[minmax(72px,1fr)_44px] items-center gap-2.5">
      <Progress className="!mb-0 flex-1" percent={value} showInfo={false} size="small" strokeColor={color} />
      <span className="text-right text-xs tabular-nums text-[var(--color-text-3)]">{formatPercentage(value, 1)}</span>
    </div>
  );
}

function EvaluationTag({ row }: { row: ApmSlo }) {
  const { t } = useTranslation();
  if (!row.is_enabled) return <Tag bordered={false}>{t('apm.slo.disabledTag', '已停用')}</Tag>;
  if (row.data_state === 'unavailable') return <Tag bordered={false} color="error">{t('apm.slo.evalError', '评估异常')}</Tag>;
  if (row.data_state === 'no_data' || row.current_rate === null) return <Tag bordered={false} color="warning">{t('common.noData', '暂无数据')}</Tag>;
  return row.current_rate >= Number(row.objective)
    ? <Tag bordered={false} color="success">{t('apm.services.met', '达标')}</Tag>
    : <Tag bordered={false} color="error">{t('apm.services.unmet', '未达标')}</Tag>;
}

export default function ApmSloPage() {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const { createSlo, deleteSlo, getServices, getSlos, setSloEnabled, updateSlo } = useApmApi();
  const [form] = Form.useForm<SloFormValues>();
  const [rows, setRows] = useState<ApmSlo[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const [sloItems, serviceItems] = await Promise.all([getSlos(), getServices({ include_archived: true })]);
      setRows(sloItems);
      setServices(serviceItems);
      setState(sloItems.length ? 'ready' : 'empty');
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [getServices, getSlos]);

  useEffect(() => {
    void load();
  }, [load]);

  const editingRow = useMemo(
    () => editingId ? rows.find((row) => row.id === editingId) : undefined,
    [editingId, rows],
  );
  const activeServices = useMemo(
    () => services.filter((service) => !service.archived_at),
    [services],
  );
  const serviceOptions = useMemo(() => {
    const options = activeServices.map((service) => ({
      value: service.id,
      label: service.namespace ? `${service.namespace} / ${service.name}` : service.name,
    }));
    if (!editingRow || options.some((option) => option.value === editingRow.service_id)) return options;
    const selectedService = services.find((service) => service.id === editingRow.service_id);
    const selectedName = selectedService?.namespace
      ? `${selectedService.namespace} / ${selectedService.name}`
      : selectedService?.name || `${editingRow.service_namespace} / ${editingRow.service_name}`;
    return [
      ...options,
      {
        value: editingRow.service_id,
        label: t('apm.slo.archivedServiceOption', '{name}（已归档）', { name: selectedName }),
        disabled: true,
      },
    ];
  }, [activeServices, editingRow, services, t]);

  const environmentOptions = useMemo(() => Array.from(new Set([
    ...activeServices.flatMap((service) => service.environment_views.map((view) => view.environment).filter(Boolean)),
    ...(editingRow?.environment ? [editingRow.environment] : []),
  ])).sort().map((value) => ({ value, label: value })), [activeServices, editingRow]);
  const filtered = useMemo(() => {
    const value = keyword.trim().toLowerCase();
    if (!value) return rows;
    return rows.filter((row) => (
      `${row.name} ${row.service_namespace} ${row.service_name} ${row.environment} ${row.endpoint}`
        .toLowerCase()
        .includes(value)
    ));
  }, [keyword, rows]);
  const pageRows = useMemo(
    () => filtered.slice((page - 1) * pageSize, page * pageSize),
    [filtered, page, pageSize],
  );

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditingId(null);
    form.resetFields();
  };

  const openCreateDrawer = () => {
    const firstService = activeServices[0];
    setEditingId(null);
    form.setFieldsValue({
      name: '',
      service_id: firstService?.id,
      environment: firstService?.environment_views[0]?.environment,
      endpoint: '',
      sli_type: 'availability',
      objective: 99.9,
      latency_threshold_ms: undefined,
      evaluation_window: 'rolling30d',
    });
    setDrawerOpen(true);
  };

  const openEditDrawer = (row: ApmSlo) => {
    setEditingId(row.id);
    form.setFieldsValue({
      name: row.name,
      service_id: row.service_id,
      environment: row.environment,
      endpoint: row.endpoint,
      sli_type: row.sli_type,
      objective: Number(row.objective),
      latency_threshold_ms: row.latency_threshold_ms ?? undefined,
      evaluation_window: row.evaluation_window,
    });
    setDrawerOpen(true);
  };

  const submit = async (values: SloFormValues) => {
    const payload: ApmSloInput = {
      ...values,
      is_enabled: editingRow?.is_enabled ?? true,
      endpoint: values.endpoint?.trim() ?? '',
      latency_threshold_ms: values.sli_type === 'availability' ? null : values.latency_threshold_ms,
    };
    setSubmitting(true);
    try {
      if (editingId) {
        await updateSlo(editingId, payload);
        message.success(t('apm.slo.updated', 'SLO 已更新'));
      } else {
        await createSlo(payload);
        message.success(t('apm.slo.created', 'SLO 已创建'));
      }
      closeDrawer();
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  const toggleEnabled = async (row: ApmSlo, enabled: boolean) => {
    setMutatingId(row.id);
    try {
      const updated = await setSloEnabled(row.id, enabled);
      setRows((items) => items.map((item) => (item.id === row.id ? updated : item)));
      message.success(enabled ? t('apm.slo.enabled', 'SLO 已启用') : t('apm.slo.disabled', 'SLO 已停用'));
    } finally {
      setMutatingId(null);
    }
  };

  const remove = async (row: ApmSlo) => {
    setMutatingId(row.id);
    try {
      await deleteSlo(row.id);
      const nextRows = rows.filter((item) => item.id !== row.id);
      setRows(nextRows);
      setState(nextRows.length ? 'ready' : 'empty');
      message.success(t('apm.slo.deleted', 'SLO 已删除'));
    } finally {
      setMutatingId(null);
    }
  };

  const columns: TableColumnsType<ApmSlo> = [
    {
      title: t('apm.slo.name', '名称'),
      dataIndex: 'name',
      width: '22%',
      render: (value, row) => (
        <div className="flex min-w-0 items-center gap-2">
          <EllipsisWithTooltip className="min-w-0 truncate font-medium text-[var(--color-text-1)]" text={value} />
          <EvaluationTag row={row} />
        </div>
      ),
    },
    {
      title: t('apm.slo.target', '目标对象'),
      width: '26%',
      responsive: ['md'],
      render: (_, row) => (
        <Space direction="vertical" size={2} className="!flex w-full min-w-0">
          <EllipsisWithTooltip className="truncate font-medium text-[var(--color-text-1)]" text={`${row.service_namespace ? `${row.service_namespace} / ` : ''}${row.service_name}`} />
          <EllipsisWithTooltip className="truncate text-xs text-[var(--color-text-3)]" text={[row.environment, row.endpoint || t('apm.slo.serviceLevel', '服务级')].join(' · ')} />
        </Space>
      ),
    },
    {
      title: t('apm.slo.sliType', 'SLI 类型'),
      dataIndex: 'sli_type',
      width: '20%',
      responsive: ['xl'],
      render: (value: ApmSliType, row) => (
        <EllipsisWithTooltip
          className="truncate"
          text={row.latency_threshold_ms
            ? `${t(sliI18n[value].id, sliI18n[value].fallback)} · ${t('apm.slo.thresholdMs', '阈值 {duration}', { duration: formatLatency(row.latency_threshold_ms, false, t) })}`
            : t(sliI18n[value].id, sliI18n[value].fallback)}
        />
      ),
    },
    {
      title: t('apm.slo.objective', '目标值'),
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      align: 'right',
      responsive: ['lg'],
      render: (_, row) => (
        <span className="tabular-nums">
          {formatPercentage(row.objective)}
          <span className="ml-1 text-xs text-[var(--color-text-3)]">
            {t(windowI18n[row.evaluation_window].id, windowI18n[row.evaluation_window].fallback)}
          </span>
        </span>
      ),
    },
    {
      title: t('apm.slo.current', '当前表现'),
      dataIndex: 'current_rate',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      align: 'right',
      responsive: ['sm'],
      render: (value: number | null) => value === null ? '—' : <span className="tabular-nums">{formatPercentage(value)}</span>,
    },
    {
      title: t('apm.slo.budget', '错误预算'),
      dataIndex: 'budget_remaining',
      width: APM_TABLE_COLUMN_WIDTHS.progress,
      responsive: ['xxl'],
      render: (value: number | null) => <BudgetProgress value={value} />,
    },
    {
      title: t('apm.slo.enabledCol', '启用'),
      dataIndex: 'is_enabled',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'center',
      render: (_, row) => (
        <Switch
          aria-label={t('apm.slo.toggleAria', '{action} {name}', {
            action: row.is_enabled ? t('apm.slo.disable', '停用') : t('apm.slo.enable', '启用'),
            name: row.name,
          })}
          checked={row.is_enabled}
          loading={mutatingId === row.id}
          size="small"
          onChange={(enabled) => void toggleEnabled(row, enabled)}
        />
      ),
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'actions',
      width: screens.sm ? APM_TABLE_COLUMN_WIDTHS.metricWide : APM_TABLE_COLUMN_WIDTHS.singleAction,
      align: 'right',
      fixed: 'right',
      render: (_, row) => screens.sm ? (
        <Space className="whitespace-nowrap" size={8}>
          <Button className="!px-0" size="small" type="link" onClick={() => openEditDrawer(row)}>{t('common.edit', '编辑')}</Button>
          <Popconfirm
            cancelText={t('common.cancel', '取消')}
            okButtonProps={{ danger: true, loading: mutatingId === row.id }}
            okText={t('common.delete', '删除')}
            title={t('apm.slo.deleteConfirm', '确认删除这个 SLO？')}
            description={t('apm.slo.deleteHint', '删除后将停止目标评估，且无法恢复。')}
            onConfirm={() => remove(row)}
          >
            <Button className="!px-0" danger disabled={mutatingId !== null && mutatingId !== row.id} size="small" type="link">{t('common.delete', '删除')}</Button>
          </Popconfirm>
        </Space>
      ) : (
        <MoreActionsDropdown
          ariaLabel={t('apm.serviceDetail.moreActions', '更多操作')}
          buttonType="link"
          items={[
            {
              key: 'edit',
              label: t('common.edit', '编辑'),
              onClick: () => openEditDrawer(row),
            },
            {
              key: 'delete',
              danger: true,
              disabled: mutatingId !== null && mutatingId !== row.id,
              label: t('common.delete', '删除'),
              confirm: {
                title: t('apm.slo.deleteConfirm', '确认删除这个 SLO？'),
                content: t('apm.slo.deleteHint', '删除后将停止目标评估，且无法恢复。'),
                okText: t('common.delete', '删除'),
                cancelText: t('common.cancel', '取消'),
              },
              onClick: () => remove(row),
            },
          ]}
          stopPropagation
        />
      ),
    },
  ];

  const content = state === 'ready' ? (
    <ApmDataTable
      columns={columns}
      dataSource={pageRows}
      headerAlignment="column"
      pagination={{
        current: page,
        pageSize,
        total: filtered.length,
        pageSizeOptions: [10, 20, 50, 100],
        showSizeChanger: true,
        onChange: (nextPage, nextPageSize) => {
          setPage(nextPageSize === pageSize ? nextPage : 1);
          setPageSize(nextPageSize);
        },
      }}
      rowKey="id"
    />
  ) : state === 'empty' ? (
    <CatalogState
      kind="empty"
      description={t('apm.slo.empty', '还没有 SLO，创建一个目标开始跟踪服务可靠性。')}
      action={<Button disabled={!services.length} type="primary" onClick={openCreateDrawer}>{t('apm.slo.create', '新建 SLO')}</Button>}
    />
  ) : <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => void load()} />;

  return (
    <ApmRouteShell dependency="telemetry" description={t('apm.slo.description', '定义服务可靠性目标，跟踪达标率与错误预算。')} title={t('apm.slo.title', 'SLO')}>
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input
              allowClear
              className="min-w-0 flex-1 md:max-w-sm"
              prefix={<SearchOutlined aria-hidden="true" />}
              placeholder={t('apm.slo.searchPlaceholder', '搜索名称 / 服务 / 端点')}
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value);
                setPage(1);
              }}
            />
            <Space className="ml-auto" size={8}>
              <Button aria-label={t('apm.slo.refresh', '刷新 SLO')} icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={() => void load()} />
              <Button disabled={!services.length} type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={openCreateDrawer}>{t('apm.slo.create', '新建 SLO')}</Button>
            </Space>
          </FilterToolbar>
          {content}
        </div>
      </ApmSurface>
      <Drawer
        destroyOnHidden
        open={drawerOpen}
        title={editingId ? t('apm.slo.edit', '编辑 SLO') : t('apm.slo.create', '新建 SLO')}
        width="min(480px, 100vw)"
        styles={{ body: { maxHeight: 'calc(100vh - 150px)', overflowY: 'auto' } }}
        extra={(
          <Space>
            <Button disabled={submitting} onClick={closeDrawer}>{t('common.cancel', '取消')}</Button>
            <Button form="apm-slo-form" htmlType="submit" loading={submitting} type="primary">{editingId ? t('common.save', '保存') : t('common.create', '创建')}</Button>
          </Space>
        )}
        onClose={closeDrawer}
      >
        <Form<SloFormValues> form={form} id="apm-slo-form" layout="vertical" requiredMark="optional" onFinish={submit}>
          <Form.Item label={t('apm.slo.name', '名称')} name="name" rules={[{ required: true, message: t('apm.slo.nameRequired', '请输入 SLO 名称') }, { max: 128, message: t('apm.slo.nameTooLong', '名称不能超过 128 个字符') }]}>
            <Input maxLength={128} placeholder={t('apm.slo.namePlaceholder', '例如：结算服务可用性')} />
          </Form.Item>
          <Form.Item label={t('apm.slo.targetService', '目标服务')} name="service_id" rules={[{ required: true, message: t('apm.slo.targetServiceRequired', '请选择目标服务') }]}>
            <Select showSearch optionFilterProp="label" placeholder={t('apm.slo.selectTargetService', '选择目标服务')} options={serviceOptions} />
          </Form.Item>
          <Form.Item label={t('apm.common.environment', '环境')} name="environment" extra={t('apm.slo.environmentHint', 'SLO 在单个部署环境内评估。')} rules={[{ required: true, message: t('apm.slo.environmentRequired', '请选择环境') }]}>
            <Select showSearch optionFilterProp="label" placeholder={t('apm.common.selectEnvironment', '选择环境')} options={environmentOptions} />
          </Form.Item>
          <Form.Item label={t('apm.slo.endpoint', '端点')} name="endpoint" extra={t('apm.slo.endpointHint', '留空时按整个服务计算。')}>
            <Input maxLength={512} placeholder={t('apm.slo.endpointPlaceholder', '例如：POST /api/checkout')} />
          </Form.Item>
          <Form.Item label={t('apm.slo.sliType', 'SLI 类型')} name="sli_type" rules={[{ required: true, message: t('apm.slo.sliRequired', '请选择 SLI 类型') }]}>
            <Select options={Object.entries(sliI18n).map(([value, item]) => ({ value, label: t(item.id, item.fallback) }))} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(before, current) => before.sli_type !== current.sli_type}>
            {({ getFieldValue }) => getFieldValue('sli_type') === 'availability' ? null : (
              <Form.Item label={t('apm.slo.latencyThreshold', '时延阈值')} name="latency_threshold_ms" rules={[{ required: true, message: t('apm.slo.latencyRequired', '请输入正数时延阈值') }]}>
                <InputNumber className="!w-full" min={1} precision={0} addonAfter={t('apm.common.millisecondUnit', 'ms')} />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item label={t('apm.slo.objectiveRate', '目标达标率')} name="objective" rules={[{ required: true, message: t('apm.slo.objectiveRequired', '请输入目标达标率') }]}>
            <InputNumber className="!w-full" max={100} min={0.001} precision={3} step={0.1} addonAfter={t('apm.common.percentUnit', '%')} />
          </Form.Item>
          <Form.Item label={t('apm.slo.window', '评估窗口')} name="evaluation_window" rules={[{ required: true, message: t('apm.slo.windowRequired', '请选择评估窗口') }]}>
            <Select options={Object.entries(windowI18n).map(([value, item]) => ({ value, label: t(item.id, item.fallback) }))} />
          </Form.Item>
        </Form>
      </Drawer>
    </ApmRouteShell>
  );
}
