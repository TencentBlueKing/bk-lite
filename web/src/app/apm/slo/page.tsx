'use client';

import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type {
  ApmService,
  ApmSliType,
  ApmSlo,
  ApmSloEvaluationWindow,
  ApmSloInput,
} from '@/app/apm/types';

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
  is_enabled: boolean;
}

const sliLabels: Record<ApmSliType, string> = {
  availability: '可用性（非错误请求占比）',
  latency_p95: '时延（P95 小于阈值）',
  latency_p99: '时延（P99 小于阈值）',
};

const windowLabels: Record<ApmSloEvaluationWindow, string> = {
  rolling7d: '滚动 7 天',
  rolling30d: '滚动 30 天',
  calendarMonth: '自然月',
};

function BudgetProgress({ value }: { value: number | null }) {
  if (value === null) return <Typography.Text type="secondary">—</Typography.Text>;
  const color = value >= 80
    ? 'var(--color-success)'
    : value >= 40
      ? 'var(--theme-color-status-warning)'
      : 'var(--color-fail)';
  return (
    <div className="flex min-w-40 items-center gap-2">
      <Progress className="!mb-0 flex-1" percent={value} showInfo={false} size="small" strokeColor={color} />
      <span className="w-12 text-right text-xs tabular-nums text-[var(--color-text-3)]">{value.toFixed(1)}%</span>
    </div>
  );
}

function EvaluationTag({ row }: { row: ApmSlo }) {
  if (!row.is_enabled) return <Tag bordered={false}>已停用</Tag>;
  if (row.data_state === 'unavailable') return <Tag bordered={false} color="error">评估异常</Tag>;
  if (row.data_state === 'no_data' || row.current_rate === null) return <Tag bordered={false} color="warning">暂无数据</Tag>;
  return row.current_rate >= Number(row.objective)
    ? <Tag bordered={false} color="success">达标</Tag>
    : <Tag bordered={false} color="error">未达标</Tag>;
}

export default function ApmSloPage() {
  const { createSlo, deleteSlo, getServices, getSlos, setSloEnabled, updateSlo } = useApmApi();
  const [form] = Form.useForm<SloFormValues>();
  const [rows, setRows] = useState<ApmSlo[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const [sloItems, serviceItems] = await Promise.all([getSlos(), getServices()]);
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

  const serviceOptions = useMemo(() => services.map((service) => ({
    value: service.id,
    label: service.namespace ? `${service.namespace} / ${service.name}` : service.name,
  })), [services]);

  const environmentOptions = useMemo(() => Array.from(new Set(services.flatMap((service) =>
    service.environment_views.map((view) => view.environment).filter(Boolean)
  ))).sort().map((value) => ({ value, label: value })), [services]);

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditingId(null);
    form.resetFields();
  };

  const openCreateDrawer = () => {
    const firstService = services[0];
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
      is_enabled: true,
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
      is_enabled: row.is_enabled,
    });
    setDrawerOpen(true);
  };

  const submit = async (values: SloFormValues) => {
    const payload: ApmSloInput = {
      ...values,
      endpoint: values.endpoint?.trim() ?? '',
      latency_threshold_ms: values.sli_type === 'availability' ? null : values.latency_threshold_ms,
    };
    setSubmitting(true);
    try {
      if (editingId) {
        await updateSlo(editingId, payload);
        message.success('SLO 已更新');
      } else {
        await createSlo(payload);
        message.success('SLO 已创建');
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
      message.success(enabled ? 'SLO 已启用' : 'SLO 已停用');
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
      message.success('SLO 已删除');
    } finally {
      setMutatingId(null);
    }
  };

  const columns: TableColumnsType<ApmSlo> = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (value, row) => (
        <Space direction="vertical" size={4}>
          <Typography.Text className="font-medium text-[var(--color-primary)]">{value}</Typography.Text>
          <EvaluationTag row={row} />
        </Space>
      ),
    },
    {
      title: '目标对象',
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Typography.Text>{row.service_namespace ? `${row.service_namespace} / ` : ''}{row.service_name}</Typography.Text>
          <Typography.Text type="secondary" className="!text-xs">
            {[row.environment, row.endpoint || '服务级'].join(' · ')}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: 'SLI 类型',
      dataIndex: 'sli_type',
      width: 210,
      render: (value: ApmSliType, row) => (
        <Space direction="vertical" size={2}>
          <span>{sliLabels[value]}</span>
          {row.latency_threshold_ms ? <Typography.Text type="secondary" className="!text-xs">阈值 {row.latency_threshold_ms} ms</Typography.Text> : null}
        </Space>
      ),
    },
    {
      title: '目标 / 窗口',
      width: 130,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <span className="tabular-nums">{Number(row.objective).toFixed(2)}%</span>
          <Typography.Text type="secondary" className="!text-xs">{windowLabels[row.evaluation_window]}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '当前达标率',
      dataIndex: 'current_rate',
      width: 130,
      render: (value: number | null) => value === null ? '—' : <span className="tabular-nums">{value.toFixed(2)}%</span>,
    },
    {
      title: '错误预算剩余',
      dataIndex: 'budget_remaining',
      width: 210,
      render: (value: number | null) => <BudgetProgress value={value} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <Switch
            aria-label={`${row.is_enabled ? '停用' : '启用'} ${row.name}`}
            checked={row.is_enabled}
            loading={mutatingId === row.id}
            size="small"
            onChange={(enabled) => void toggleEnabled(row, enabled)}
          />
          <Button aria-label={`编辑 ${row.name}`} icon={<EditOutlined aria-hidden="true" />} size="small" type="link" onClick={() => openEditDrawer(row)} />
          <Popconfirm
            cancelText="取消"
            okButtonProps={{ danger: true, loading: mutatingId === row.id }}
            okText="删除"
            title="确认删除这个 SLO？"
            description="删除后将停止目标评估，且无法恢复。"
            onConfirm={() => remove(row)}
          >
            <Button aria-label={`删除 ${row.name}`} danger icon={<DeleteOutlined aria-hidden="true" />} size="small" type="link" />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const content = state === 'ready' ? (
    <Table columns={columns} dataSource={rows} pagination={false} rowKey="id" scroll={{ x: 1120 }} />
  ) : state === 'empty' ? (
    <Empty className="py-14" description="还没有 SLO，创建一个目标开始跟踪服务可靠性。">
      <Button disabled={!services.length} type="primary" onClick={openCreateDrawer}>新建 SLO</Button>
    </Empty>
  ) : <CatalogState kind={state} />;

  return (
    <ApmRouteShell dependency="telemetry" description="定义服务可靠性目标，持续跟踪达标率和错误预算消耗。" title="SLO">
      <ApmSurface className="overflow-hidden" padding="none">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <Typography.Text strong>可靠性目标</Typography.Text>
            <Typography.Text type="secondary" className="ml-2 !text-xs tabular-nums">共 {rows.length} 个</Typography.Text>
          </div>
          <Space>
            <Button aria-label="刷新 SLO" icon={<ReloadOutlined aria-hidden="true" />} onClick={() => void load()} />
            <Button disabled={!services.length} type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={openCreateDrawer}>新建 SLO</Button>
          </Space>
        </div>
        {content}
      </ApmSurface>
      <Drawer
        destroyOnHidden
        open={drawerOpen}
        title={editingId ? '编辑 SLO' : '新建 SLO'}
        width={480}
        styles={{ body: { maxHeight: 'calc(100vh - 150px)', overflowY: 'auto' } }}
        extra={(
          <Space>
            <Button disabled={submitting} onClick={closeDrawer}>取消</Button>
            <Button form="apm-slo-form" htmlType="submit" loading={submitting} type="primary">{editingId ? '保存' : '创建'}</Button>
          </Space>
        )}
        onClose={closeDrawer}
      >
        <Form<SloFormValues> form={form} id="apm-slo-form" layout="vertical" requiredMark="optional" onFinish={submit}>
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入 SLO 名称' }, { max: 128, message: '名称不能超过 128 个字符' }]}>
            <Input maxLength={128} placeholder="例如：结算服务可用性" />
          </Form.Item>
          <Form.Item label="目标服务" name="service_id" rules={[{ required: true, message: '请选择目标服务' }]}>
            <Select showSearch optionFilterProp="label" placeholder="选择目标服务" options={serviceOptions} />
          </Form.Item>
          <Form.Item label="环境" name="environment" extra="SLO 在单个部署环境内评估。" rules={[{ required: true, message: '请选择环境' }]}>
            <Select showSearch optionFilterProp="label" placeholder="选择环境" options={environmentOptions} />
          </Form.Item>
          <Form.Item label="端点（可选）" name="endpoint" extra="留空时按整个服务计算。">
            <Input maxLength={512} placeholder="例如：POST /api/checkout" />
          </Form.Item>
          <Form.Item label="SLI 类型" name="sli_type" rules={[{ required: true, message: '请选择 SLI 类型' }]}>
            <Select options={Object.entries(sliLabels).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(before, current) => before.sli_type !== current.sli_type}>
            {({ getFieldValue }) => getFieldValue('sli_type') === 'availability' ? null : (
              <Form.Item label="时延阈值" name="latency_threshold_ms" rules={[{ required: true, message: '请输入正数时延阈值' }]}>
                <InputNumber className="!w-full" min={1} precision={0} addonAfter="ms" />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item label="目标达标率" name="objective" rules={[{ required: true, message: '请输入目标达标率' }]}>
            <InputNumber className="!w-full" max={100} min={0.001} precision={3} step={0.1} addonAfter="%" />
          </Form.Item>
          <Form.Item label="评估窗口" name="evaluation_window" rules={[{ required: true, message: '请选择评估窗口' }]}>
            <Select options={Object.entries(windowLabels).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item label="启用" name="is_enabled" valuePropName="checked" extra="启用后开始评估目标并计算错误预算。">
            <Switch />
          </Form.Item>
        </Form>
      </Drawer>
    </ApmRouteShell>
  );
}
