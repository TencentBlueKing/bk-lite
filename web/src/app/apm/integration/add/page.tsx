'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { ApiOutlined, CodeOutlined, CopyOutlined, ExperimentOutlined, GlobalOutlined, RocketOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, message, Modal, Segmented, Select, Space, Tag, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmApplication, ApmCloudRegion, ApmIngestSnippet, ApmIngestSnippetInput } from '@/app/apm/types';

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
    key: 'sdk', title: 'SDK', icon: <CodeOutlined />, methods: [
      { key: 'nodejs', title: 'Node.js', description: '零代码自动探针，支持 Express / Nest / Koa / Fastify', badge: '推荐', language: 'nodejs', available: true },
      { key: 'java', title: 'Java', description: 'Java Agent 字节码注入，支持 Spring / Dubbo / gRPC', badge: '推荐', language: 'java', available: true },
      { key: 'python', title: 'Python', description: '自动探针接入，支持 Django / Flask / FastAPI', language: 'python', available: true },
      { key: 'dotnet', title: '.NET', description: '基于 OpenTelemetry .NET 自动探针', available: false },
      { key: 'go', title: 'Go', description: '通过 OpenTelemetry Go SDK 完成应用内埋点', language: 'go', available: true },
    ],
  },
  { key: 'otel', title: 'OpenTelemetry', icon: <ApiOutlined />, methods: [{ key: 'otel-collector', title: 'OTel Collector', description: '复用自建 Collector，将链路转发到平台 OTLP 端点', available: false }] },
  { key: 'ebpf', title: 'eBPF', icon: <ExperimentOutlined />, methods: [{ key: 'ebpf-obi', title: 'eBPF 自动注入（OBI）', description: '无需修改业务代码，通过内核态捕获服务链路', badge: '低侵入', available: false }] },
  { key: 'kubernetes', title: 'Kubernetes', icon: <GlobalOutlined />, methods: [{ key: 'otel-operator', title: 'Kubernetes 自动注入', description: '通过 OTel Operator 和 Pod 注解自动注入探针', available: false }] },
];

type PageState = CatalogStateKind | 'ready';
type SnippetMode = 'agent' | 'docker';
type SnippetForm = Omit<ApmIngestSnippetInput, 'language' | 'runtime'>;

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function requestErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return error instanceof Error && error.message ? error.message : '生成接入配置失败，请稍后重试。';
}

export default function ApmIntegrationAddPage() {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modalApi, modalContextHolder] = Modal.useModal();
  const { getApplications, getCloudRegions, getIngestSnippet, isLoading } = useApmApi();
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [cloudRegions, setCloudRegions] = useState<ApmCloudRegion[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [emptyDescription, setEmptyDescription] = useState('请先创建并启用一个应用，再生成接入配置。');
  const [selectedMethod, setSelectedMethod] = useState<IntegrationMethod | null>(null);
  const [mode, setMode] = useState<SnippetMode>('agent');
  const [snippet, setSnippet] = useState<ApmIngestSnippet | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    if (isLoading) return;
    setState('loading');
    try {
      const [items, regions] = await Promise.all([getApplications(), getCloudRegions()]);
      setApplications(items.filter((item) => item.is_enabled));
      setCloudRegions(regions);
      if (!items.some((item) => item.is_enabled)) {
        setEmptyDescription('请先创建并启用一个应用，再生成接入配置。');
        setState('empty');
      } else if (regions.length === 0) {
        setEmptyDescription('暂无可用云区域，请联系运维配置区域 APM OTLP 接入端点。');
        setState('empty');
      } else {
        setState('ready');
      }
    } catch (error) {
      setState(catalogErrorKind(error));
    }
  }, [getApplications, getCloudRegions, isLoading]);

  useEffect(() => { void loadCatalog(); }, [loadCatalog]);

  const applicationOptions = useMemo(() => applications.map((application) => ({
    value: application.application_id,
    label: `${application.name}（${application.application_id}）`,
  })), [applications]);
  const cloudRegionOptions = useMemo(() => cloudRegions.map((region) => ({
    value: region.id,
    label: region.name,
  })), [cloudRegions]);

  const openMethod = (method: IntegrationMethod) => {
    if (!method.available || !method.language) {
      modalApi.info({ title: `${method.title} 接入`, content: '当前 MVP 尚未开放此接入方式。', okText: '知道了' });
      return;
    }
    setSelectedMethod(method);
    setMode('agent');
    setSnippet(null);
    setGenerationError(null);
  };

  const copyWithFeedback = async (value: string, success: string) => {
    try {
      await copyText(value);
      messageApi.success(success);
    } catch {
      messageApi.error('复制失败，请手动选择并复制');
    }
  };

  const generate = async (values: SnippetForm) => {
    if (!selectedMethod?.language) return;
    setGenerating(true);
    setGenerationError(null);
    try {
      const result = await getIngestSnippet({
        ...values,
        language: selectedMethod.language,
        runtime: mode === 'docker' ? 'docker' : 'host',
      });
      setSnippet(result);
      messageApi.success('接入配置已生成；关闭窗口后不会保存');
    } catch (error) {
      setSnippet(null);
      setGenerationError(requestErrorMessage(error));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <ApmRouteShell title="添加接入" description="选择语言与应用，即时生成可复制的 OpenTelemetry 接入配置。">
      {messageContextHolder}
      {modalContextHolder}
      <Alert className="mb-4" showIcon type="info" message="接入配置不会保存" description="应用是持久化的业务边界；服务与接入实例将在遥测数据首次上报后自动发现。当前版本不签发或校验 APM Token。" />
      {state === 'loading' || state === 'error' || state === 'degraded' ? (
        <ApmSurface><CatalogState kind={state} /></ApmSurface>
      ) : state === 'empty' ? (
        <ApmSurface>
          <CatalogState kind="empty" description={emptyDescription} />
          {applications.length === 0 ? <div className="mt-3 text-center"><Link href="/apm/integration/applications"><Button type="primary">前往应用管理</Button></Link></div> : null}
        </ApmSurface>
      ) : (
        <div className="flex flex-col gap-4">
          {INTEGRATION_GROUPS.map((group) => (
            <ApmSurface key={group.key}>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-1)]"><span className="text-[var(--color-primary)]">{group.icon}</span>{group.title}</div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.methods.map((method) => (
                  <Card
                    key={method.key}
                    hoverable
                    role="button"
                    tabIndex={0}
                    aria-label={`${method.title} 接入${method.available ? '' : '，规划中'}`}
                    className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                    onClick={() => openMethod(method)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        openMethod(method);
                      }
                    }}
                  >
                    <div className="flex min-h-24 items-start justify-between gap-3">
                      <div><Typography.Title level={5} className="!mb-2">{method.title}</Typography.Title><Typography.Text type="secondary" className="text-xs leading-5">{method.description}</Typography.Text></div>
                      <Space direction="vertical" align="end" size={4}>{method.badge ? <Tag color="blue">{method.badge}</Tag> : null}{!method.available ? <Tag>规划中</Tag> : null}</Space>
                    </div>
                  </Card>
                ))}
              </div>
            </ApmSurface>
          ))}
        </div>
      )}

      <Modal title={`${selectedMethod?.title ?? ''} 接入`} open={Boolean(selectedMethod)} width={920} footer={null} onCancel={() => setSelectedMethod(null)} destroyOnHidden styles={{ body: { maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' } }}>
        <div className="flex flex-col gap-4 pt-2">
          <ApmSurface>
            <div className="mb-4 flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--color-primary)] text-sm font-semibold text-white">1</span><Typography.Text strong>上报端点</Typography.Text></div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Typography.Text type="secondary" className="mb-1 block text-xs">OTLP/HTTP 端点</Typography.Text>
                <Space.Compact block>
                  <Button disabled>POST</Button>
                  <Input readOnly value={snippet?.http_endpoint ?? '生成配置后显示'} />
                  <Button disabled={!snippet} icon={<CopyOutlined />} onClick={() => snippet && void copyWithFeedback(snippet.http_endpoint, 'HTTP 端点已复制')}>复制</Button>
                </Space.Compact>
              </div>
              <div>
                <Typography.Text type="secondary" className="mb-1 block text-xs">OTLP/gRPC 端点</Typography.Text>
                <Space.Compact block>
                  <Button disabled>gRPC</Button>
                  <Input readOnly value={snippet?.grpc_endpoint ?? '生成配置后显示'} />
                  <Button disabled={!snippet} icon={<CopyOutlined />} onClick={() => snippet && void copyWithFeedback(snippet.grpc_endpoint, 'gRPC 端点已复制')}>复制</Button>
                </Space.Compact>
              </div>
            </div>
            <Typography.Text type="secondary" className="mt-3 block text-xs">当前版本无需 APM Token；端点由所选云区域的受信配置提供。</Typography.Text>
          </ApmSurface>

          <ApmSurface>
            <div className="mb-1 flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--color-primary)] text-sm font-semibold text-white">2</span><Typography.Text strong>接入配置</Typography.Text></div>
            <Typography.Text type="secondary" className="mb-4 block text-xs">应用 ID、服务名称和版本将分别映射到标准 OpenTelemetry 资源属性。</Typography.Text>
            <Form<SnippetForm>
              key={selectedMethod?.key ?? 'integration-form'}
              layout="vertical"
              initialValues={{
                application_id: applications[0]?.application_id,
                cloud_region_id: cloudRegions[0]?.id,
                service_name: '',
                service_version: '',
                environment: 'production',
              }}
              onValuesChange={() => { setSnippet(null); setGenerationError(null); }}
              onFinish={(values) => void generate(values)}
            >
              <div className="grid gap-x-5 md:grid-cols-2">
                <Form.Item name="application_id" label="应用" rules={[{ required: true, message: '请选择应用' }]}><Select showSearch optionFilterProp="label" options={applicationOptions} /></Form.Item>
                <Form.Item name="cloud_region_id" label="云区域" rules={[{ required: true, message: '请选择云区域' }]}><Select showSearch optionFilterProp="label" options={cloudRegionOptions} /></Form.Item>
                <Form.Item name="service_name" label="服务名称" rules={[{ required: true, whitespace: true, message: '请输入服务名称' }, { max: 256 }]}><Input placeholder="service.name，例如 checkout" /></Form.Item>
                <Form.Item name="service_version" label="服务版本" rules={[{ max: 256 }]}><Input placeholder="service.version，例如 1.4.0（可选）" /></Form.Item>
                <Form.Item name="environment" label="部署环境" rules={[{ required: true, whitespace: true, message: '请输入部署环境' }, { max: 256 }]}><Input placeholder="deployment.environment，例如 production" /></Form.Item>
              </div>
              {generationError ? <Alert className="mb-4" showIcon type="error" message="配置生成失败" description={generationError} /> : null}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Segmented value={mode} onChange={(value) => { setMode(value as SnippetMode); setSnippet(null); }} options={[{ label: `${selectedMethod?.title ?? ''} 自动探针`, value: 'agent' }, { label: 'Docker 运行（-e 注入）', value: 'docker' }]} />
                <Button htmlType="submit" type="primary" icon={<RocketOutlined />} loading={generating}>生成临时配置</Button>
              </div>
            </Form>
          </ApmSurface>

          {snippet ? (
            <ApmSurface>
              <div className="mb-3 flex items-center justify-between"><div><Typography.Text strong>Shell 接入片段</Typography.Text><Typography.Text type="secondary" className="ml-2 text-xs">{snippet.cloud_region.name} · 仅在本窗口保留</Typography.Text></div><Button icon={<CopyOutlined />} onClick={() => void copyWithFeedback(snippet.code, '片段已复制')}>复制片段</Button></div>
              <pre className="max-h-[420px] overflow-auto rounded-lg bg-[#0f172a] p-4 text-xs leading-6 text-slate-100"><code>{snippet.code}</code></pre>
            </ApmSurface>
          ) : null}
        </div>
      </Modal>
    </ApmRouteShell>
  );
}
