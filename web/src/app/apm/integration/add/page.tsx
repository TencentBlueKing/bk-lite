'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  CopyOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  StopOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import OrganizationAssignmentModal from '@/app/apm/components/organization-assignment-modal';
import type {
  ApmIngestSnippet,
  ApmIngestSnippetInput,
  ApmIngestSource,
  ApmIngestSourceInput,
  ApmIngestSourceWithCredential,
} from '@/app/apm/types';
import GroupTreeSelect from '@/components/group-tree-select';
import Permission from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

const LANGUAGE_OPTIONS = [
  { value: 'python', label: 'Python' },
  { value: 'java', label: 'Java' },
  { value: 'nodejs', label: 'Node.js' },
  { value: 'go', label: 'Go' },
] satisfies { value: ApmIngestSnippetInput['language']; label: string }[];

const RUNTIME_OPTIONS = [
  { value: 'kubernetes', label: 'Kubernetes Pod' },
  { value: 'docker', label: 'Docker 容器' },
  { value: 'host', label: '固定主机' },
  { value: 'other', label: '其他运行环境' },
] satisfies { value: ApmIngestSnippetInput['runtime']; label: string }[];

type SecretState = Pick<ApmIngestSourceWithCredential, 'credential'> & {
  source: ApmIngestSource;
};

type PageState = CatalogStateKind | 'ready';

function publicOtlpEndpoint(ingestType: ApmIngestSource['ingest_type']) {
  if (typeof window === 'undefined') return ingestType === 'otlp_grpc' ? 'http://localhost:4317' : 'http://localhost:4318';
  const port = ingestType === 'otlp_grpc' ? '4317' : '4318';
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(textarea);
  if (!copied) throw new Error('clipboard unavailable');
}

export default function ApmIntegrationAddPage() {
  const {
    getIngestSources,
    createIngestSource,
    rotateIngestSource,
    disableIngestSource,
    setIngestSourceOrganizations,
    getIngestSnippet,
    isLoading: authLoading,
  } = useApmApi();
  const { flatGroups, selectedGroup } = useUserInfoContext();
  const [sources, setSources] = useState<ApmIngestSource[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [stateDescription, setStateDescription] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [secret, setSecret] = useState<SecretState | null>(null);
  const [snippet, setSnippet] = useState<ApmIngestSnippet | null>(null);
  const [snippetSubmitting, setSnippetSubmitting] = useState(false);
  const [organizationSource, setOrganizationSource] = useState<ApmIngestSource | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);
  const [createForm] = Form.useForm<ApmIngestSourceInput>();
  const [snippetForm] = Form.useForm<Omit<ApmIngestSnippetInput, 'credential'>>();

  const groupNames = useMemo(
    () => new Map(flatGroups.map((group) => [Number(group.id), group.name])),
    [flatGroups]
  );

  const loadSources = useCallback(async () => {
    setState('loading');
    setStateDescription('');
    try {
      const data = await getIngestSources();
      setSources(data);
      setState(data.length ? 'ready' : 'empty');
    } catch (error) {
      setState(catalogErrorKind(error));
      setStateDescription(error instanceof Error ? error.message : '接入源加载失败');
    }
  }, [getIngestSources]);

  useEffect(() => {
    if (authLoading) return;
    void loadSources();
  }, [authLoading, loadSources]);

  useEffect(() => {
    if (!secret) return;
    setSnippet(null);
    snippetForm.setFieldsValue({
      language: 'python',
      runtime: 'kubernetes',
      endpoint: publicOtlpEndpoint(secret.source.ingest_type),
      service_namespace: '',
      service_name: secret.source.name,
      environment: secret.source.environment_hint || 'production',
    });
  }, [secret, snippetForm]);

  const revealCredential = useCallback((created: ApmIngestSourceWithCredential) => {
    const { credential, ...source } = created;
    setSecret({ credential, source });
  }, []);

  const submitCreate = useCallback(async (values: ApmIngestSourceInput) => {
    setCreateSubmitting(true);
    try {
      const created = await createIngestSource(values);
      setCreateOpen(false);
      createForm.resetFields();
      revealCredential(created);
      message.success('接入源已创建');
      await loadSources();
    } finally {
      setCreateSubmitting(false);
    }
  }, [createForm, createIngestSource, loadSources, revealCredential]);

  const rotate = useCallback(async (source: ApmIngestSource) => {
    const rotated = await rotateIngestSource(source.id);
    revealCredential(rotated);
    message.success('凭证已轮换，旧凭证将在边缘短缓存过期后失效');
    await loadSources();
  }, [loadSources, revealCredential, rotateIngestSource]);

  const disable = useCallback(async (source: ApmIngestSource) => {
    await disableIngestSource(source.id);
    message.success('接入源已禁用');
    await loadSources();
  }, [disableIngestSource, loadSources]);

  const openOrganizations = useCallback((source: ApmIngestSource) => {
    setOrganizationSource(source);
  }, []);

  const submitOrganizations = useCallback(async (organizationIds: number[]) => {
    if (!organizationSource) return;
    setOrganizationSubmitting(true);
    try {
      await setIngestSourceOrganizations(organizationSource.id, organizationIds);
      setOrganizationSource(null);
      message.success('接入源组织已更新');
      await loadSources();
    } finally {
      setOrganizationSubmitting(false);
    }
  }, [loadSources, organizationSource, setIngestSourceOrganizations]);

  const generateSnippet = useCallback(async (values: Omit<ApmIngestSnippetInput, 'credential'>) => {
    if (!secret) return;
    setSnippetSubmitting(true);
    try {
      setSnippet(await getIngestSnippet(secret.source.id, { ...values, credential: secret.credential }));
    } finally {
      setSnippetSubmitting(false);
    }
  }, [getIngestSnippet, secret]);

  const copy = useCallback(async (value: string, label: string) => {
    try {
      await copyText(value);
      message.success(`${label}已复制`);
    } catch {
      message.error(`${label}复制失败，请手动选择复制`);
    }
  }, []);

  const closeSecret = useCallback(() => {
    Modal.confirm({
      title: '确认关闭一次性凭证？',
      content: '关闭后无法再次查看此 Token 或生成包含它的片段；如遗失只能轮换凭证。',
      okText: '确认关闭',
      cancelText: '继续配置',
      okButtonProps: { danger: true },
      onOk: () => {
        setSecret(null);
        setSnippet(null);
        snippetForm.resetFields();
      },
    });
  }, [snippetForm]);

  const columns = useMemo<ColumnsType<ApmIngestSource>>(() => [
    {
      title: '接入源',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, source) => (
        <div>
          <Typography.Text strong>{name}</Typography.Text>
          <Typography.Text type="secondary" className="block text-xs">
            {source.credential_prefix}…
          </Typography.Text>
        </div>
      ),
    },
    {
      title: '协议',
      dataIndex: 'ingest_type',
      key: 'ingest_type',
      width: 125,
      render: (value: ApmIngestSource['ingest_type']) => (
        <Tag color="blue">{value === 'otlp_grpc' ? 'OTLP/gRPC' : 'OTLP/HTTP'}</Tag>
      ),
    },
    {
      title: '环境提示',
      dataIndex: 'environment_hint',
      key: 'environment_hint',
      width: 140,
      render: (value: string) => value || '未指定',
    },
    {
      title: '组织',
      dataIndex: 'organization_ids',
      key: 'organization_ids',
      render: (ids: number[]) => (
        <Space size={[0, 4]} wrap>
          {ids.map((id) => <Tag key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>)}
        </Space>
      ),
    },
    {
      title: '最近上报',
      dataIndex: 'last_received_at',
      key: 'last_received_at',
      width: 180,
      render: (value: string | null) => value ? new Date(value).toLocaleString() : '尚未上报',
    },
    {
      title: '状态',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (enabled: boolean) => <Tag color={enabled ? 'success' : 'default'}>{enabled ? '已启用' : '已禁用'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      fixed: 'right',
      render: (_, source) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/add">
          <Space size="small" wrap>
            <Button type="link" size="small" icon={<SettingOutlined />} onClick={() => openOrganizations(source)}>
              组织
            </Button>
            <Popconfirm
              title={source.is_enabled ? '确认轮换凭证？' : '轮换凭证并重新启用？'}
              description="旧 Token 将失效，新 Token 只展示一次。"
              okText="确认轮换"
              cancelText="取消"
              onConfirm={() => rotate(source)}
            >
              <Button type="link" size="small" icon={<ReloadOutlined />}>轮换</Button>
            </Popconfirm>
            {source.is_enabled && (
              <Popconfirm
                title="确认禁用接入源？"
                description="边缘短缓存过期后，当前 Token 的新上报将被拒绝。"
                okText="确认禁用"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => disable(source)}
              >
                <Button type="link" danger size="small" icon={<StopOutlined />}>禁用</Button>
              </Popconfirm>
            )}
          </Space>
        </Permission>
      ),
    },
  ], [disable, groupNames, openOrganizations, rotate]);

  const tableContent = state !== 'ready' && state !== 'empty'
    ? <CatalogState kind={state} description={stateDescription} />
    : sources.length
      ? <Table rowKey="id" columns={columns} dataSource={sources} pagination={{ pageSize: 20 }} scroll={{ x: 1100 }} />
      : <CatalogState kind="empty" description="当前组织还没有接入源，请先创建一个受控 OTLP 接入。" />;

  return (
    <ApmRouteShell
      title="APM 接入"
      description="创建受控 OTLP 接入源，并生成包含鉴权与动态实例身份的可执行配置。"
    >
      <div className="flex flex-col gap-4">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <Typography.Text strong className="block text-sm">受控接入源</Typography.Text>
              <Typography.Text type="secondary" className="text-xs">
                每个来源使用独立 Token；轮换或禁用不会删除已经存储的遥测数据。
              </Typography.Text>
            </div>
            <Space wrap>
              <Link href="/apm/integration/instances">
                <Button icon={<UnorderedListOutlined />}>查看接入实例</Button>
              </Link>
              <Button icon={<ReloadOutlined />} onClick={() => void loadSources()}>刷新</Button>
              <Permission requiredPermissions={['Operate']} permissionPath="/apm/integration/add">
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => {
                    createForm.setFieldsValue({
                      ingest_type: 'otlp_http',
                      organization_ids: selectedGroup ? [Number(selectedGroup.id)] : [],
                      environment_hint: 'production',
                    });
                    setCreateOpen(true);
                  }}
                >
                  创建接入源
                </Button>
              </Permission>
            </Space>
          </div>
        </ApmSurface>

        <ApmSurface padding="none">{tableContent}</ApmSurface>

        <Alert
          type="info"
          showIcon
          message="接入凭证只在创建或轮换成功时展示一次；实例 ID 必须按 Pod、容器或主机动态生成，不能在多个副本间复用。"
        />
      </div>

      <Modal
        title="创建 APM 接入源"
        open={createOpen}
        okText="创建并生成 Token"
        cancelText="取消"
        confirmLoading={createSubmitting}
        onOk={() => createForm.submit()}
        onCancel={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical" onFinish={submitCreate} preserve={false}>
          <Form.Item name="name" label="接入源名称" rules={[{ required: true, message: '请输入接入源名称' }, { max: 128 }]}>
            <Input placeholder="例如：结算服务生产环境" autoComplete="off" />
          </Form.Item>
          <Form.Item name="organization_ids" label="可用组织" rules={[{ required: true, message: '请至少选择一个组织' }]}>
            <GroupTreeSelect multiple mode="ownership" showSearch placeholder="选择可管理此接入源的组织" />
          </Form.Item>
          <Form.Item name="ingest_type" label="上报协议" rules={[{ required: true }]}>
            <Select options={[
              { value: 'otlp_http', label: 'OTLP/HTTP (protobuf)' },
              { value: 'otlp_grpc', label: 'OTLP/gRPC' },
            ]} />
          </Form.Item>
          <Form.Item name="environment_hint" label="默认环境提示" rules={[{ max: 128 }]}>
            <Input placeholder="production" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={<Space><KeyOutlined />一次性接入凭证与配置</Space>}
        open={Boolean(secret)}
        width={820}
        footer={<Button danger onClick={closeSecret}>我已保存，关闭并清除</Button>}
        closable={false}
        maskClosable={false}
        keyboard={false}
      >
        {secret && (
          <div className="flex flex-col gap-4">
            <Alert
              type="warning"
              showIcon
              message="Token 仅在本窗口显示一次"
              description="请立即复制并安全注入运行环境。关闭或刷新后平台无法恢复明文，只能轮换。"
            />
            <Input.Password
              value={secret.credential}
              readOnly
              visibilityToggle
              addonBefore="Bearer Token"
              addonAfter={<Button type="text" size="small" icon={<CopyOutlined />} onClick={() => void copy(secret.credential, 'Token')}>复制</Button>}
            />
            <ApmSurface padding="compact">
              <Typography.Text strong>生成可执行接入片段</Typography.Text>
              <Form
                form={snippetForm}
                layout="vertical"
                className="mt-3"
                onFinish={generateSnippet}
              >
                <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
                  <Form.Item name="language" label="语言 / SDK" rules={[{ required: true }]}>
                    <Select options={LANGUAGE_OPTIONS} />
                  </Form.Item>
                  <Form.Item name="runtime" label="运行环境" rules={[{ required: true }]}>
                    <Select options={RUNTIME_OPTIONS} />
                  </Form.Item>
                  <Form.Item name="service_namespace" label="服务命名空间" rules={[{ max: 256 }]}>
                    <Input placeholder="shop（可留空）" />
                  </Form.Item>
                  <Form.Item name="service_name" label="服务名称" rules={[{ required: true, message: '请输入服务名称' }, { max: 256 }]}>
                    <Input placeholder="checkout" />
                  </Form.Item>
                  <Form.Item name="environment" label="部署环境" rules={[{ required: true, message: '请输入部署环境' }, { max: 256 }]}>
                    <Input placeholder="production" />
                  </Form.Item>
                  <Form.Item name="endpoint" label="OTLP 公网端点" rules={[{ required: true, type: 'url', message: '请输入有效的 HTTP/HTTPS URL' }]}>
                    <Input placeholder="https://apm.example.com:4318" />
                  </Form.Item>
                </div>
                <Button htmlType="submit" type="primary" loading={snippetSubmitting} icon={<SafetyCertificateOutlined />}>
                  验证 Token 并生成片段
                </Button>
              </Form>
            </ApmSurface>
            {snippet && (
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <Typography.Text strong>Shell 接入片段</Typography.Text>
                  <Button icon={<CopyOutlined />} onClick={() => void copy(snippet.code, '接入片段')}>复制片段</Button>
                </div>
                <Input.TextArea value={snippet.code} readOnly autoSize={{ minRows: 10, maxRows: 18 }} className="font-mono text-xs" />
              </div>
            )}
          </div>
        )}
      </Modal>

      <OrganizationAssignmentModal
        open={Boolean(organizationSource)}
        title={`调整组织${organizationSource ? `：${organizationSource.name}` : ''}`}
        organizationIds={organizationSource?.organization_ids ?? []}
        submitting={organizationSubmitting}
        description="继承此接入源组织的实例会同步更新；自定义组织实例不受影响。"
        onCancel={() => setOrganizationSource(null)}
        onSubmit={submitOrganizations}
      />
    </ApmRouteShell>
  );
}
