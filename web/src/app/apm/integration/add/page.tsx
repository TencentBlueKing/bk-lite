'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import Link from 'next/link';
import {
  ApiOutlined,
  CodeOutlined,
  CopyOutlined,
  ExperimentOutlined,
  GlobalOutlined,
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
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Steps,
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

interface IntegrationMethod {
  key: string;
  title: string;
  description: string;
  badge?: string;
  language?: ApmIngestSnippetInput['language'];
  available: boolean;
}

const INTEGRATION_GROUPS: { key: string; title: string; icon: ReactNode; methods: IntegrationMethod[] }[] = [
  {
    key: 'sdk',
    title: 'SDK',
    icon: <CodeOutlined />,
    methods: [
      { key: 'nodejs', title: 'Node.js', description: '零代码自动探针接入，支持 Express / Nest / Koa / Fastify', badge: '推荐', language: 'nodejs', available: true },
      { key: 'java', title: 'Java', description: '字节码注入零代码接入，支持 Spring / Dubbo / gRPC', badge: '推荐', language: 'java', available: true },
      { key: 'python', title: 'Python', description: '运行时 SDK 接入，支持 Django / Flask / FastAPI', language: 'python', available: true },
      { key: 'dotnet', title: '.NET', description: '基于 OpenTelemetry .NET 自动探针', available: false },
      { key: 'go', title: 'Go', description: '编译期引入 SDK 接入，需要在代码中埋点', language: 'go', available: true },
    ],
  },
  {
    key: 'otel',
    title: 'OpenTelemetry',
    icon: <ApiOutlined />,
    methods: [
      { key: 'otel-collector', title: 'OTel Collector（链路）', description: '复用自建 Collector，通过 exporter 将链路推送至本平台', available: true },
    ],
  },
  {
    key: 'ebpf',
    title: 'eBPF',
    icon: <ExperimentOutlined />,
    methods: [
      { key: 'ebpf-obi', title: 'eBPF 自动注入（OBI）', description: '无需改代码，通过内核态 eBPF 捕获服务链路', badge: '低侵入', available: false },
    ],
  },
  {
    key: 'kubernetes',
    title: 'Kubernetes',
    icon: <GlobalOutlined />,
    methods: [
      { key: 'otel-operator', title: 'Kubernetes 自动注入（OTel Operator）', description: '安装 Operator 后通过 Pod 注解自动注入探针', available: false },
    ],
  },
];

type SecretState = Pick<ApmIngestSourceWithCredential, 'credential'> & {
  source: ApmIngestSource;
};

type PageState = CatalogStateKind | 'ready';
type SnippetMode = 'agent' | 'docker';
type SnippetFormValues = Omit<ApmIngestSnippetInput, 'credential' | 'endpoint' | 'runtime'>;

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
  const [guideMethod, setGuideMethod] = useState<IntegrationMethod | null>(null);
  const [preferredLanguage, setPreferredLanguage] = useState<ApmIngestSnippetInput['language']>();
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [secret, setSecret] = useState<SecretState | null>(null);
  const [snippet, setSnippet] = useState<ApmIngestSnippet | null>(null);
  const [snippetSubmitting, setSnippetSubmitting] = useState(false);
  const [snippetMode, setSnippetMode] = useState<SnippetMode>('agent');
  const [snippetLanguage, setSnippetLanguage] = useState<ApmIngestSnippetInput['language']>('python');
  const [organizationSource, setOrganizationSource] = useState<ApmIngestSource | null>(null);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);
  const [createForm] = Form.useForm<ApmIngestSourceInput>();
  const [snippetForm] = Form.useForm<SnippetFormValues>();

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
    setSnippetMode('agent');
    setSnippetLanguage(preferredLanguage ?? 'python');
    snippetForm.setFieldsValue({
      language: preferredLanguage ?? 'python',
      service_namespace: '',
      service_name: secret.source.name,
      environment: secret.source.environment_hint || 'production',
    });
  }, [preferredLanguage, secret, snippetForm]);

  const openCreate = useCallback((method?: IntegrationMethod) => {
    setPreferredLanguage(method?.language);
    createForm.setFieldsValue({
      ingest_type: 'otlp_http',
      organization_ids: selectedGroup ? [Number(selectedGroup.id)] : [],
      environment_hint: 'production',
    });
    setCreateOpen(true);
  }, [createForm, selectedGroup]);

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
    setPreferredLanguage(undefined);
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

  const generateSnippet = useCallback(async (values: SnippetFormValues) => {
    if (!secret) return;
    setSnippetSubmitting(true);
    try {
      setSnippet(await getIngestSnippet(secret.source.id, {
        ...values,
        credential: secret.credential,
        endpoint: publicOtlpEndpoint(secret.source.ingest_type),
        runtime: snippetMode === 'docker' ? 'docker' : 'host',
      }));
    } finally {
      setSnippetSubmitting(false);
    }
  }, [getIngestSnippet, secret, snippetMode]);

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
        setSnippetMode('agent');
        setSnippetLanguage('python');
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

  const activeLanguage = preferredLanguage ?? snippetLanguage;
  const activeLanguageLabel = LANGUAGE_OPTIONS.find((option) => option.value === activeLanguage)?.label ?? 'SDK';
  const agentModeLabel = {
    python: 'Python 自动探针',
    nodejs: 'Node.js 自动探针',
    java: 'Java Agent',
    go: 'Go SDK',
  }[activeLanguage];
  const assignedEndpoint = secret ? publicOtlpEndpoint(secret.source.ingest_type) : '';

  return (
    <ApmRouteShell
      title="接入方式总览"
      description="按语言和运行环境选择接入方式，再创建受控 OTLP 接入源与可执行配置。"
    >
      <div className="flex flex-col gap-4">
        {INTEGRATION_GROUPS.map((group) => (
          <section key={group.key} aria-labelledby={`integration-${group.key}`}>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-[var(--color-primary)]" aria-hidden="true">{group.icon}</span>
              <Typography.Title id={`integration-${group.key}`} level={2} className="!m-0 !text-sm !font-semibold">
                {group.title}
              </Typography.Title>
              <Tag bordered={false}>{group.methods.length} 种</Tag>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {group.methods.map((method) => (
                <Card
                  key={method.key}
                  size="small"
                  hoverable
                  className="h-full border-[var(--color-border-2)]"
                  styles={{ body: { height: '100%', padding: 16 } }}
                  role="button"
                  tabIndex={0}
                  onClick={() => setGuideMethod(method)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setGuideMethod(method);
                    }
                  }}
                >
                  <div className="flex h-full min-h-28 flex-col">
                    <div className="flex items-center gap-2">
                      <Typography.Text strong>{method.title}</Typography.Text>
                      {method.badge ? <Tag bordered={false} color={method.available ? 'blue' : 'default'}>{method.badge}</Tag> : null}
                      {!method.available ? <Tag bordered={false}>规划中</Tag> : null}
                    </div>
                    <Typography.Text type="secondary" className="mt-2 block text-xs leading-5">
                      {method.description}
                    </Typography.Text>
                    <Typography.Text className="mt-auto self-start text-xs text-[var(--color-primary)]">
                      查看接入详情 →
                    </Typography.Text>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}

        <Alert
          type="info"
          showIcon
          message="本地 MVP 使用受控 Token 保护 OTLP 入口；凭证仅在创建或轮换后展示一次。"
          description="这与原型中的无业务层鉴权假设不同，当前实现保留已落地的安全边界。"
        />

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
                  onClick={() => openCreate()}
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
        title={guideMethod ? `${guideMethod.title} 接入指南` : '接入指南'}
        open={Boolean(guideMethod)}
        width={720}
        okText={guideMethod?.available ? '创建受控接入源' : '知道了'}
        cancelText="返回目录"
        onCancel={() => setGuideMethod(null)}
        onOk={() => {
          if (guideMethod?.available) {
            const method = guideMethod;
            setGuideMethod(null);
            openCreate(method);
          } else {
            setGuideMethod(null);
          }
        }}
      >
        {guideMethod ? (
          <div className="flex flex-col gap-4">
            <Typography.Paragraph type="secondary">{guideMethod.description}</Typography.Paragraph>
            {guideMethod.available ? (
              <Steps
                direction="vertical"
                size="small"
                items={[
                  { title: '创建接入源', description: '选择组织、协议与默认环境，生成一次性 Token。' },
                  { title: '生成配置', description: '填写服务身份和运行环境，生成对应 SDK 或 Collector 配置。' },
                  { title: '验证上报', description: '启动应用后，在接入列表确认实例最近上报时间和状态。' },
                ]}
              />
            ) : (
              <Alert type="info" showIcon message="当前 MVP 尚未开放此接入方式" description="目录先与产品设计对齐；后端接入与配置生成能力完成后再开放操作。" />
            )}
          </div>
        ) : null}
      </Modal>

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
        title={<Space><KeyOutlined />{activeLanguageLabel} 接入</Space>}
        open={Boolean(secret)}
        width={960}
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
              <div className="mb-4 flex items-center gap-2">
                <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-xs font-semibold text-white">1</span>
                <Typography.Title level={3} className="!m-0 !text-base">上报端点</Typography.Title>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <Typography.Text type="secondary" className="mb-1 block text-xs">云区域</Typography.Text>
                  <Input value={secret.source.cloud_region_id ? `#${secret.source.cloud_region_id}` : 'default'} readOnly aria-label="云区域" />
                </div>
                <div>
                  <Typography.Text type="secondary" className="mb-1 block text-xs">组织</Typography.Text>
                  <div className="flex min-h-8 items-center gap-1 rounded-md border border-[var(--color-border-2)] px-3 py-1.5">
                    {secret.source.organization_ids.map((id) => <Tag key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>)}
                  </div>
                </div>
              </div>
              <Typography.Text strong className="mb-2 mt-4 block">API 端点</Typography.Text>
              <div className="relative max-w-full overflow-x-auto rounded-lg bg-slate-950 px-4 py-5 pr-14 font-mono text-sm text-slate-100">
                <Tag color="success" className="!mr-3">POST</Tag>
                <span>{assignedEndpoint}</span>
                <Button
                  type="text"
                  icon={<CopyOutlined />}
                  aria-label="复制 API 端点"
                  className="!absolute !right-2 !top-2 !text-slate-300"
                  onClick={() => void copy(assignedEndpoint, 'API 端点')}
                />
              </div>
            </ApmSurface>
            <ApmSurface padding="compact">
              <div className="mb-1 flex items-center gap-2">
                <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-xs font-semibold text-white">2</span>
                <Typography.Title level={3} className="!m-0 !text-base">接入配置</Typography.Title>
              </div>
              <Typography.Text type="secondary" className="mb-4 ml-8 block text-xs">
                填写服务身份，选择运行方式后生成包含安装、配置和启动步骤的完整片段。
              </Typography.Text>
              <Form
                form={snippetForm}
                layout="vertical"
                onFinish={generateSnippet}
              >
                <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2 lg:grid-cols-4">
                  {preferredLanguage ? (
                    <>
                      <Form.Item name="language" hidden><Input /></Form.Item>
                      <Form.Item label="语言 / SDK">
                        <Input value={activeLanguageLabel} readOnly />
                      </Form.Item>
                    </>
                  ) : (
                    <Form.Item name="language" label="语言 / SDK" rules={[{ required: true }]}>
                      <Select
                        options={LANGUAGE_OPTIONS}
                        onChange={(value) => {
                          setSnippetLanguage(value);
                          setSnippet(null);
                        }}
                      />
                    </Form.Item>
                  )}
                  <Form.Item name="service_namespace" label="服务命名空间" rules={[{ max: 256 }]}>
                    <Input placeholder="shop（可留空）" />
                  </Form.Item>
                  <Form.Item name="service_name" label="服务名称" rules={[{ required: true, message: '请输入服务名称' }, { max: 256 }]}>
                    <Input placeholder="checkout" />
                  </Form.Item>
                  <Form.Item name="environment" label="部署环境" rules={[{ required: true, message: '请输入部署环境' }, { max: 256 }]}>
                    <Input placeholder="production" />
                  </Form.Item>
                </div>
                <Segmented
                  value={snippetMode}
                  options={[
                    { value: 'agent', label: agentModeLabel },
                    { value: 'docker', label: 'Docker 运行（-e 注入）' },
                  ]}
                  onChange={(value) => {
                    setSnippetMode(value as SnippetMode);
                    setSnippet(null);
                  }}
                  className="mb-4"
                />
                <Button htmlType="submit" type="primary" loading={snippetSubmitting} icon={<SafetyCertificateOutlined />}>
                  验证 Token 并生成片段
                </Button>
              </Form>
              {snippet && (
                <div className="mt-4">
                  <Typography.Text type="secondary" className="mb-2 block text-xs">
                    {snippetMode === 'docker' ? 'Docker 运行（-e 注入）' : agentModeLabel}
                  </Typography.Text>
                  <div className="relative max-w-full overflow-x-auto rounded-lg bg-slate-950 p-4 pt-12 font-mono text-xs leading-6 text-slate-100">
                    <Tag className="!absolute !left-3 !top-3 !border-0 !bg-slate-700 !text-slate-100">BASH</Tag>
                    <Button
                      icon={<CopyOutlined />}
                      aria-label="复制接入片段"
                      className="!absolute !right-3 !top-2"
                      onClick={() => void copy(snippet.code, '接入片段')}
                    >
                      复制片段
                    </Button>
                    <pre className="m-0 min-w-max whitespace-pre">{snippet.code}</pre>
                  </div>
                </div>
              )}
            </ApmSurface>
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
