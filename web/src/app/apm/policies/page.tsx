'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PlusOutlined } from '@ant-design/icons';
import {
  Badge,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type {
  ApmPolicy,
  ApmPolicyComparator,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicySeverity,
  ApmService,
  ApmNotificationChannel,
} from '@/app/apm/types';

type PageState = CatalogStateKind | 'ready';

const METRIC_LABELS: Record<ApmPolicyMetric, string> = {
  error_rate: '错误率',
  p95: 'P95 延迟',
  p99: 'P99 延迟',
  throughput: '吞吐',
  no_traffic: '无流量',
};

const COMPARATOR_LABELS: Record<ApmPolicyComparator, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
};

const SEVERITY_LABELS: Record<ApmPolicySeverity, string> = {
  critical: '严重',
  error: '错误',
  warning: '警告',
};

const DEFAULT_POLICY: Partial<ApmPolicyInput> = {
  environment: 'production',
  metric_type: 'error_rate',
  comparator: 'gt',
  threshold: 0.05,
  duration_window: 3,
  recovery_window: 3,
  severity: 'warning',
  notice: false,
  notice_type_ids: [],
  notice_users: [],
  is_enabled: true,
};

export default function ApmPoliciesPage() {
  const {
    createPolicy,
    deletePolicy,
    getPolicies,
    getNotificationChannels,
    getServices,
    isLoading: authLoading,
    setPolicyEnabled,
    testPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<ApmPolicyInput>();
  const [policies, setPolicies] = useState<ApmPolicy[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [notificationChannels, setNotificationChannels] = useState<ApmNotificationChannel[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [editing, setEditing] = useState<ApmPolicy | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    getNotificationChannels()
      .then(setNotificationChannels)
      .catch(() => setNotificationChannels([]));
    Promise.all([getPolicies(), getServices()])
      .then(([policyItems, serviceItems]) => {
        setPolicies(policyItems);
        setServices(serviceItems);
        setState(policyItems.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, getNotificationChannels, getPolicies, getServices]);

  useEffect(() => load(), [load]);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(DEFAULT_POLICY as ApmPolicyInput);
    setModalOpen(true);
  };

  const openEdit = (policy: ApmPolicy) => {
    setEditing(policy);
    form.setFieldsValue({ ...policy, threshold: policy.threshold });
    setModalOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updatePolicy(editing.id, values);
        message.success('策略已更新');
      } else {
        await createPolicy(values);
        message.success('策略已创建');
      }
      setModalOpen(false);
      form.resetFields();
      load();
    } finally {
      setSaving(false);
    }
  };

  const serviceOptions = useMemo(
    () => services.map((service) => ({
      value: service.id,
      label: `${service.namespace || '未归类应用'} / ${service.name}`,
    })),
    [services]
  );

  const columns: TableColumnsType<ApmPolicy> = [
    {
      title: '策略',
      dataIndex: 'name',
      render: (value, policy) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary">
            {policy.service_namespace || '未归类应用'} / {policy.service_name} · {policy.environment || '未设置环境'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '条件',
      responsive: ['sm'],
      render: (_, policy) => (
        <span className="font-mono">
          {METRIC_LABELS[policy.metric_type]} {COMPARATOR_LABELS[policy.comparator]} {policy.threshold}
        </span>
      ),
    },
    {
      title: '窗口',
      width: 150,
      responsive: ['lg'],
      render: (_, policy) => `${policy.duration_window} 次命中 / ${policy.recovery_window} 次恢复`,
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 90,
      responsive: ['lg'],
      render: (value: ApmPolicySeverity) => (
        <Tag bordered={false} color={{ critical: 'red', error: 'orange', warning: 'gold' }[value]}>{SEVERITY_LABELS[value]}</Tag>
      ),
    },
    {
      title: '状态',
      width: 100,
      render: (_, policy) => (
        <Tag bordered={false} color={policy.state?.status === 'firing' ? 'error' : 'success'}>
          {policy.state?.status === 'firing' ? '告警中' : '正常'}
        </Tag>
      ),
    },
    {
      title: '启用',
      width: 90,
      responsive: ['md'],
      render: (_, policy) => (
        <Switch
          checked={policy.is_enabled}
          aria-label={`${policy.name}启用状态`}
          onChange={async (checked) => {
            await setPolicyEnabled(policy.id, checked);
            setPolicies((items) => items.map((item) => (
              item.id === policy.id ? { ...item, is_enabled: checked } : item
            )));
            message.success(checked ? '策略已启用' : '策略已停用');
          }}
        />
      ),
    },
    {
      title: '操作',
      width: 210,
      align: 'right',
      render: (_, policy) => (
        <Space wrap>
          <Button type="link" onClick={() => openEdit(policy)}>编辑</Button>
          <Button
            type="link"
            loading={testingId === policy.id}
            onClick={async () => {
              setTestingId(policy.id);
              try {
                const result = await testPolicy(policy.id);
                message.info(`当前值 ${result.value}，${result.breached ? '已命中阈值' : '未命中阈值'}`);
              } finally {
                setTestingId(null);
              }
            }}
          >
            测试查询
          </Button>
          <Popconfirm
            title="删除策略"
            description="删除后不再评估该策略，确认继续？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              await deletePolicy(policy.id);
              message.success('策略已删除');
              load();
            }}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="APM 策略"
      description="按服务与环境管理阈值策略；告警事实保存在 APM，告警中心可作为 NATS 通知渠道。"
      dependency="control"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Badge
                count={policies.filter((policy) => policy.state?.status === 'firing').length}
                showZero
                color="var(--color-fail)"
              />
              <Typography.Text type="secondary" className="text-xs">
                告警中策略 · 每分钟评估，查询失败时保持上次状态
              </Typography.Text>
            </div>
            <Button
              type="primary"
              icon={<PlusOutlined aria-hidden="true" />}
              onClick={openCreate}
              disabled={!services.length}
            >
              新建策略
            </Button>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={policies}
              pagination={{
                defaultPageSize: 20,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
            />
          ) : (
            <CatalogState
              kind={state}
              description={state === 'empty' ? (services.length ? '当前组织暂无 APM 策略。' : '请先接入并发现服务，再创建策略。') : undefined}
            />
          )}
        </ApmSurface>
      </div>
      <Modal
        title={editing ? '编辑 APM 策略' : '新建 APM 策略'}
        open={modalOpen}
        confirmLoading={saving}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        onOk={submit}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
        }}
        destroyOnHidden
        width={760}
        styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      >
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
            <Input maxLength={256} autoFocus />
          </Form.Item>
          <Form.Item name="service_id" label="服务" rules={[{ required: true, message: '请选择服务' }]}>
            <Select showSearch optionFilterProp="label" options={serviceOptions} />
          </Form.Item>
          <Form.Item name="environment" label="环境" tooltip="没有 deployment.environment 标签时可留空。">
            <Input maxLength={256} placeholder="production" />
          </Form.Item>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="metric_type" label="指标" rules={[{ required: true }]}>
              <Select options={Object.entries(METRIC_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="comparator" label="比较符" rules={[{ required: true }]}>
              <Select options={Object.entries(COMPARATOR_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item
              name="threshold"
              label="阈值"
              tooltip="错误率使用 0–1 小数；延迟单位为毫秒；吞吐单位为请求/秒。"
              rules={[{ required: true, message: '请输入阈值' }]}
            >
              <InputNumber className="w-full" min={0} step={0.01} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="duration_window" label="连续命中次数" rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="recovery_window" label="连续恢复次数" rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="severity" label="告警级别" rules={[{ required: true }]}>
              <Select options={Object.entries(SEVERITY_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </div>
          <Form.Item name="notice" label="发送到告警中心" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(previous, current) => previous.notice !== current.notice}>
            {({ getFieldValue }) => getFieldValue('notice') ? (
              <Form.Item
                name="notice_type_ids"
                label="告警中心 NATS 渠道"
                rules={[{ required: true, message: '请选择告警中心通知渠道' }]}
                extra="这里只发送 APM 事件副本；渠道不可用时，APM 自有告警和事件仍会正常保存。"
              >
                <Select
                  mode="multiple"
                  options={notificationChannels.map((channel) => ({
                    value: channel.id,
                    label: channel.name,
                  }))}
                  placeholder={notificationChannels.length ? '请选择渠道' : '请先在系统管理中配置告警中心 NATS 渠道'}
                />
              </Form.Item>
            ) : null}
          </Form.Item>
          <Form.Item name="is_enabled" label="创建后启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ApmRouteShell>
  );
}
